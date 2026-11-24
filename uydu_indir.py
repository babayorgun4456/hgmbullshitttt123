"""HGM güncel uydu görüntüsü indirici — bbox + zoom -> mozaik PNG.

Kaynak: atlas.harita.gov.tr/webservis/ortofoto (HGM'nin güncel ortofoto servisi).
İstek başlığında Referer zorunlu. Anahtarlar sunucu.py ile aynı ayar.env dosyasından okunur
(HGM_WS_KEY, HGM_HARITA_KEY, HGM_API_KEY). HGM_API_KEY *ortam değişkeni* verilirse
bütün katmanlarda o kullanılır (eski aracın davranışı).

Kullanım:
    python uydu_indir.py --bbox 32.830,39.920,32.845,39.930 --zoom 17
    python uydu_indir.py --bbox 32.830,39.920,32.845,39.930 --otomatik-zoom
    python uydu_indir.py --bbox 36.4,26.9,36.6,27.1 --zoom 15 --zorla

Çıktı: mozaik PNG + aynı adla .json (bbox, zoom, karo sayısı, kaynak, tarih,
otomatik zoom ölçümü, kapsama örneklemi) ve world file (.pgw).

Uyarı: HGM verisi telifli. Kişisel/yerel kullanım için; toplu indirmeyi
sınırlı tutun (varsayılan en çok 400 karo) ve herkese açık yayınlamayın.
"""
import argparse
import concurrent.futures as cf
import io
import json
import math
import os
import statistics
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

KATMANLAR = {
    "uydu": "https://atlas.harita.gov.tr/webservis/ortofoto/{z}/{x}/{y}.jpg",
    "hgm_harita": "https://atlas.harita.gov.tr/webservis/harita/hgm_harita/{z}/{x}/{y}.png",
    "topografik": "https://atlasapitest.harita.gov.tr/Layers/Topografik/{z}/{x}/{y}.png",
}
# sunucu.py ile aynı ayar.env ve aynı adlar
AYAR_ADLARI = {"uydu": "HGM_WS_KEY", "hgm_harita": "HGM_HARITA_KEY", "topografik": "HGM_API_KEY"}
BASLIK = {
    "Referer": "https://atlas.harita.gov.tr/",
    "Origins": "https://atlas.harita.gov.tr",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
}
EN_BUYUK_Z = {"uydu": 19, "hgm_harita": 16, "topografik": 19}
KARO = 256

# HGM'yi yormamak için: her istekten önce bekleme ve en çok 4 eşzamanlı istek
ISTEK_BEKLEME = 0.1
EN_COK_ESZAMANLI = 4

# Otomatik zoom. Eşikler 24.11.2026 ölçümünden (Ankara, Hakkari, Gümrü, Halkis, Filibe, Berbera).
MAE_ESIGI = 10.0          # z -> z+1 geçişi yalnız bu farkın üstünde yeni bilgi sayılır
OLCUM_NOKTA = 3
OLCUM_NOKTA_EN_COK = 5
EN_AZ_ZOOM = 12
EN_UST_ZOOM = 19
OLCUM_BUTCESI = 30        # ölçüm için indirilecek en çok karo

# Boş (deniz/veri yok) karo: düz gri. Ölçülen boş karolar 1,8-2,4 KB ve std <= 3,2.
# Prompt'taki varsayılan 6,0 idi. 24.11.2026'da Halkis z16'da koyu orman karosu (2494 bayt,
# std 4,2) boş sayılıp mozaikten silindi. Ölçülen en yüksek boş std'nin hemen üstüne çekildi.
BOS_STD = 3.5
BOS_KUCUK_BAYT = 2200
BOS_KUCUK_STD = 10.0
KAPSAMA_NOKTA = 9         # 3x3 grid
BOS_DURDUR_ORANI = 0.6    # bu oranın üstünde --zorla olmadan indirilmez
BOS_UYARI_ORANI = 0.2
HATA_ORANI = 0.2          # bu oranın üstünde karo inmezse iş iptal


def anahtarlari_oku():
    """ayar.env (ANAHTAR=deger) okunur, sunucu.py ile aynı dosya."""
    ayar = {}
    dosya = Path(__file__).resolve().parent / "ayar.env"
    if dosya.exists():
        for satir in dosya.read_text(encoding="utf-8").splitlines():
            if "=" in satir and not satir.lstrip().startswith("#"):
                k, v = satir.split("=", 1)
                ayar[k.strip()] = v.strip()
    return {katman: ayar.get(ad, "") for katman, ad in AYAR_ADLARI.items()}


