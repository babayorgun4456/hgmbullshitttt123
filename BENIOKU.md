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
| 502 | HGM'ye ulaşılamadı ya da HGM bozuk karo döndü (önbelleğe yazılmaz) |
| 503 | HGM bu katmanı 403 ile kapattı, sunucu 30 sn o katmana gitmiyor |

`?yenile=1` eklenirse önbellek ve "karo yok" kaydı atlanır, karo HGM'den yeniden alınır.
`HEAD` istekleri `GET` ile aynı durum kodunu ve başlıkları gövdesiz döner.

## Neden vekil

- `atlas.harita.gov.tr/webservis/...` (uydu, raster katmanlar, HGM Harita, yol/yazı) Referer
  `https://atlas.harita.gov.tr/` değilse 403 "Invalid referer" veriyor. Tarayıcı bu başlığı değiştiremez.
  `atlasapitest.harita.gov.tr/Layers/...` (Temel, Siyasi, Gece, Topografik) Referer istemiyor, CORS açık.
- Bütün katmanlar tek biçimli bir adresten verilir, anahtarlar istemciye gitmez.
- Karolar `onbellek/<katman>/z/x/y` altına yazılır. Bakılan yer bir daha HGM'den istenmez.
- HGM zaman zaman bir katmanı birkaç dakika 403 ile kapatıyor. `atlasapitest` katmanlarında
  403 gelince sunucu o katmana 30 sn hiç gitmez (`BEKLEME_403`).

## Sınırlar (koddaki değerler)

- HGM'ye katman başına en çok 12 eşzamanlı istek (`ESZAMANLI = 12`). Ayrıca hız sınırı yok.
  Ölçüm (24.11.2026): 16 eşzamanlı istekle 300 karo 5 sn içinde geldi, hiç 403 olmadı.
- Sunucu yalnız `127.0.0.1` ve `::1` adreslerini dinler, ağdaki başka makinelere açık değildir.
- HTTP üzerinden yalnız `/`, `/index.html`, `/leaflet/*`, `/katmanlar.json` ve `/t/*` servis edilir.
  Proje klasöründeki diğer dosyalar (anahtarlar, log, önbellek) 404 döner.
