"""HGM Atlas karo sunucusu (yerel vekil + önbellek).

Her HGM katmanı tek biçimli bir XYZ adresinden verilir:
    http://localhost:8833/t/<katman>/{z}/{x}/{y}
Bu adres Leaflet, OpenLayers, MapLibre, QGIS gibi her harita altyapısında
olduğu gibi kullanılabilir. Katman listesi: http://localhost:8833/katmanlar.json

Neden vekil gerekiyor:
- atlas.harita.gov.tr/webservis/... yalnız Referer https://atlas.harita.gov.tr/
  olan istekleri kabul ediyor (yoksa 403 "Invalid referer"). atlasapitest
  Layers/* uçları ise Referer istemiyor, CORS açık.
- Bütün katmanlar tek biçimli bir adresten ve disk önbelleğinden verilir. Aynı karo
  ikinci kez HGM'den istenmez, HGM 403 ile kapatırsa o katmana bir süre gidilmez.

Anahtarlar ayar.env dosyasından ya da ortam değişkenlerinden okunur (ayar.env.ornek).
Çalıştır:  python sunucu.py
"""
import collections
import contextlib
import hashlib
import http.client
import http.server
import json
import os
import posixpath
import random
import re
import socket
import socketserver
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

KOK = Path(__file__).resolve().parent
ONBELLEK = KOK / "onbellek"
AYAR_DOSYASI = KOK / "ayar.env"
GEREKLI_AYARLAR = ("HGM_API_KEY", "HGM_WS_KEY", "HGM_HARITA_KEY")
# Vektör karo "enc" değerleri isteğe bağlı: eksikse o vektör katmanı listeye girmez.
VEKTOR_AYARLARI = ("HGM_VEKTOR_ENC", "HGM_ETIKET_ENC", "HGM_ETIKET_UYDU_ENC", "HGM_METEO_ENC")
SECIMLI_AYARLAR = ("PORT", "HGM_ESZAMANLI", "HGM_HIZ", "HGM_UST_ADRES") + VEKTOR_AYARLARI


def ayar_oku():
    """ayar.env (ANAHTAR=deger satırları) okunur, ortam değişkeni varsa o geçerli olur.
    Anahtarlar HGM'nin genel config.js dosyasında açık ama kodda durmamalı:
    kod paylaşılınca anahtarlar da gitmesin."""
    ayar = {}
    if AYAR_DOSYASI.exists():
        for satir in AYAR_DOSYASI.read_text(encoding="utf-8").splitlines():
            satir = satir.strip()
            if satir and not satir.startswith("#") and "=" in satir:
                k, v = satir.split("=", 1)
                ayar[k.strip()] = v.strip().strip('"').strip("'")
    for k in GEREKLI_AYARLAR + SECIMLI_AYARLAR:
        if os.environ.get(k):
            ayar[k] = os.environ[k]
    return ayar


AYAR = ayar_oku()
EKSIK_AYARLAR = [k for k in GEREKLI_AYARLAR if not AYAR.get(k)]
PORT = int(AYAR.get("PORT") or 8833)
API_KEY = AYAR.get("HGM_API_KEY", "")
WS_KEY = AYAR.get("HGM_WS_KEY", "")
HGM_HARITA_KEY = AYAR.get("HGM_HARITA_KEY", "")
# Yalnız testler için: bütün HGM istekleri bu adrese gider (ör. http://127.0.0.1:9999).
UST_ADRES = AYAR.get("HGM_UST_ADRES") or None

