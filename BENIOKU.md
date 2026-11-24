# HGM karoları: yerel karo sunucusu + Leaflet örneği

## Kurulum ve çalıştırma

1. `ayar.env.ornek` dosyasını `ayar.env` adıyla kopyalayın ve anahtarları doldurun.
   Anahtarlar ortam değişkeni olarak da verilebilir (`HGM_API_KEY`, `HGM_WS_KEY`, `HGM_HARITA_KEY`, `PORT`).
   Eksik anahtar varsa sunucu hangisinin eksik olduğunu yazıp çıkar.
2. Çalıştırın:

```
cd "C:\Users\user\Desktop\hgm-harita"
python sunucu.py
```

Örnek harita: http://localhost:8833
Katman listesi (JSON): http://localhost:8833/katmanlar.json

Yalnız standart Python kütüphanesi kullanılır, kurulum gerekmez.

## Başka bir harita altyapısına eklemek

Her katman düz bir XYZ karo adresi. HGM anahtarları ve Referer başlığı sunucuda kalır.

```
http://localhost:8833/t/<katman>/{z}/{x}/{y}
```

| katman | ad | HGM'nin verdiği en yüksek zoom |
|---|---|---|
| temel | Temel | 19 |
| siyasi | Siyasi | 15 |
| gece | Gece | 19 |
| topografik | Topografik | 19 |
| uydu | Uydu (yazısız) | 19 |
| yol_yazi | Yol ve yer adları, şeffaf, uydunun üstüne | 19 (z6'dan başlar) |
| fiziki_raster | Fiziki (Raster) | 9 |
| siyasi_raster | Siyasi (Raster) | 9 |
| topografik_raster | Topografik (Raster) | 13 (yalnız Türkiye) |
| hgm_harita | HGM Harita | 16 |

En yüksek zoom'un üstünde karo istemeyin, altyapının büyütme ayarını kullanın.

Leaflet:
```js
L.tileLayer("http://localhost:8833/t/topografik/{z}/{x}/{y}", { maxNativeZoom: 19, maxZoom: 19 }).addTo(map);
```

OpenLayers:
```js
new ol.layer.Tile({ source: new ol.source.XYZ({ url: "http://localhost:8833/t/uydu/{z}/{x}/{y}", maxZoom: 19 }) });
```

MapLibre:
```js
map.addSource("hgm", { type: "raster", tiles: ["http://localhost:8833/t/temel/{z}/{x}/{y}"], tileSize: 256, maxzoom: 19 });
```

QGIS: XYZ Tiles > Yeni bağlantı > aynı adres.

## Yanıtlar

| Durum | Anlamı |
|---|---|
| 200 PNG/JPEG | Karo (önbellekten ya da HGM'den) |
| 200, 1x1 şeffaf PNG | HGM'de bu karo yok (ör. Topografik Raster Türkiye dışı). 30 gün HGM'ye tekrar sorulmaz |
| 400 | z/x/y sayı değil ya da aralık dışında (0 ≤ z ≤ 22, 0 ≤ x, y < 2^z) |
| 404 | Bilinmeyen katman ya da izinli olmayan dosya |
| 502 | HGM'ye ulaşılamadı, HGM hata verdi (yeniden denemelerden sonra) ya da bozuk karo döndü (önbelleğe yazılmaz) |
| 503 + `Retry-After` | HGM bu katmanı art arda 3 kez 403 ile reddetti, sunucu 30 sn o katmana gitmiyor |

`?yenile=1` eklenirse önbellek ve "karo yok" kaydı atlanır, karo HGM'den yeniden alınır.
`HEAD` istekleri `GET` ile aynı durum kodunu ve başlıkları gövdesiz döner (karo önbellekte yoksa HGM'den alınır).
`OPTIONS` 204 ve CORS başlıkları döner.

Durum uçları:
- `GET /saglik`: ayakta mı, katman sayısı, önbellek boyutu, kapalı katmanlar
- `GET /istatistik`: önbellek isabet/ıska, HGM hata ve yeniden deneme sayıları, HGM ve yanıt gecikmesi (p50/p95)

## Neden vekil

- `atlas.harita.gov.tr/webservis/...` (uydu, raster katmanlar, HGM Harita, yol/yazı) Referer
  `https://atlas.harita.gov.tr/` değilse 403 "Invalid referer" veriyor. Tarayıcı bu başlığı değiştiremez.
  `atlasapitest.harita.gov.tr/Layers/...` (Temel, Siyasi, Gece, Topografik) Referer istemiyor, CORS açık.
- Bütün katmanlar tek biçimli bir adresten verilir, anahtarlar istemciye gitmez.
- Karolar `onbellek/<katman>/z/x/y` altına yazılır. Bakılan yer bir daha HGM'den istenmez.
- HGM zaman zaman bir katmanı birkaç dakika 403 ile kapatıyor. Herhangi bir katmanda art arda
  3 kez 403 gelince sunucu o katmana 30 sn hiç gitmez (`ESIK_403`, `BEKLEME_403`). 200 gelince sayaç sıfırlanır.
- 429 ve 5xx yanıtlarında 3 kez daha denenir (0,5 / 1 / 2 sn, `Retry-After` varsa ona uyulur, en çok 5 sn).
  Yönlendirmeler en çok 3 kez izlenir.

## Sınırlar (koddaki değerler)

- HGM'ye katman başına en çok 12 eşzamanlı istek (`HGM_ESZAMANLI`) ve saniyede 40 karo (`HGM_HIZ`,
  token bucket, anlık 80). İkisi de `ayar.env` ile değiştirilebilir.
  Ölçüm (24.11.2026, 48 soğuk karo): 2 eşzamanlı + 8/sn ile 4,3 sn, 4 ile 2,7 sn, 12 ile 1,2 sn. Hiç 403 olmadı.
- Aynı karoya aynı anda gelen istekler HGM'ye tek istek olarak gider.
- Sunucu yalnız `127.0.0.1` ve `::1` adreslerini dinler, ağdaki başka makinelere açık değildir.
- HTTP üzerinden yalnız `/`, `/index.html`, `/leaflet/*`, `/katmanlar.json` ve `/t/*` servis edilir.
  Proje klasöründeki diğer dosyalar (anahtarlar, log, önbellek) 404 döner.
- Aynı port ikinci kez açılamaz, ikinci `python sunucu.py` "Port 8833 zaten kullanımda" deyip çıkar.

## Testler

```
python -m pytest -q
```

Testler yerel sahte bir HGM sunucusu kullanır, gerçek HGM'ye hiç istek atmaz.