ANAHTARLAR = anahtarlari_oku()
_istek_kilidi = threading.Lock()
_son_istek = [0.0]


def karo_no(lon, lat, z):
    """Boylam/enlem -> (x, y) karo numarası (Web Mercator)."""
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(max(min(lat, 85.05112878), -85.05112878))
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def karo_no_kesirli(lon, lat, z):
    """karo_no ile aynı, tam sayıya yuvarlanmadan: noktanın karo içindeki yeri için."""
    n = 2 ** z
    lat_rad = math.radians(max(min(lat, 85.05112878), -85.05112878))
    return (lon + 180.0) / 360.0 * n, (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n


def karo_bbox(x, y, z):
    """Karonun coğrafi sınırları (batı, güney, doğu, kuzey)."""
    n = 2 ** z

    def boylam(i):
        return i / n * 360.0 - 180.0

    def enlem(i):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * i / n))))

    return boylam(x), enlem(y + 1), boylam(x + 1), enlem(y)


def karo_indir(katman, z, x, y, deneme=3):
    url = KATMANLAR[katman].format(z=z, x=x, y=y)
    anahtar = "key" if "atlasapitest" in url else "apikey"
    deger = os.environ.get("HGM_API_KEY") or ANAHTARLAR[katman]
    if not deger:
        raise RuntimeError(f"{katman} anahtarı yok: ayar.env içine {AYAR_ADLARI[katman]}=... yazın")
    url += f"?{anahtar}={deger}"
    son_hata = None
    for i in range(deneme):
        with _istek_kilidi:  # istekler arasında en az ISTEK_BEKLEME
            bekle = _son_istek[0] + ISTEK_BEKLEME - time.time()
            _son_istek[0] = max(time.time(), _son_istek[0] + ISTEK_BEKLEME)
        if bekle > 0:
            time.sleep(bekle)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=BASLIK), timeout=25) as r:
                return x, y, r.read()
        except Exception as e:  # yeniden dene, sonra pes et
            son_hata = e
            time.sleep(0.4 * (i + 1))
    raise RuntimeError(f"{katman} {z}/{x}/{y}: {type(son_hata).__name__}")


class KaroDeposu:
    """Ölçüm, kapsama ve mozaik aynı karoyu iki kez indirmesin. İndirilen sayıyı da tutar."""

    def __init__(self, katman, indirici=None):
        self.katman, self.veri, self.indirilen = katman, {}, 0
        self.indirici = indirici or karo_indir
        self.kilit = threading.Lock()

    def al(self, z, x, y):
        if (z, x, y) not in self.veri:
            veri = self.indirici(self.katman, z, x, y)[2]
            with self.kilit:
                self.veri[(z, x, y)] = veri
                self.indirilen += 1
        return self.veri[(z, x, y)]


def gri(veri):
    return Image.open(io.BytesIO(veri)).convert("L")


def bos_karo_mu(veri):
    """Deniz ya da veri olmayan yer: neredeyse düz tek renk karo."""
    std = ImageStat.Stat(gri(veri)).stddev[0]
    return std < BOS_STD or (len(veri) < BOS_KUCUK_BAYT and std < BOS_KUCUK_STD)


def ceyrek_mae(ust_veri, alt_veri, ceyrek_x, ceyrek_y):
    """z karosunun bir çeyreği ile o çeyreğe denk gelen z+1 karosunun 2:1 küçültülmüşü
    arasındaki ortalama mutlak fark. Küçükse z+1 yeni ayrıntı getirmiyor, yalnız büyütüyor."""
    yarim = KARO // 2
    ust = gri(ust_veri).crop((ceyrek_x * yarim, ceyrek_y * yarim, (ceyrek_x + 1) * yarim, (ceyrek_y + 1) * yarim))
    alt = gri(alt_veri).resize((yarim, yarim), Image.BOX)
    return ImageStat.Stat(ImageChops.difference(ust, alt)).mean[0]


def olcum_noktalari(b, g, d, k, adet):
    """Merkez ve köşelere yakın noktalar (bbox'ın %25/%75'i), sabit sırayla."""
    orta = ((b + d) / 2, (g + k) / 2)
    kose = [(b + (d - b) * fx, g + (k - g) * fy) for fx, fy in ((.25, .75), (.75, .25), (.25, .25), (.75, .75))]
    return ([orta] + kose)[:adet]