# ad: (görünen ad, sunucu, yol şablonu, uzantı, en düşük z, HGM'nin verdiği en yüksek z, tür)
KATMANLAR = {
    "temel":             ("Temel",               "atlasapitest.harita.gov.tr", "/Layers/Base/{z}/{x}/{y}.png?key=" + API_KEY,       "png", 0, 19, "altlik"),
    "siyasi":            ("Siyasi",              "atlasapitest.harita.gov.tr", "/Layers/Siyasi/{z}/{x}/{y}.png?key=" + API_KEY,     "png", 0, 15, "altlik"),
    "gece":              ("Gece",                "atlasapitest.harita.gov.tr", "/Layers/Gece/{z}/{x}/{y}.png?key=" + API_KEY,       "png", 0, 19, "altlik"),
    "topografik":        ("Topografik",          "atlasapitest.harita.gov.tr", "/Layers/Topografik/{z}/{x}/{y}.png?key=" + API_KEY, "png", 0, 19, "altlik"),
    "uydu":              ("Uydu",                "atlas.harita.gov.tr", "/webservis/ortofoto/{z}/{x}/{y}.jpg?apikey=" + WS_KEY,                   "jpg", 0, 19, "altlik"),
    "fiziki_raster":     ("Fiziki (Raster)",     "atlas.harita.gov.tr", "/webservis/hgmrasterhrt/fiziki/{z}/{x}/{y}.png?apikey=" + WS_KEY,        "png", 1, 9,  "altlik"),
    "siyasi_raster":     ("Siyasi (Raster)",     "atlas.harita.gov.tr", "/webservis/hgmrasterhrt/m%C3%BClki_idari/{z}/{x}/{y}.png?apikey=" + WS_KEY, "png", 1, 9, "altlik"),
    "topografik_raster": ("Topografik (Raster)", "atlas.harita.gov.tr", "/webservis/hgmrasterhrt/topografik/{z}/{x}/{y}.png?apikey=" + WS_KEY,    "png", 1, 13, "altlik"),
    "hgm_harita":        ("HGM Harita",          "atlas.harita.gov.tr", "/webservis/harita/hgm_harita/{z}/{x}/{y}.png?apikey=" + HGM_HARITA_KEY,  "png", 1, 16, "altlik"),
    "yol_yazi":          ("Yol ve yer adları (şeffaf)", "atlas.harita.gov.tr", "/webservis/harita/yolorta_uydu/{z}/{x}/{y}.png?apikey=" + WS_KEY, "png", 6, 19, "ust"),
    "yol_yazi_acik":     ("Yol ve yer adları, açık zemin (şeffaf)", "atlas.harita.gov.tr", "/webservis/harita/yolorta_varsayilan/{z}/{x}/{y}.png?apikey=" + WS_KEY, "png", 6, 20, "ust"),
}

# Vektör karolar (Mapbox Vector Tile). HGM sitesinin uydu ve korona stilleri bunları
# kullanıyor. Referer istemiyorlar ama anahtar istemciye gitmesin ve önbellek olsun diye
# raster katmanlarla aynı adres biçiminden verilir: /t/<ad>/{z}/{x}/{y}
# ayar adı: (görünen ad, sunucu, yol şablonu, en düşük z, en yüksek z, katman adı)
VEKTOR_TANIMLARI = {
    "HGM_VEKTOR_ENC":      ("HGM vektör: sınır, yol, yerleşim, göl, orman", "atlas1.harita.gov.tr", "/CPbf/{z}/{x}/{y}.pbf?enc=", 0, 21, "hgm_vektor"),
    "HGM_ETIKET_ENC":      ("HGM yer adları (vektör)", "atlas1.harita.gov.tr", "/CPbf/{z}/{x}/{y}.pbf?enc=", 0, 21, "hgm_etiket"),
    "HGM_ETIKET_UYDU_ENC": ("HGM yer adları, uydu stili (vektör)", "atlas1.harita.gov.tr", "/CPbf/{z}/{x}/{y}.pbf?enc=", 0, 21, "hgm_etiket_uydu"),
    "HGM_METEO_ENC":       ("Meteoroloji istasyonları (vektör)", "atlas.harita.gov.tr", "/api/Pbf/{z}/{x}/{y}.pbf?enc=", 5, 14, "meteoroloji"),
}
ENC_KATMAN = {}  # HGM stil dosyasındaki enc değeri -> bizim katman adı
for _ayar, (_gorunen, _host, _yol, _min, _max, _ad) in VEKTOR_TANIMLARI.items():
    if AYAR.get(_ayar):
        KATMANLAR[_ad] = (_gorunen, _host, _yol + quote(AYAR[_ayar], safe=""), "pbf", _min, _max, "vektor")
        ENC_KATMAN[AYAR[_ayar]] = _ad

BASLIK = {
    "Referer": "https://atlas.harita.gov.tr/",
    "Origin": "https://atlas.harita.gov.tr",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Connection": "keep-alive",
}
TIPLER = {"png": "image/png", "jpg": "image/jpeg", "pbf": "application/x-protobuf"}


