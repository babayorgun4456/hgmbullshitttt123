# HGM Harita: yerel karo sunucusu, harita sayfaları ve uydu indirici

Harita Genel Müdürlüğü'nün (HGM) [atlas.harita.gov.tr](https://atlas.harita.gov.tr) haritalarını
başka bir harita altyapısında kullanmak için küçük bir araç seti:

- **`sunucu.py`**: HGM'nin bütün çalışan katmanlarını tek biçimli adreslerden veren yerel karo sunucusu.
  Anahtarları ve zorunlu başlıkları kendisi ekler, karoları diskte saklar.
- **`index.html`**: raster katmanlar için Leaflet haritası.
- **`vektor.html`**: HGM vektör verisi ve meteoroloji istasyonları için MapLibre haritası.
- **`uydu_indir.py`**: bir alanın HGM uydu görüntüsünü mozaik PNG olarak indiren komut satırı aracı.

Yalnız Python standart kütüphanesi kullanılır. Uydu indirici ek olarak Pillow ister.
Leaflet 1.9.4 ve MapLibre GL 5.24.1 klasörde yerel kopya olarak durur, internetten yüklenmez.

---

## İçindekiler

1. [Hızlı başlangıç](#1-hızlı-başlangıç)
2. [Klasör yapısı](#2-klasör-yapısı)
3. [Anahtarlar ve ayarlar](#3-anahtarlar-ve-ayarlar)
4. [Katmanlar](#4-katmanlar)
5. [Başka bir haritaya eklemek](#5-başka-bir-haritaya-eklemek)
6. [Sunucunun bütün adresleri](#6-sunucunun-bütün-adresleri)
7. [Uydu indirici](#7-uydu-indirici)
8. [Sunucu nasıl çalışıyor](#8-sunucu-nasıl-çalışıyor)
9. [Testler](#9-testler)
10. [Bilinen sınırlar](#10-bilinen-sınırlar)

---

## 1. Hızlı başlangıç

Gereken: Python 3.9 veya üstü. Uydu indirici için ayrıca `pip install pillow`.

```
cd hgm-harita
python sunucu.py
```

Sonra tarayıcıda:

| Adres | Ne açılır |
|---|---|
| http://localhost:8833 | Raster harita (10 altlık, 2 şeffaf üst katman) |
| http://localhost:8833/vektor.html | Vektör harita (HGM stilleri, katman aç/kapa, meteoroloji) |
| http://localhost:8833/katmanlar.json | Bütün katmanların listesi ve adresleri |
| http://localhost:8833/saglik | Sunucu ayakta mı |

Sunucu yalnız bu bilgisayardan erişilebilir (`127.0.0.1` ve `::1`). Durdurmak için konsolda Ctrl+C.
Aynı port ikinci kez açılamaz. İkinci kez `python sunucu.py` derseniz "Port 8833 zaten kullanımda" yazıp çıkar.

---

## 2. Klasör yapısı

| Yol | İçerik |
|---|---|
| `sunucu.py` | Karo sunucusu |
| `uydu_indir.py` | Uydu mozaik indirici |
| `ayar.env` | HGM anahtarları ve ayarlar (iki araç da okur) |
| `index.html` | Leaflet raster haritası |
| `vektor.html` | MapLibre vektör haritası |
| `leaflet/`, `maplibre/` | Kütüphanelerin yerel kopyaları |
| `tests/` | Testler (HGM'ye istek atmaz) |
| `docs/kure-analiz/` | HGM KÜRE masaüstü uygulaması ve 116 katmanlı WMS servisi üzerine inceleme notları |
| `onbellek/` | Karo önbelleği. Sunucu çalıştıkça dolar, git'e eklenmez |

---

## 3. Anahtarlar ve ayarlar

Bütün anahtarlar `ayar.env` dosyasında. Hepsi HGM'nin herkese açık `config.js` ve `style/*.json`
dosyalarında geçiyor. Ortam değişkeni verilirse dosyadakinin yerine o kullanılır.

| # | Ayar | Değer | Ne açıyor | Durum (24.11.2026) |
|---|---|---|---|---|
| 1 | `HGM_API_KEY` | `MEZEVy8rQXZlV0NBK3pzbWlEb0tmQT09` | `atlasapitest.harita.gov.tr/Layers/{Base,Siyasi,Gece,Topografik}` | Çalışıyor |
| 2 | `HGM_WS_KEY` | `rXKdDZxXgj2hgFspEC4BKG4HMittQ0Y6` | `atlas.harita.gov.tr/webservis/` ortofoto, raster haritalar, yol katmanları | Çalışıyor, Referer şart |
| 3 | `HGM_HARITA_KEY` | `g0mWEt2oJlJIn82U9Ab70dn1gXuHZHre` | `webservis/harita/hgm_harita` | Çalışıyor, Referer şart |
| 4 | `HGM_VEKTOR_ENC` | `eO5x/wDfI6MHinhGp2x0W4myARmP+hvpaww9g9CLUI8=` | `atlas1.harita.gov.tr/CPbf` vektör: sınır, yol, yerleşim, göl, orman | Çalışıyor |
| 5 | `HGM_ETIKET_ENC` | `cpkSHipmtpCzOFRx5kmnLGHHaFydusJMyBWgMkNyZCU=` | `CPbf` vektör: yer adları | Çalışıyor |
| 6 | `HGM_ETIKET_UYDU_ENC` | `cpkSHipmtpCzOFRx5kmnLIkl89oUJdACy7xHVeebgZw=` | `CPbf` vektör: yer adları, uydu stili sürümü | Çalışıyor |
| 7 | `HGM_METEO_ENC` | `DsTX5MTbGW7dp1PyxvvB8pn1dEqfV+bYTU2P2MQb/nrgUQmm6OMBy69ZcTdQVo4JjJd9jUKdk3zocn5ZfZRwhaHauH67Tzd1rsvsMqn5M2JDWv3ye3Y//yMtb4xbVP/0` | `atlas.harita.gov.tr/api/Pbf` meteoroloji istasyonları | Çalışıyor |
| 8 | (kullanılmıyor) | `f98122c0428560ea210c116bc344c99c` | `css.harita.gov.tr/mobil-gorsun/wms` | **401**, geçersiz kimlik |

Diğer ayarlar:

| Ayar | Varsayılan | Anlamı |
|---|---|---|
| `PORT` | 8833 | Sunucunun portu |
| `HGM_ESZAMANLI` | 12 | Katman başına HGM'ye aynı anda en çok kaç istek |
| `HGM_HIZ` | 40 | Katman başına saniyede en çok kaç karo (anlık 80) |
| `HGM_UST_ADRES` | boş | Yalnız testler için, bütün HGM isteklerini başka adrese yönlendirir |

İlk üç anahtardan biri eksikse sunucu açılmaz ve hangisinin eksik olduğunu yazar.
Vektör anahtarlarından biri eksikse yalnız o vektör katmanı listeden düşer.

---

## 4. Katmanlar

Bütün katmanlar aynı adres biçimiyle verilir:

```
http://localhost:8833/t/<katman>/{z}/{x}/{y}
```

### Raster altlıklar

| Katman | Ad | En yüksek zoom | Kaynak |
|---|---|---|---|
| `temel` | Temel | 19 | atlasapitest Base |
| `siyasi` | Siyasi | 15 | atlasapitest Siyasi (z15 üstü boş) |
| `gece` | Gece | 19 | atlasapitest Gece |
| `topografik` | Topografik | 19 | atlasapitest Topografik |
| `uydu` | Uydu (yazısız) | 19 | webservis/ortofoto |
| `fiziki_raster` | Fiziki (Raster) | 9 | webservis/hgmrasterhrt/fiziki |
| `siyasi_raster` | Siyasi (Raster) | 9 | webservis/hgmrasterhrt/mülki_idari |
| `topografik_raster` | Topografik (Raster) | 13 | webservis/hgmrasterhrt/topografik (yalnız Türkiye) |
| `hgm_harita` | HGM Harita | 16 | webservis/harita/hgm_harita |

### Şeffaf üst katmanlar

| Katman | Ad | Zoom |
|---|---|---|
| `yol_yazi` | Yol ve yer adları, uydunun üstüne | 6-19 |
| `yol_yazi_acik` | Yol ve yer adları, açık renkli zeminin üstüne | 6-20 |

### Vektör katmanlar (Mapbox Vector Tile)

| Katman | İçindeki katmanlar | Zoom |
|---|---|---|
| `hgm_vektor` | karalar, ülkeler, adalar, denizler, göller, iso_bath, sounding, orman_alan_250k, sinir_cizgileri, karayolu, yolorta_yurtdisi, yerlesim, noktalar, onemli_noktalar, donati_alan, donati_font_point, plate_cizgi, plate_nokta | 0-21 |
| `hgm_etiket` | label3 (yer adları), cad_2021 (cadde adları) | 0-21 |
| `hgm_etiket_uydu` | hgm_etiket ile aynı, HGM uydu stilinin sürümü | 0-21 |
| `meteoroloji` | meteoroloji: istad, sicaklik, aciklama, ruzgarhiz, ruzgaryon, yagis, aktuelbasinc, verizamani, ilce, ilplaka... | 5-14 |

### HGM'nin kendi stilleri

Adresleri bu sunucuya çevrilmiş, MapLibre'ye doğrudan verilebilir:

| Adres | İçerik |
|---|---|
| `/stil/hgm_vektor.json` | HGM Vektör haritası (HGM'deki corona.json; ölü kaynakları çıkarılmış, z7 altına kara rengi eklenmiş) |
| `/stil/hgm_uydu_vektor.json` | Uydu görüntüsü + vektör yer adları (HGM'deki hgm_uydu2.json) |

Stillerin yazı tipleri ve simgeleri `/hgm-stil/fonts/...` ve `/hgm-stil/sprites/...` adresinden gelir.

---

## 5. Başka bir haritaya eklemek

En yüksek zoom'un üstünde karo istemeyin. Altyapının "büyüt" ayarını kullanın
(Leaflet'te `maxNativeZoom`, MapLibre'de kaynağın `maxzoom` değeri).

**Leaflet**
```js
L.tileLayer("http://localhost:8833/t/topografik/{z}/{x}/{y}", { maxNativeZoom: 19, maxZoom: 19 }).addTo(map);
L.tileLayer("http://localhost:8833/t/fiziki_raster/{z}/{x}/{y}", { minNativeZoom: 1, maxNativeZoom: 9 }).addTo(map);
```

**OpenLayers**
```js
new ol.layer.Tile({ source: new ol.source.XYZ({ url: "http://localhost:8833/t/uydu/{z}/{x}/{y}", maxZoom: 19 }) });
```

**MapLibre, raster katman**
```js
map.addSource("hgm", { type: "raster", tiles: ["http://localhost:8833/t/temel/{z}/{x}/{y}"], tileSize: 256, maxzoom: 19 });
map.addLayer({ id: "hgm", type: "raster", source: "hgm" });
```

**MapLibre, HGM'nin bütün vektör haritası**
```js
new maplibregl.Map({ container: "harita", style: "http://localhost:8833/stil/hgm_vektor.json" });
```

**MapLibre, vektör veriyi kendi stilinizle**
```js
map.addSource("hgm", { type: "vector", tiles: ["http://localhost:8833/t/hgm_vektor/{z}/{x}/{y}"], maxzoom: 21 });
map.addLayer({ id: "sinirlar", type: "line", source: "hgm", "source-layer": "sinir_cizgileri",
               paint: { "line-color": "#c00", "line-width": 1.5 } });
```

**QGIS**: Tarayıcı paneli > XYZ Tiles > Yeni bağlantı > adres `http://localhost:8833/t/uydu/{z}/{x}/{y}`,
en yüksek zoom 19. Vektör katmanlar için "Vector Tiles" > Yeni genel bağlantı, aynı adres biçimi.

Katman listesini programla okumak için `/katmanlar.json`: her katmanın `id`, `ad`, `tur`
(`altlik`, `ust`, `vektor`, `stil`), `format`, `minZoom`, `maxNativeZoom` ve `url` alanı var.

---

## 6. Sunucunun bütün adresleri

| Adres | Yanıt |
|---|---|
| `GET /t/<katman>/{z}/{x}/{y}` | Karo (png, jpg ya da pbf) |
| `GET /t/...?yenile=1` | Önbelleği atlayıp karoyu HGM'den yeniden alır |
| `HEAD /t/...` | Aynı durum ve başlıklar, gövdesiz |
| `GET /katmanlar.json` | Katman listesi |
| `GET /stil/<ad>.json` | HGM stili, adresleri yerele çevrilmiş |
| `GET /hgm-stil/fonts/...`, `/hgm-stil/sprites/...` | Stillerin yazı tipi ve simgeleri |
| `GET /saglik` | `{"durum":"ayakta","katman":15,"onbellek_mb":...,"kapali_katmanlar":[]}` |
| `GET /istatistik` | Önbellek isabet/ıska, HGM hata ve yeniden deneme sayıları, gecikme p50/p95 |
| `GET /`, `/index.html`, `/vektor.html`, `/leaflet/*`, `/maplibre/*` | Sayfalar |

Başka her dosya (anahtarlar, log, önbellek, kod) 404 döner.

Karo yanıtları:

| Durum | Anlamı |
|---|---|
| 200 | Karo |
| 200, boş karo | HGM'de o karo yok (ör. Topografik Raster Türkiye dışında). Raster için 1×1 şeffaf PNG, vektör için boş gövde. 30 gün HGM'ye tekrar sorulmaz |
| 400 | z/x/y sayı değil ya da aralık dışında (0 ≤ z ≤ 22, 0 ≤ x, y < 2^z) |
| 404 | Bilinmeyen katman |
| 502 | HGM'ye ulaşılamadı, HGM hata verdi ya da bozuk karo döndü (önbelleğe yazılmaz) |
| 503 + `Retry-After` | HGM bu katmanı art arda 3 kez 403 ile reddetti, sunucu 30 sn o katmana gitmiyor |

---

## 7. Uydu indirici

Bir alanın HGM uydu görüntüsünü indirip tek parça PNG yapar. Yanına aynı adla `.json`
(alan, zoom, karo sayısı, ölçümler) ve `.pgw` (world file) yazar.

```
python uydu_indir.py --bbox 32.830,39.920,32.845,39.932 --zoom 17
python uydu_indir.py --bbox 32.830,39.920,32.845,39.932 --otomatik-zoom --cikti anitkabir.png
python uydu_indir.py --bbox 26.9,36.4,27.1,36.6 --zoom 13 --zorla
python uydu_indir.py --bbox 32.80,39.90,32.90,39.95 --zoom 15 --katman hgm_harita
```

`--bbox` sırası: **batı,güney,doğu,kuzey** (boylam önce). Bir noktanın çevresi için,
enlemi `E` boylamı `B` olan nokta için yaklaşık 1 km: `B-0.006,E-0.005,B+0.006,E+0.005`.

| Bayrak | Varsayılan | Ne yapar |
|---|---|---|
| `--zoom` | 17 | Sabit zoom |
| `--katman` | uydu | `uydu`, `hgm_harita` ya da `topografik` |
| `--cikti` | uydu_z<zoom>_<tarih>.png | Çıktı dosyası |
| `--otomatik-zoom` | kapalı | HGM'nin o bölgedeki gerçek ayrıntısının bittiği zoom'u ölçüp seçer, `--zoom` yok sayılır |
| `--esik` | 10.0 | z→z+1 farkı bu değerin üstündeyse z+1 gerçek ayrıntı sayılır |
| `--olcum-nokta` | 3 (en çok 5) | Ölçüm noktası sayısı: merkez ve köşelere yakın |
| `--en-az-zoom` | 12 | Ölçümün başladığı zoom |
| `--olcum-butcesi` | 30 | Ölçüm için en çok kaç karo indirilir |
| `--kapsama-nokta` | 9 | Boş/deniz oranı için 3×3 örnek |
| `--bos-esik` | 0.6 | Boş oranı bunun üstündeyse `--zorla` olmadan indirilmez (çıkış kodu 2) |
| `--zorla` | kapalı | Çoğu deniz/boş olsa da indir |
| `--saydam-bos` / `--no-saydam-bos` | açık | Boş karolar mozaikte saydam kalır (o zaman PNG RGBA olur) |
| `--en-cok-hata-orani` | 0.2 | Bundan fazla karo inmezse iş iptal, azsa eksiklerle devam |
| `--en-cok-karo` | 400 | Aşılırsa indirme başlamaz |
| `--eszamanli` | 4 | En çok 4. Ayrıca her istek arasında 0,1 sn beklenir |

Çıkış kodları: `0` tamam, `1` hata (çok fazla karo, çok fazla indirme hatası...), `2` bölge çoğunlukla boş/deniz.

### Otomatik zoom nasıl seçiyor

HGM bazı bölgelerde yüksek zoom'da gerçek görüntü vermiyor, alt seviyeyi büyütüyor.
Her ölçüm noktasında z karosunun noktayı içeren çeyreği ile aynı yerin z+1 karosu
(yarıya küçültülmüş) karşılaştırılır. Fark büyükse z+1 yeni ayrıntı getiriyor, küçükse
yalnız büyütme. 12'den 19'a bütün geçişler ölçülür, farkı eşiğin üstünde kalan **en yüksek**
seviye seçilir. Sonra karo sınırı aşılıyorsa zoom düşürülür. `.json` içinde
`otomatik_zoom.olculen` ölçümün bulduğu, `secilen` indirilen zoom'dur.

Ölçüm örnekleri (24.11.2026):

| Yer | Seçilen | Not |
|---|---|---|
| Ankara, Anıtkabir | z17 | z16→17 farkı 10,2, z17→18 5,5 |
| Ermenistan (43.85,40.55,43.95,40.65) | ölçülen z18, indirilen z15 | z17→18 farkı 14,7, z18→19 0,7. z16-18 400 karoyu aşıyor |
| Hakkari, Irak sınırı | z12 | bütün farklar 5-8 |
| Berbera, Somali | z12 | z13'ten sonra fark 4'ün altında |
| Halkis, Yunanistan | z12 | z13'ten sonra fark 2'nin altında |

### Boş karo

Deniz ve veri olmayan yerlerde HGM düz gri karo döner. Gri ton standart sapması 3,5'in
altındaysa ya da karo 2200 bayttan küçük ve sapması 10'un altındaysa boş sayılır. Bu ölçüt
yalnız `uydu` katmanında kullanılır.

---

## 8. Sunucu nasıl çalışıyor

- **Neden aracı sunucu:** `atlas.harita.gov.tr/webservis/...` adresleri istek
  `Referer: https://atlas.harita.gov.tr/` taşımıyorsa 403 "Invalid referer" veriyor ve tarayıcı bu
  başlığı değiştiremez. Sunucu başlığı ve anahtarı kendisi ekler, istemciye anahtar gitmez.
- **Önbellek:** karolar `onbellek/<katman>/z/x/y.<uzantı>` olarak yazılır, aynı karo HGM'den bir daha
  istenmez. HGM'den gelen gövde doğrulanır (PNG/JPEG imzası, vektörde protobuf başı). Bozuk gövde yazılmaz.
- **Boş karo kaydı:** HGM 404 derse `.bos` dosyası yazılır, 30 gün o karo HGM'ye sorulmaz.
- **Hız:** katman başına 12 eşzamanlı istek ve saniyede 40 karo. Ölçüm: 48 yeni karo 12 eşzamanlıyla
  1,2 sn, 2 eşzamanlıyla 4,3 sn. Hiçbirinde HGM 403 vermedi. Aynı karoya aynı anda gelen istekler HGM'ye
  tek istek olarak gider.
- **Hatalar:** 429 ve 5xx yanıtlarında 3 kez daha denenir (0,5 / 1 / 2 sn, `Retry-After` varsa ona
  uyulur, en çok 5 sn). Yönlendirmeler en çok 3 kez izlenir. Bir katmanda art arda 3 kez 403 gelirse o
  katmana 30 sn gidilmez, 200 gelince sayaç sıfırlanır.
- **Log:** her satır `zaman | seviye | olay | ayrıntı`. 1 sn'den uzun karo istekleri ve hatalar yazılır.

---

## 9. Testler

```
python -m pip install pytest pillow
python -m pytest -q
```

Testler yerel sahte bir HGM sunucusu ve sahte karolar kullanır, gerçek HGM'ye hiç istek atmaz
(sunucu testlerinde HTTPS bağlantısı tamamen engellidir).

---

## 10. Bilinen sınırlar

- **Meteoroloji verisi canlı değil.** 24.11.2026 17:00 civarında istasyonların veri zamanı 08:59 idi.
  HGM'nin ne sıklıkla güncellediği bilinmiyor.
- **Düşük zoom vektör karoları büyük.** Türkiye ölçeğinde tek karo 1-2 MB. İlk açılış 1-2 sn sürebilir,
  sonra önbellekten gelir.
- **`.pgw` dosyası** piksel boyutunu derece olarak yazıyor ve enlem için de aynı değeri kullanıyor.
  Görüntü Web Mercator olduğu için QGIS'te dikeyde uzar (Ankara'da yaklaşık %30). Eski araçla aynı kalsın
  diye değiştirilmedi.
- **HGM tarafı değişebilir.** Anahtarlar, adresler ve zoom sınırları HGM'nin sitesinden alındı. HGM bunları
  değiştirirse `ayar.env` ve `sunucu.py` içindeki `KATMANLAR` tablosu güncellenmeli.
- HGM verisi telifli. Kişisel ve yerel kullanım için. Toplu indirmeyi sınırlı tutun, herkese açık yayınlamayın.