def zoom_sec(depo, noktalar, en_az, esik, butce):
    """en_az..EN_UST_ZOOM arasındaki bütün geçişleri ölçer, farkı eşiğin üstünde kalan EN YÜKSEK
    z+1'i seçer. (seçilen, ölçümler, gerekçe)

    "İlk düşük farkta dur" kuralı kullanılmıyor: 24.11.2026 ölçümünde Ankara'da z12->13 farkı
    9,3 (eşik altı) çıkıp z13->14 13,0, z16->17 10,2 idi; ilk düşükte durunca z12 seçiliyordu.
    Ermenistan'da da z12-14 arası 5 civarı, z14-18 arası 15-60 (farklı görüntü kaynağı).
    Çeyrek yöntemiyle bir nokta tam tarama için 8 karo tutar, 3 nokta bütçeye sığar."""
    olcumler, z = [], en_az
    while z < EN_UST_ZOOM:
        maeler = []
        for lon, lat in noktalar:
            fx, fy = karo_no_kesirli(lon, lat, z + 1)
            ax, ay = int(fx), int(fy)
            gerekli = 2 if (z, ax // 2, ay // 2) not in depo.veri else 1
            if depo.indirilen + gerekli > butce:
                return _en_yuksek_gecen(olcumler, en_az, esik, f"ölçüm bütçesi ({butce} karo) z{z}'de doldu")
            try:
                ust = depo.al(z, ax // 2, ay // 2)
                alt = depo.al(z + 1, ax, ay)
            except Exception:  # geçici HGM hatası: bu nokta bu seviyede sayılmaz
                continue
            if bos_karo_mu(ust):  # denizde fark hep sıfır çıkar, kararı bozmasın
                continue
            maeler.append(ceyrek_mae(ust, alt, ax % 2, ay % 2))
        if maeler:  # hepsi boş/denizse bu seviye karara katılmaz
            olcumler.append({"z": z, "mae": round(statistics.median(maeler), 2)})
        z += 1
    return _en_yuksek_gecen(olcumler, en_az, esik, "tarama bitti")


def _en_yuksek_gecen(olcumler, en_az, esik, not_):
    gecen = [o["z"] + 1 for o in olcumler if o["mae"] >= esik]
    if not olcumler:
        return en_az, olcumler, f"{not_}; ölçülebilen nokta yok (boş/deniz ya da HGM hatası), z{en_az} seçildi"
    if not gecen:
        return en_az, olcumler, f"{not_}; hiçbir geçişte fark {esik} eşiğine ulaşmadı, z{en_az} seçildi"
    secilen = max(gecen)
    return secilen, olcumler, (f"{not_}; farkı {esik} eşiğinin üstünde kalan en yüksek geçiş "
                               f"z{secilen - 1}->z{secilen}, z{secilen} seçildi")


def kapsama_ornekle(depo, b, g, d, k, z, adet):
    """Bbox'ı ızgara noktalarıyla örnekleyip boş karo oranını döner."""
    kenar = max(1, round(math.sqrt(adet)))
    karolar = sorted({karo_no(b + (d - b) * (i + .5) / kenar, g + (k - g) * (j + .5) / kenar, z)
                      for i in range(kenar) for j in range(kenar)})
    bos = [list(xy) for xy in karolar if bos_karo_mu(depo.al(z, *xy))]
    return {"ornek": len(karolar), "bos": len(bos), "oran": round(len(bos) / len(karolar), 2), "bos_karolar": bos}


def karo_araligi(b, g, d, k, z):
    x0, y0 = karo_no(b, k, z)   # sol üst = batı, kuzey
    x1, y1 = karo_no(d, g, z)   # sağ alt = doğu, güney
    return x0, y0, x1, y1


def main(argv=None, indirici=None):
    p = argparse.ArgumentParser(description="HGM uydu görüntüsünü mozaik olarak indirir")
    p.add_argument("--bbox", required=True, help="batı,güney,doğu,kuzey (ondalık derece)")
    p.add_argument("--zoom", type=int, default=17)
    p.add_argument("--katman", default="uydu", choices=sorted(KATMANLAR))
    p.add_argument("--cikti", default=None)
    p.add_argument("--en-cok-karo", type=int, default=400)
    p.add_argument("--eszamanli", type=int, default=4, help="HGM'yi yormamak için düşük tutun (en çok 4)")
    p.add_argument("--otomatik-zoom", action="store_true", help="gerçek ayrıntının bittiği zoom'u ölçüp seçer")
    p.add_argument("--esik", type=float, default=MAE_ESIGI)
    p.add_argument("--olcum-nokta", type=int, default=OLCUM_NOKTA)
    p.add_argument("--en-az-zoom", type=int, default=EN_AZ_ZOOM)
    p.add_argument("--olcum-butcesi", type=int, default=OLCUM_BUTCESI)
    p.add_argument("--kapsama-nokta", type=int, default=KAPSAMA_NOKTA)
    p.add_argument("--bos-esik", type=float, default=BOS_DURDUR_ORANI)
    p.add_argument("--zorla", action="store_true", help="bölge çoğunlukla boş/deniz olsa da indir")
    p.add_argument("--saydam-bos", action=argparse.BooleanOptionalAction, default=True,
                   help="boş karoları mozaikte saydam bırak (RGBA)")
    p.add_argument("--en-cok-hata-orani", type=float, default=HATA_ORANI)
    a = p.parse_args(argv)

    try:
        b, g, d, k = (float(t) for t in a.bbox.split(","))
    except ValueError:
        sys.exit("--bbox dört sayı olmalı: batı,güney,doğu,kuzey")
    if not (b < d and g < k):
        sys.exit("--bbox sırası yanlış: batı<doğu, güney<kuzey")
    if a.eszamanli > EN_COK_ESZAMANLI:
        print(f"uyarı: --eszamanli {a.eszamanli} -> {EN_COK_ESZAMANLI} (HGM'yi yormamak için üst sınır)")
        a.eszamanli = EN_COK_ESZAMANLI
    depo = KaroDeposu(a.katman, indirici)

    otomatik = None
    if a.otomatik_zoom:
        noktalar = olcum_noktalari(b, g, d, k, max(1, min(a.olcum_nokta, OLCUM_NOKTA_EN_COK)))
        try:
            secilen, olcumler, gerekce = zoom_sec(depo, noktalar, a.en_az_zoom, a.esik, a.olcum_butcesi)
        except Exception as e:
            sys.exit(f"otomatik zoom ölçümü başarısız: {e}. Bir süre sonra tekrar deneyin ya da --zoom verin.")
        for o in olcumler:
            print(f"  ölçüm z{o['z']}->z{o['z'] + 1}: MAE {o['mae']}")
        a.zoom = min(secilen, EN_BUYUK_Z[a.katman])
        while a.zoom > 0:
            x0, y0, x1, y1 = karo_araligi(b, g, d, k, a.zoom)
            if (x1 - x0 + 1) * (y1 - y0 + 1) <= a.en_cok_karo:
                break
            gerekce += f"; z{a.zoom} karo bütçesini aşıyor, bir alt zoom"
            a.zoom -= 1
        print(f"otomatik zoom: z{a.zoom} ({gerekce})  [ölçüm için {depo.indirilen} karo indirildi]")
        otomatik = {"secilen": a.zoom, "olculen": secilen, "esik": a.esik, "olcumler": olcumler,
                    "olcum_karo": depo.indirilen, "gerekce": gerekce}
    if not (0 <= a.zoom <= EN_BUYUK_Z[a.katman]):
        sys.exit(f"{a.katman} için zoom 0-{EN_BUYUK_Z[a.katman]} aralığında olmalı")

    x0, y0, x1, y1 = karo_araligi(b, g, d, k, a.zoom)
    sutun, satir = x1 - x0 + 1, y1 - y0 + 1
    toplam = sutun * satir
    print(f"karo: {sutun}×{satir} = {toplam}  (z{a.zoom}, {a.katman})")
    if toplam > a.en_cok_karo:
        sys.exit(f"çok fazla karo ({toplam} > {a.en_cok_karo}). Zoom'u düşürün veya --en-cok-karo artırın.")

    kapsama = None
    if a.katman == "uydu":  # boş karo ölçütü uydu görüntüsü için ölçüldü
        try:
            kapsama = kapsama_ornekle(depo, b, g, d, k, a.zoom, a.kapsama_nokta)
        except Exception as e:
            print(f"uyarı: kapsama örneklenemedi ({e}), devam ediliyor")
        if kapsama and kapsama["oran"] > a.bos_esik and not a.zorla:
            print(f"bölgenin %{round(kapsama['oran'] * 100)}'i boş/deniz görünüyor ({kapsama['bos']}/{kapsama['ornek']} "
                  f"örnek). İndirilmedi. Yine de indirmek için --zorla ekleyin.", file=sys.stderr)
            return 2
        if kapsama and kapsama["oran"] >= BOS_UYARI_ORANI:
            print(f"uyarı: bölgenin %{round(kapsama['oran'] * 100)}'i boş/deniz görünüyor, devam ediliyor")

    cikti = a.cikti or f"uydu_z{a.zoom}_{datetime.now().strftime('%Y%m%d_%H%M')}.png"
    if not cikti.lower().endswith(".png"):
        cikti += ".png"

    karolar = [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
    t0 = time.time()
    sonuc, eksik = {}, []

    def indir(xy):
        try:
            return xy, depo.al(a.zoom, *xy)
        except Exception as e:
            return xy, e

    with cf.ThreadPoolExecutor(a.eszamanli) as ex:
        for i, (xy, veri) in enumerate(ex.map(indir, karolar), 1):
            if isinstance(veri, Exception):
                eksik.append(list(xy))
            else:
                sonuc[xy] = veri
            if i % 25 == 0 or i == toplam:
                print(f"  {i}/{toplam} karo  {time.time()-t0:.1f} sn", flush=True)
    if not sonuc:
        sys.exit("hiç karo indirilemedi. İnternet bağlantısını ve ayar.env anahtarlarını kontrol edin.")
    if len(eksik) / toplam > a.en_cok_hata_orani:
        sys.exit(f"{len(eksik)}/{toplam} karo indirilemedi (sınır %{round(a.en_cok_hata_orani * 100)}). "
                 f"HGM geçici olarak sorunlu olabilir, birkaç dakika sonra tekrar deneyin.")

    saydam = a.saydam_bos and a.katman == "uydu"
    bos_kume = {xy for xy, veri in sonuc.items() if saydam and bos_karo_mu(veri)}
    # Boş karo yoksa eskisi gibi RGB, varsa boşlar saydam kalsın diye RGBA
    kip = "RGBA" if bos_kume or (saydam and eksik) else "RGB"
    mozaik = Image.new(kip, (sutun * KARO, satir * KARO))
    for (x, y) in karolar:
        if (x, y) not in sonuc or (x, y) in bos_kume:
            continue
        try:
            mozaik.paste(Image.open(io.BytesIO(sonuc[(x, y)])).convert(kip), ((x - x0) * KARO, (y - y0) * KARO))
        except Exception:
            continue  # bozuk karo: atla, mozaik devam
    mozaik.save(cikti)

    bilgi = {
        "katman": a.katman,
        "zoom": a.zoom,
        "istek_bbox": [b, g, d, k],
        "karo_bbox": list(karo_bbox(x0, y0, a.zoom)[:1]) + [karo_bbox(x1, y1, a.zoom)[1]] +
                     [karo_bbox(x1, y1, a.zoom)[2], karo_bbox(x0, y0, a.zoom)[3]],
        "karo": {"x": [x0, x1], "y": [y0, y1], "sayi": toplam},
        "piksel": [mozaik.width, mozaik.height],
        "kaynak": "Harita Genel Müdürlüğü — atlas.harita.gov.tr",
        "cekilme": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if otomatik:
        bilgi["otomatik_zoom"] = otomatik
    if kapsama:
        bilgi["kapsama"] = kapsama
    if eksik:
        bilgi["eksik_karolar"] = eksik
    with open(os.path.splitext(cikti)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump(bilgi, f, ensure_ascii=False, indent=1)

    # world file: piksel başına derece
    kb = karo_bbox(x0, y0, a.zoom)
    boyut = (kb[2] - kb[0]) / (sutun * KARO)
    with open(os.path.splitext(cikti)[0] + ".pgw", "w") as f:
        f.write(f"{boyut}\n0\n0\n{-boyut}\n{kb[0] + boyut/2}\n{kb[3] - boyut/2}\n")

    if eksik:
        print(f"uyarı: {len(eksik)} karo eksik, mozaikte boş kaldı (liste .json içinde)")
    print(f"yazıldı: {cikti}  {mozaik.width}×{mozaik.height}px {kip}  ({time.time()-t0:.1f} sn, "
          f"toplam {depo.indirilen} karo indirildi)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