# HGM'nin karo vermediği yerler (ör. Topografik Raster Türkiye dışında 404) için 1x1 şeffaf PNG
def _bos_png():
    import struct
    import zlib

    def parca(tur, veri):
        return struct.pack(">I", len(veri)) + tur + veri + struct.pack(">I", zlib.crc32(tur + veri))
    imza = bytes([137, 80, 78, 71, 13, 10, 26, 10])
    return (imza + parca(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + parca(b"IDAT", zlib.compress(bytes(5))) + parca(b"IEND", b""))


BOS_PNG = _bos_png()

# HGM bazen 200 ile hata sayfası ya da yarım gövde dönebilir. Doğrulanmadan diske
# yazılırsa bozuk karo kalıcı olur, o yüzden imza ve en küçük boy kontrol edilir.
IMZALAR = {"png": b"\x89PNG\r\n\x1a\n", "jpg": b"\xff\xd8\xff"}
EN_KUCUK_GOVDE = 64
# 404 ile "karo yok" denen yerler kalıcı değil, HGM sonradan veri ekleyebilir.
BOS_TTL = 30 * 86400
EN_YUKSEK_Z = 22


def gecerli_govde(uzanti, govde):
    if uzanti == "pbf":
        # Boş vektör karo geçerli (o bölgede veri yok). Dolu karo protobuf "layers"
        # alanıyla (alan 3, tür 2 = 0x1a) başlar. HTML/JSON hata sayfası bununla başlamaz.
        return not govde or govde[:1] == b"\x1a"
    return len(govde) >= EN_KUCUK_GOVDE and govde.startswith(IMZALAR[uzanti])


def gecerli_koordinat(z, x, y):
    return 0 <= z <= EN_YUKSEK_Z and 0 <= x < 2 ** z and 0 <= y < 2 ** z


# --- Günlük ---------------------------------------------------------------------
def log(seviye, olay, ayrinti=""):
    """Tek satır: ISO8601 zaman | seviye | olay | ayrıntı. Anahtar içeren HGM adresleri
    buraya hiç verilmez, yalnız katman adı ve z/x/y yazılır."""
    zaman = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"{zaman} | {seviye} | {olay} | {ayrinti}", flush=True)


# --- İstatistik -----------------------------------------------------------------
class Istatistik:
    def __init__(self):
        self.kilit = threading.Lock()
        self.sayac = collections.Counter()
        self.ust_sureler = collections.deque(maxlen=2000)   # HGM'ye giden isteklerin süresi
        self.yanit_sureler = collections.deque(maxlen=2000)  # /t/ isteklerinin toplam süresi

    def say(self, ad, n=1):
        with self.kilit:
            self.sayac[ad] += n

    def sure(self, liste, sn):
        with self.kilit:
            getattr(self, liste).append(sn)

    @staticmethod
    def _yuzdelik(degerler, oran):
        if not degerler:
            return None
        s = sorted(degerler)
        return round(s[min(len(s) - 1, int(oran * len(s)))] * 1000, 1)

    def ozet(self):
        with self.kilit:
            ust, yanit = list(self.ust_sureler), list(self.yanit_sureler)
            sayac = dict(self.sayac)
        return {
            "sayac": sayac,
            "hgm_gecikme_ms": {"p50": self._yuzdelik(ust, 0.5), "p95": self._yuzdelik(ust, 0.95), "ornek": len(ust)},
            "yanit_gecikme_ms": {"p50": self._yuzdelik(yanit, 0.5), "p95": self._yuzdelik(yanit, 0.95), "ornek": len(yanit)},
        }


ISTATISTIK = Istatistik()


# --- HGM'ye giden istek sınırı ------------------------------------------------
# Ölçüm (24.11.2026, her ayar için 48 soğuk karo, temel z12, tarayıcı gibi 12 paralel istek):
#   ESZAMANLI=2,  HIZ=8/sn : toplam 4,3 sn, istemci p95 1,50 sn, HGM tek karo p50 112 ms
#   ESZAMANLI=4,  HIZ=40/sn: toplam 2,7 sn, istemci p95 0,53 sn, HGM tek karo p50 140 ms
#   ESZAMANLI=12, HIZ=40/sn: toplam 1,2 sn, istemci p95 0,38 sn, HGM tek karo p50 199 ms
# Loglardaki 1-2 sn'lik "soğuk karo" süresi HGM'nin yavaşlığı değil, bizim kuyrukta
# bekleme süresiydi. Hiçbir ayarda 403 olmadı. Ekranı en hızlı dolduran 12 bırakıldı.
ESZAMANLI = int(AYAR.get("HGM_ESZAMANLI") or 12)
# Hız sınırı (katman başına token bucket). Ölçümde ekran dolusu karo ~40-60 adet ve
# HGM 16 paralel istekte bile 403 vermedi. Sınır yalnız taşkın koruması olarak duruyor,
# o yüzden tarayıcının bir ekran dolusunu bekletmeyecek kadar geniş.
HIZ = float(AYAR.get("HGM_HIZ") or 40)     # karo/sn
KAPASITE = int(max(16, HIZ * 2))            # anlık patlama
BEKLEME_403 = 30   # ardışık 403'ten sonra o katmana bu kadar saniye gidilmez
ESIK_403 = 3       # tek bir 403 geçici olabilir, art arda 3 tanesi gerçek kapanma
YENIDEN_DENEME = 3            # 429/5xx için en çok bu kadar ek deneme
GERI_CEKME_TABAN = 0.5        # 0.5 sn -> 1 sn -> 2 sn (+ rastgele pay)
RETRY_AFTER_TAVAN = 5.0       # tarayıcı karoyu beklerken daha uzun tutmanın anlamı yok
EN_COK_YONLENDIRME = 3
UST_ZAMAN_ASIMI = 30


class Kova:
    """Token bucket: saniyede `hiz` jeton dolar, en çok `kapasite` birikir."""

    def __init__(self, hiz, kapasite):
        self.hiz, self.kapasite = hiz, kapasite
        self.jeton, self.son = float(kapasite), time.monotonic()
        self.kilit = threading.Lock()

    def al(self):
        while True:
            with self.kilit:
                simdi = time.monotonic()
                self.jeton = min(self.kapasite, self.jeton + (simdi - self.son) * self.hiz)
                self.son = simdi
                if self.jeton >= 1:
                    self.jeton -= 1
                    return
                bekle = (1 - self.jeton) / self.hiz
            time.sleep(bekle)


_kilitler = {ad: threading.Semaphore(ESZAMANLI) for ad in KATMANLAR}
_kovalar = {ad: Kova(HIZ, KAPASITE) for ad in KATMANLAR}
_kapali_bitis = {ad: 0.0 for ad in KATMANLAR}
_ardisik_403 = collections.Counter()
_durum_kilidi = threading.Lock()
_yerel = threading.local()

# Aynı karo için aynı anda gelen istekler HGM'ye tek istek olarak gitsin.
_karo_kilitleri = {}
_karo_kilitleri_kilidi = threading.Lock()


@contextlib.contextmanager
def _karo_kilidi(anahtar):
    with _karo_kilitleri_kilidi:
        kayit = _karo_kilitleri.setdefault(anahtar, [threading.Lock(), 0])
        kayit[1] += 1
    try:
        with kayit[0]:
            yield
    finally:
        with _karo_kilitleri_kilidi:
            kayit[1] -= 1
            if kayit[1] == 0:
                _karo_kilitleri.pop(anahtar, None)


def _baglanti(host):
    havuz = getattr(_yerel, "havuz", None)
    if havuz is None:
        havuz = _yerel.havuz = {}
    if host not in havuz:
        if UST_ADRES:
            havuz[host] = http.client.HTTPConnection(urlsplit(UST_ADRES).netloc, timeout=UST_ZAMAN_ASIMI)
        else:
            havuz[host] = http.client.HTTPSConnection(host, timeout=UST_ZAMAN_ASIMI)
    return havuz[host]


def _cek(host, yol):
    """Tek HTTP isteği: (durum, başlıklar, gövde). Kopmuş açık bağlantıda bir kez yeniden bağlanır."""
    for deneme in range(2):
        b = _baglanti(host)
        try:
            b.request("GET", yol, headers=BASLIK)
            r = b.getresponse()
            govde = r.read()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, govde
        except (http.client.HTTPException, OSError):
            b.close()
            _yerel.havuz.pop(host, None)
            if deneme:
                raise


def _retry_after(basliklar):
    try:
        return min(RETRY_AFTER_TAVAN, max(0.0, float(basliklar.get("retry-after", ""))))
    except ValueError:
        return None


def _cek_dayanikli(host, yol):
    """Yönlendirmeleri izler, 429/5xx'te geri çekilerek yeniden dener. (durum, gövde)."""
    yonlendirme = 0
    deneme = 0
    while True:
        durum, basliklar, govde = _cek(host, yol)
        if durum in (301, 302, 303, 307, 308):
            yonlendirme += 1
            hedef = basliklar.get("location")
            if not hedef or yonlendirme > EN_COK_YONLENDIRME:
                return 502, b"HGM yonlendirmesi izlenemedi"
            parca = urlsplit(hedef)
            if parca.netloc:
                host = parca.hostname
            yol = (parca.path or "/") + ("?" + parca.query if parca.query else "")
            continue
        if (durum == 429 or 500 <= durum <= 599) and deneme < YENIDEN_DENEME:
            bekle = _retry_after(basliklar)
            if bekle is None:
                bekle = GERI_CEKME_TABAN * (2 ** deneme) * (1 + random.random() * 0.25)
            deneme += 1
            ISTATISTIK.say("yeniden_deneme")
            time.sleep(bekle)
            continue
        return durum, govde


def _bos_gecerli(bos):
    try:
        return time.time() - bos.stat().st_mtime < BOS_TTL
    except OSError:
        return False


def karo_yolu(ad, z, x, y):
    return ONBELLEK / ad / str(z) / str(x) / f"{y}.{KATMANLAR[ad][3]}"


def kapali_kalan(ad):
    """Katman devre kesiciyle kapalıysa kalan saniye, değilse 0."""
    return max(0.0, _kapali_bitis[ad] - time.time())


def karo_getir(ad, z, x, y, yenile=False):
    """(durum, içerik). Önce disk, sonra HGM. yenile=True önbelleği atlar."""
    _, host, sablon, uzanti, _, _, _ = KATMANLAR[ad]
    dosya = karo_yolu(ad, z, x, y)
    bos = dosya.with_suffix(".bos")  # HGM'de bu karo yok, bir süre sorma
    if not yenile:
        if dosya.exists():
            ISTATISTIK.say("isabet")
            return 200, dosya.read_bytes()
        if _bos_gecerli(bos):
            ISTATISTIK.say("bos_isabet")
            return 204, b""
    if kapali_kalan(ad):
        ISTATISTIK.say("devre_kesik")
        return 503, b"HGM bu katmani gecici olarak kapatti"
    with _karo_kilidi((ad, z, x, y)):
        if not yenile and dosya.exists():  # bu arada başka istek indirmiş olabilir
            ISTATISTIK.say("isabet")
            return 200, dosya.read_bytes()
        with _kilitler[ad]:
            _kovalar[ad].al()
            ISTATISTIK.say("iskaca")
            t0 = time.time()
            durum, govde = _cek_dayanikli(host, sablon.format(z=z, x=x, y=y))
            sure = time.time() - t0
            ISTATISTIK.sure("ust_sureler", sure)
            if sure > 2:
                log("UYARI", "yavas_hgm", f"{ad} {z}/{x}/{y} {sure:.1f} sn")
        _devre_guncelle(ad, durum)
        if durum == 200 and not gecerli_govde(uzanti, govde):
            ISTATISTIK.say("gecersiz_govde")
            log("UYARI", "gecersiz_govde", f"{ad} {z}/{x}/{y}: HGM 200 dondu ama govde gecersiz "
                f"({len(govde)} bayt, bas: {govde[:16]!r}), onbellege yazilmadi")
            return 502, b"HGM gecersiz karo dondu"
        if durum == 200:
            bos.unlink(missing_ok=True)
            dosya.parent.mkdir(parents=True, exist_ok=True)
            gecici = dosya.with_name(dosya.name + f".{threading.get_ident()}.tmp")
            gecici.write_bytes(govde)
            gecici.replace(dosya)
            return 200, govde
        if durum == 404:
            bos.parent.mkdir(parents=True, exist_ok=True)
            bos.touch()
            return 204, b""
        ISTATISTIK.say("hgm_hata")
        return durum, govde


def _devre_guncelle(ad, durum):
    """Ardışık 403'leri sayar. Eşik aşılınca katmanı bir süre kapatır, 200 gelince sıfırlar."""
    with _durum_kilidi:
        if durum == 403:
            _ardisik_403[ad] += 1
            if _ardisik_403[ad] >= ESIK_403 and not kapali_kalan(ad):
                _kapali_bitis[ad] = time.time() + BEKLEME_403
                log("UYARI", "devre_kesici", f"HGM '{ad}' katmanini art arda {_ardisik_403[ad]} kez 403 ile "
                    f"reddetti, {BEKLEME_403} sn gidilmeyecek")
        elif durum == 200:
            _ardisik_403[ad] = 0


def onbellek_mb():
    """Dizin taraması pahalı (on binlerce dosya), 60 sn'de bir hesaplanır."""
    simdi = time.time()
    if simdi - onbellek_mb.zaman > 60:
        toplam = sum(f.stat().st_size for f in ONBELLEK.rglob("*") if f.is_file()) if ONBELLEK.exists() else 0
        onbellek_mb.deger, onbellek_mb.zaman = round(toplam / 1048576, 1), simdi
    return onbellek_mb.deger


onbellek_mb.deger, onbellek_mb.zaman = 0.0, 0.0


# --- HGM stilleri ----------------------------------------------------------------
# HGM sitesinin vektör kullanan iki stili, bizim adreslerimize çevrilerek verilir.
STILLER = {
    "hgm_vektor": ("HGM Vektör", "corona.json"),
    "hgm_uydu_vektor": ("HGM Uydu + vektör yazı", "hgm_uydu2.json"),
}
STIL_TTL = 86400
# corona.json içindeki "corona" katmanı salgın dönemi verisi, atlas_kara_orman ise 404 veriyor
ATILAN_KATMANLAR = {"corona"}
STIL_VARLIK = re.compile(r"^(fonts/[^/]+/\d+-\d+\.pbf|sprites/sprite(@2x)?\.(json|png))$")
VARLIK_TIPLERI = {".pbf": "application/x-protobuf", ".json": "application/json", ".png": "image/png"}


def _hgm_stil_dosyasi(yol, ttl=None):
    """atlas.harita.gov.tr/style/<yol> içeriği, diskte saklanır. (durum, gövde)"""
    uzanti = Path(yol).suffix
    dosya = ONBELLEK / "_stil" / (hashlib.sha1(yol.encode()).hexdigest() + uzanti)
    if dosya.exists() and (ttl is None or time.time() - dosya.stat().st_mtime < ttl):
        return 200, dosya.read_bytes()
    durum, govde = _cek_dayanikli("atlas.harita.gov.tr", "/style/" + yol)
    if durum == 200 and govde:
        dosya.parent.mkdir(parents=True, exist_ok=True)
        gecici = dosya.with_name(dosya.name + f".{threading.get_ident()}.tmp")
        gecici.write_bytes(govde)
        gecici.replace(dosya)
    elif dosya.exists():  # HGM'ye ulaşılamadıysa eski kopya da iş görür
        return 200, dosya.read_bytes()
    return durum, govde


def _kaynak_esle(adres):
    """HGM stilindeki bir karo adresini bizim katman adına çevirir, eşleşme yoksa None."""
    if "/CPbf/" in adres or "/api/Pbf/" in adres:
        enc = unquote(adres.split("enc=", 1)[1]) if "enc=" in adres else ""
        return ENC_KATMAN.get(enc)
    for parca, ad in (("webservis/ortofoto/", "uydu"), ("yolorta_uydu/", "yol_yazi"),
                      ("yolorta_varsayilan/", "yol_yazi_acik"), ("hgm_harita/", "hgm_harita")):
        if parca in adres:
            return ad
    return None


def _dusuk_zoom_kara_ekle(stil):
    """HGM vektör karolarında z7 altında "karalar" katmanı yok, yalnız "ulkeler" ve "adalar" var.
    HGM stilinde o düzeylerde karayı ölü atlas_kara_orman rasterı boyuyordu. Onun yerine
    ülke ve ada çokgenleri, HGM'nin z7'deki kara rengiyle boyanır."""
    kara = next((l for l in stil["layers"] if l.get("source-layer") == "karalar" and l["type"] == "fill"), None)
    if kara is None:
        return
    renk = "rgba(255, 253, 248, 1)"
    sira = next((i for i, l in enumerate(stil["layers"]) if l["type"] != "background"), 0)
    for kaynak_katman in ("ulkeler", "adalar"):
        stil["layers"].insert(sira, {
            "id": f"kara_z7_alti_{kaynak_katman}", "type": "fill", "source": kara["source"],
            "source-layer": kaynak_katman, "maxzoom": kara.get("minzoom", 7),
            "paint": {"fill-color": renk, "fill-antialias": False},
        })


def stil_uret(ad, koken):
    """HGM stilini indirir, kaynakları /t/ adreslerine, yazı tipi ve simgeleri /hgm-stil/'e çevirir."""
    gorunen, dosya_adi = STILLER[ad]
    durum, govde = _hgm_stil_dosyasi(dosya_adi, ttl=STIL_TTL)
    if durum != 200:
        return None
    stil = json.loads(govde.decode("utf-8", "replace"))
    olu = set()
    for kaynak_adi, kaynak in list(stil.get("sources", {}).items()):
        hedef = _kaynak_esle((kaynak.get("tiles") or [""])[0])
        if hedef not in KATMANLAR:
            olu.add(kaynak_adi)
            del stil["sources"][kaynak_adi]
            continue
        k = KATMANLAR[hedef]
        kaynak.pop("url", None)
        kaynak["tiles"] = [f"{koken}/t/{hedef}/{{z}}/{{x}}/{{y}}"]
        kaynak["minzoom"], kaynak["maxzoom"] = k[4], k[5]
        kaynak["attribution"] = "© Harita Genel Müdürlüğü"
    stil["layers"] = [l for l in stil.get("layers", [])
                      if l.get("source") not in olu and l.get("source-layer") not in ATILAN_KATMANLAR]
    _dusuk_zoom_kara_ekle(stil)
    stil["glyphs"] = f"{koken}/hgm-stil/fonts/{{fontstack}}/{{range}}.pbf"
    stil["sprite"] = f"{koken}/hgm-stil/sprites/sprite"
    stil["name"] = gorunen
    stil["id"] = ad
    return stil


def katman_listesi(adres):
    return [
        {"id": ad, "ad": k[0], "tur": k[6], "format": k[3], "minZoom": k[4], "maxNativeZoom": k[5],
         "url": f"http://{adres}/t/{ad}/{{z}}/{{x}}/{{y}}"}
        for ad, k in KATMANLAR.items()
    ] + [
        {"id": ad, "ad": gorunen, "tur": "stil", "url": f"http://{adres}/stil/{ad}.json"}
        for ad, (gorunen, _) in STILLER.items()
    ]


class Isleyici(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(KOK), **k)

    def log_message(self, fmt, *args):
        if not self.path.startswith("/t/"):
            log("BILGI", "istek", f"{self.address_string()} {fmt % args}")

    def gonder(self, kod, tip, govde, onbellek=False, ek_baslik=None):
        self.send_response(kod)
        self.send_header("Content-Type", tip)
        self.send_header("Content-Length", str(len(govde)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=604800" if onbellek else "no-store")
        for k, v in (ek_baslik or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(govde)

    def gonder_json(self, veri):
        govde = json.dumps(veri, ensure_ascii=False, indent=1).encode()
        return self.gonder(200, "application/json; charset=utf-8", govde)

    def statik_izinli(self, yol):
        """Proje klasöründe anahtar dosyası, log ve önbellek de duruyor. Yalnız
        sayfanın kendisi ve Leaflet dosyaları servis edilir."""
        norm = posixpath.normpath(unquote(yol))
        if norm in ("/", "/index.html", "/vektor.html"):
            return True
        return norm.startswith(("/leaflet/", "/maplibre/")) and (KOK / norm.lstrip("/")).is_file()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        adres = urlsplit(self.path)
        yol = adres.path
        if yol == "/katmanlar.json":
            return self.gonder_json(katman_listesi(self.headers.get("Host", f"localhost:{PORT}")))
        if yol == "/saglik":
            return self.gonder_json({"durum": "ayakta", "katman": len(KATMANLAR), "onbellek_mb": onbellek_mb(),
                                     "kapali_katmanlar": [ad for ad in KATMANLAR if kapali_kalan(ad)]})
        if yol == "/istatistik":
            return self.gonder_json(ISTATISTIK.ozet())
        if yol.startswith("/t/"):
            return self.karo_yanitla(yol, adres.query)
        if yol.startswith("/stil/") and yol.endswith(".json"):
            ad = yol[len("/stil/"):-len(".json")]
            if ad not in STILLER:
                return self.gonder(404, "text/plain", b"bilinmeyen stil")
            try:
                stil = stil_uret(ad, f"http://{self.headers.get('Host', f'localhost:{PORT}')}")
            except Exception as e:
                log("HATA", "stil", f"{ad}: {type(e).__name__}")
                stil = None
            if stil is None:
                return self.gonder(502, "text/plain", b"HGM stil dosyasi alinamadi")
            return self.gonder_json(stil)
        if yol.startswith("/hgm-stil/"):
            return self.stil_varligi(yol[len("/hgm-stil/"):])
        if not self.statik_izinli(yol):
            return self.gonder(404, "text/plain", b"bulunamadi")
        if self.command == "HEAD":
            return super().do_HEAD()
        return super().do_GET()

    def stil_varligi(self, yol):
        """HGM'nin yazı tipi ve simge dosyaları. Yalnız bu iki tür, başka bir dosya değil."""
        if not STIL_VARLIK.match(yol):
            return self.gonder(404, "text/plain", b"bulunamadi")
        try:
            durum, govde = _hgm_stil_dosyasi(yol)
        except Exception as e:
            durum, govde = 502, type(e).__name__.encode()
        if durum != 200:
            return self.gonder(502 if durum != 404 else 404, "text/plain", f"HGM {durum}".encode())
        return self.gonder(200, VARLIK_TIPLERI[Path(yol).suffix], govde, onbellek=True)

    def karo_yanitla(self, yol, sorgu):
        parca = yol[3:].split("/")
        if len(parca) != 4 or parca[0] not in KATMANLAR:
            return self.gonder(404, "text/plain", b"bilinmeyen katman")
        try:
            z, x, y = int(parca[1]), int(parca[2]), int(parca[3].split(".")[0])
        except ValueError:
            return self.gonder(400, "text/plain", b"z/x/y sayi olmali")
        if not gecerli_koordinat(z, x, y):
            return self.gonder(400, "text/plain", b"z/x/y aralik disinda")
        ad = parca[0]
        yenile = parse_qs(sorgu).get("yenile") == ["1"]
        t0 = time.time()
        try:
            durum, govde = karo_getir(ad, z, x, y, yenile=yenile)
        except Exception as e:
            ISTATISTIK.say("hgm_ulasilamadi")
            durum, govde = 502, f"HGM'ye ulasilamadi: {type(e).__name__}".encode()
        sure = time.time() - t0
        ISTATISTIK.sure("yanit_sureler", sure)
        if durum not in (200, 204):
            log("HATA", "karo", f"{ad} {z}/{x}/{y} durum={durum} {govde[:80]!r}")
        if sure > 1:
            log("UYARI", "yavas", f"{ad} {z}/{x}/{y} durum={durum} {sure:.1f} sn")
        if durum == 200:
            return self.gonder(200, TIPLER[KATMANLAR[ad][3]], govde, onbellek=True)
        if durum == 204:  # karo yok: boş karo, hata değil
            if KATMANLAR[ad][3] == "pbf":
                return self.gonder(200, TIPLER["pbf"], b"", onbellek=True)
            return self.gonder(200, "image/png", BOS_PNG, onbellek=True)
        if durum == 503:
            kalan = max(1, int(kapali_kalan(ad) + 0.999))
            return self.gonder(503, "text/plain", govde, ek_baslik={"Retry-After": str(kalan)})
        # HGM'nin kendi hatası (403, 429, 5xx, yönlendirme sorunu) bizim için ağ geçidi hatası
        return self.gonder(502, "text/plain", f"HGM {durum}: ".encode() + govde[:200])


class Sunucu(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    # Windows'ta SO_REUSEADDR ikinci bir sürecin aynı portu sessizce almasına izin
    # veriyor (ölçüldü), istekler iki süreç arasında dağılıyordu. Orada özel kullanım istenir.
    allow_reuse_address = os.name != "nt"
    # Varsayılan bekleme kuyruğu 5. Tarayıcı aynı anda 12+ bağlantı açınca
    # Windows fazlasını reddediyordu (ERR_CONNECTION_REFUSED, karolar boş kalıyordu).
    request_queue_size = 128

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address):
        pass  # tarayıcının iptal ettiği karo istekleri olağan


class Sunucu6(Sunucu):
    address_family = socket.AF_INET6


def baslat(port=None, ipv6=True):
    """Sunucuyu kurar, port doluysa OSError fırlatır. (ipv4_sunucu, ipv6_sunucu|None)"""
    port = PORT if port is None else port
    s4 = Sunucu(("127.0.0.1", port), Isleyici)
    s6 = None
    if ipv6:
        # "localhost" önce IPv6 (::1) dener. Yalnız IPv4 dinlenirse her istek ~200 ms bekler.
        try:
            s6 = Sunucu6(("::1", s4.server_address[1]), Isleyici)
        except OSError:
            s6 = None
    return s4, s6


if __name__ == "__main__":
    if EKSIK_AYARLAR:
        print("HATA: su ayarlar eksik: " + ", ".join(EKSIK_AYARLAR), file=sys.stderr)
        print(f"  {AYAR_DOSYASI.name} dosyasina ANAHTAR=deger olarak yazin "
              f"(ornek: {AYAR_DOSYASI.name}.ornek) ya da ortam degiskeni olarak verin.", file=sys.stderr)
        sys.exit(2)
    try:
        s4, s6 = baslat()
    except OSError:
        print(f"HATA: Port {PORT} zaten kullanimda. Calisan sunucuyu kapatin ya da ayar.env "
              f"icinde PORT degistirin.", file=sys.stderr)
        sys.exit(1)
    if s6:
        threading.Thread(target=s6.serve_forever, daemon=True).start()
    log("BILGI", "basladi", f"harita http://localhost:{PORT}  katmanlar /katmanlar.json  "
        f"eszamanli={ESZAMANLI} hiz={HIZ:g}/sn")
    with s4:
        s4.serve_forever()
