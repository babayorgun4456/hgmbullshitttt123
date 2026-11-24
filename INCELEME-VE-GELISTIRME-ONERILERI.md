# HGM Harita — Kapsamlı İnceleme ve Geliştirme Önerileri

**İnceleme tarihi:** 24 Kasım 2026
**Kapsam:** `hgm-harita` (yerel karo vekili + Leaflet istemcisi), HGM Atlas servisleri, [morluto/rea](https://github.com/morluto/rea) aracının bu proje için değerlendirilmesi
**Yöntem:** kaynak kodu okuması, çalışan sunucu üzerinde canlı testler, HGM'nin web uygulamasının statik analizi (bundle → config → stil dosyaları → karo uç noktaları), **REA 6.10.1'in taşınabilir Node 26.13.1 ile kurulup HGM'ye karşı çalıştırılması** (Chrome 158 + CDP: 137 istek ağ gözlemi, bundle analizi)

> Bu belgedeki her sayısal iddia bu oturumda ölçülmüştür. Ölçümler tek seferliktir; HGM tarafındaki değerler gün içinde değişebilir. Doğrulanamayan noktalar açıkça "varsayım" olarak işaretlenmiştir.

---

## İçindekiler

1. [Yönetici özeti](#1-yönetici-özeti)
2. [Projenin bugünkü durumu](#2-projenin-bugünkü-durumu)
3. [HGM tarafı: gerçekte ne sunuluyor](#3-hgm-tarafı-gerçekte-ne-sunuluyor)
4. [Bulgular: hatalar, riskler, tutarsızlıklar](#4-bulgular-hatalar-riskler-tutarsızlıklar)
5. [Geliştirme önerileri ve yol haritası](#5-geliştirme-önerileri-ve-yol-haritası)
6. [Uygulanabilir kod örnekleri](#6-uygulanabilir-kod-örnekleri)
7. [REA değerlendirmesi](#7-rea-değerlendirmesi)
8. [Başarı ölçütleri](#8-başarı-ölçütleri)
9. [Ekler](#9-ekler)
10. [REA ile ne geliştirebiliriz](#10-rea-ile-ne-geliştirebiliriz)

---

## 1. Yönetici özeti

Proje **fikir olarak doğru, uygulama olarak sağlam ama kırılgan**. 221 satırlık tek dosyalık bir Python vekili, HGM'nin 10 raster katmanını tek biçimli bir XYZ adresine çeviriyor, diske önbellekliyor ve Leaflet ile gösteriyor. Bu sadelik en büyük gücü: bağımlılık yok, kurulum yok, anlaşılır.

Buna karşılık üç yapısal sorun var:

| Sorun | Etki | Kanıt |
|---|---|---|
| Vekil, proje kök dizinini **statik olarak servis ediyor** | `/sunucu.py` ve `/onbellek/` yayında; API anahtarları okunabilir | `GET /sunucu.py → 200, 9.863 bayt` |
| Önbellek **doğrulamasız ve süresiz** | Bozuk bir yanıt kalıcı olarak önbelleğe yazılabilir; 404'ler sonsuza dek boş kalır | `sunucu.py:107-129` |
| README ile kod **birbirini tutmuyor** | "2 eşzamanlı / 8 karo-sn" yazıyor, kodda 12 eşzamanlı ve hız sınırı yok | `BENIOKU.md:56-57` ↔ `sunucu.py:71` |

Ve bir de **hukuki belirsizlik**: HGM Atlas'ın kendi belge sayfası yalnızca `© 2020 HGM - Her hakkı saklıdır` diyor; servislerin üçüncü taraf kullanımına dair yayımlanmış bir lisans/koşul yok. Bu, projenin en büyük tek riski — teknik değil, hukuki.

**En büyük teknik fırsat:** HGM'nin **Uydu** haritası hibrit çalışıyor — ortofoto raster + vektör etiketler (`/CPbf/{z}/{x}/{y}.pbf`). Proje bugün uydu üzerine raster `yol_yazi` katmanı koyuyor; vektör etiketler aynı işi her zoom'da keskin yapabilir (bkz. §3.2, §5.5). Diğer dört harita saf raster olduğu için bu, "her şeyi vektöre taşı" değil, **hedefli** bir iyileştirme.

**Öncelik sırası:** önce güvenlik ve önbellek doğruluğu (1 gün), sonra dayanıklılık + testler (1 hafta), sonra mimari (2-4 hafta), en son ürün özellikleri.

> **REA ile canlı doğrulama notu:** İlk turda "HGM vektör karo yayınlıyor, en büyük fırsat bu" demiştim. REA ile HGM'yi gerçek tarayıcıda izleyince bunun **yalnızca Uydu haritası için** geçerli olduğu ortaya çıktı; Temel, Topografik, Siyasi ve Gece haritaları saf raster (§3.2). Fırsat geçerli ama dar: uydu üzerine keskin etiket. Bu düzeltme, araçla doğrulamanın neden gerekli olduğunun iyi bir örneği.

### Puan tablosu

| Boyut | Puan | Gerekçe |
|---|---|---|
| İşlevsellik | 8/10 | 10 katman, doğru zoom sınırları, çalışan önbellek |
| Kod okunabilirliği | 8/10 | Tek dosya, Türkçe adlandırma, açıklayıcı yorumlar |
| Dayanıklılık | 5/10 | Doğrulama, yeniden deneme, devre kesici eksik |
| Güvenlik | 4/10 | Kaynak dosya + önbellek dizini yayında, anahtarlar gömülü |
| Test / CI | 1/10 | Hiç test yok, sürüm kontrolü yok |
| Dokümantasyon | 7/10 | İyi yazılmış ama kodla çelişiyor |
| İstemci deneyimi | 6/10 | Sade ve çalışır; permalink, arama, mobil yok |
| Hukuki uygunluk | 3/10 | Lisans belirsiz, ticari kullanım riskli |

---

## 2. Projenin bugünkü durumu

### 2.1 Mimari

```
┌──────────────┐   HTTP/1.1    ┌─────────────────────┐   HTTPS    ┌────────────────────────────┐
│  Tarayıcı    │ ────────────► │  sunucu.py :8833    │ ─────────► │ atlasapitest.harita.gov.tr │
│  Leaflet     │  /t/<katman>/ │  · katman eşlemesi  │            │   /Layers/<Katman>/…png    │
│  1.9.4       │   {z}/{x}/{y} │  · 12 eşzamanlı     │            ├────────────────────────────┤
│              │ ◄──────────── │  · disk önbelleği   │ ◄───────── │ atlas.harita.gov.tr        │
└──────────────┘               │  · Referer başlığı  │            │   /webservis/…             │
                               └─────────┬───────────┘            └────────────────────────────┘
                                         │
                                   onbellek/<katman>/<z>/<x>/<y>.<uzantı>
                                          veya  <y>.bos  (HGM'de yok)
```

### 2.2 Dosya envanteri

| Dosya | Boyut | Rol |
|---|---|---|
| `sunucu.py` | 9.863 B / 221 satır | Vekil + önbellek + statik sunucu |
| `index.html` | 3.392 B / 78 satır | Leaflet istemcisi (satır içi JS) |
| `leaflet/leaflet.js` + `.css` + `images/` | ~163 KB | Leaflet 1.9.4, yerel kopya |
| `onbellek/` | **14.819 dosya / 216,5 MB** | Karon önbelleği (10 katman) |
| `BENIOKU.md` | 1.975 B | Kurulum ve entegrasyon notları |
| `sunucu.log` | 2.538 B, kilitli | Çalışan sürecin çıktısı (zaman damgasız) |
| `INCELEME-VE-GELISTIRME-ONERILERI.md` | bu dosya | İnceleme raporu |

**Sürüm kontrolü yok.** `git status` → `not a git repository`. 216 MB'lık önbellek ve anahtar içeren kaynak, herhangi bir geçmiş/yedek olmadan tek kopya hâlinde duruyor.

### 2.3 Önbellek gerçekleri

| Katman | Karon | Boyut | Ortalama |
|---|---:|---:|---:|
| uydu | 4.017 | 41,5 MB | 10,6 KB |
| topografik_raster | 1.613 | 59,3 MB | 37,7 KB |
| topografik | 1.360 | 23,9 MB | 18,0 KB |
| hgm_harita | 1.026 | 16,4 MB | 16,4 KB |
| siyasi | 1.016 | 8,9 MB | 9,0 KB |
| gece | 982 | 5,3 MB | 5,5 KB |
| temel | 1.644 | 13,2 MB | 8,2 KB |
| yol_yazi | 2.092 | 9,4 MB | 4,6 KB | 
| siyasi_raster | 536 | 18,0 MB | 34,4 KB |
| fiziki_raster | 533 | 20,7 MB | 39,8 KB |
| **Toplam** | **14.819** | **216,5 MB** | 15,0 KB |

59 adet `.bos` işaretçisi var; hepsi `topografik_raster` katmanında ve Türkiye dışına düşen karolar (ör. `6/34/22`…`6/35/26`). Bu davranış doğru: HGM raster topografik yalnız Türkiye'yi kapsıyor.

### 2.4 Ölçümler

**Yerel sunucu (önbellekten servis):**

| Senaryo | Sonuç |
|---|---|
| Sıralı, 25 karo | 87 karo/sn · ortalama 11,5 ms · p95 22,2 ms |
| Paralel 32 iş parçacığı, 100 karo | 2.077 karo/sn |

Önbellek isabetinde performans sorunu yok; darboğaz yalnızca HGM'ye giden ilk isteklerde.

**Soğuk karo (HGM'den ilk kez) — gerçek kullanım logundan:**

`sunucu.log`, 24.11.2026 15:15–15:17 arasındaki iki gezintiyi kaydetmiş. `[yavas]` satırlarının tamamı 1,0–2,0 saniye arasında:

```
[yavas] /t/gece/13/4811/3148 200 2.0 sn
[yavas] /t/topografik/13/4810/3147 200 2.0 sn
[yavas] /t/topografik/10/630/384 200 1.3 sn
... (toplam 37 satır, hepsi 1,0 sn üstü)
```

Yorum: bir görüntü alanındaki **tüm** karolar aynı anda 1-2 s'ye çıkıyor. Bu, tek tek yavaş karolardan çok, HGM'nin eşzamanlı istekleri kuyruğa aldığını gösteriyor — yani 12 eşzamanlı istek ayarı muhtemelen fazla. Ayrıca `[yavas]` loglarında zaman damgası yok, hangi ana ait olduğu bilinmiyor (B14).

**HGM yukarı akış (tek ölçüm):**

| Uç nokta | Süre | Boyut | Not |
|---|---|---|---|
| `atlasapitest/Layers/Base/16/…` | 0,60 s | 11,4 KB | `Cache-Control: private`, **Referer gerekmiyor** |
| `atlas/webservis/ortofoto/16/…` | 0,09 s | 17,0 KB | `ETag: "6b0543e5-43f4"`, Referer zorunlu |
| `atlas/webservis/harita/hgm_harita/16/…` | 0,09 s | 30,8 KB | `ETag` var |
| `atlas1/CPbf/6/38/24.pbf` | 0,18 s | **969 KB** | Vektör karo, sıkıştırılmamış |

---

## 3. HGM tarafı: gerçekte ne sunuluyor

### 3.1 Raster katmanlar — projedeki tablo doğru

HGM'nin kendi `atlas_raster.json` stil dosyası, katman zoom sınırlarını birebir doğruluyor:

| Katman | HGM stili | Projedeki değer | Durum |
|---|---|---|---|
| fiziki_raster | minzoom 1, maxzoom 9 | 1–9 | ✅ |
| siyasi_raster | minzoom 1, maxzoom 9 | 1–9 | ✅ |
| topografik_raster | minzoom 1, maxzoom 13 | 1–13 | ✅ |
| hgm_harita | minzoom 1, maxzoom 16 | 1–16 | ✅ |

Yani `BENIOKU.md`'deki zoom tablosu güvenilir; bu iyi bir mühendislik.

**Ama:** `BENIOKU.md:55` "Referer olmadan 403" diyor. Ölçüm bunu **kısmen** doğruluyor:

| Uç nokta | Referer'lı | Referer'sız | Yanlış Referer |
|---|---|---|---|
| `atlasapitest/Layers/Base` | 200 | **200** | **200** |
| `atlas/webservis/ortofoto` | 200 | **403** | **403** |

Yani Referer zorunluluğu yalnız `atlas.harita.gov.tr/webservis/*` için geçerli. Üstelik üç uç nokta da `Access-Control-Allow-Origin: *` döndürüyor — teknik olarak tarayıcı, `Layers/*` katmanlarını vekilsiz de çekebilir.

> **Vekilin gerçek gerekçesi** bu yüzden şu şekilde yeniden yazılmalı: (1) `webservis/*` için Referer, (2) disk önbelleği ve çevrimdışı çalışma, (3) HGM'nin 403 ile katman kapatmasını önleyen hız sınırı, (4) tüm katmanlar için tek biçimli adres. "Anahtarlar sunucuda kalır" gerekçesi zayıf — anahtarlar HGM'nin kendi genel `config.js` ve stil dosyalarında açıkça duruyor.

### 3.2 Vektör karo gerçeği — ve düzeltme

İlk incelemede "HGM'nin haritaları vektör" diye not ettim. **REA ile canlı gözlem bunu kısmen çürüttü.** HGM'nin hangi haritasının hangi kaynağı kullandığı:

| HGM haritası | Stil dosyası | Kaynak türü |
|---|---|---|
| Temel | `hgm_varsayilan.json` | **Yalnız raster** (`/Layers/Base/…png`) |
| Topografik | `hgm_yukseklik.json` | **Yalnız raster** (`/Layers/Topografik/…png`) |
| Siyasi | `hgm_siyasi.json` | **Yalnız raster** (`/Layers/Siyasi/…png`) |
| Gece | `hgm_dark.json` | **Yalnız raster** (`/Layers/Gece/…png`) |
| **Uydu** | `hgm_uydu2.json` | **Hibrit**: vektör `composite` + `label3` + raster `ortofoto` + `yolorta_uydu` |

Yani vektör karolar yalnızca **Uydu** haritasının etiket/detay katmanlarında kullanılıyor:

```
https://atlas1.harita.gov.tr/CPbf/{z}/{x}/{y}.pbf?enc=<token>
https://atlas2.harita.gov.tr/CPbf/{z}/{x}/{y}.pbf?enc=<token>
```

Bu, projenin `temel` katmanının **HGM'nin kendi varsayılan haritasıyla aynı kaynağı** kullandığını doğruluyor: REA gözleminde 18 adet `atlasapitest/Layers/Base/{z}/{x}/{y}.png?key=MEZEVy8…` isteği yakalandı — projedeki `temel` katmanıyla birebir aynı. HGM'nin dört raster haritası da projedeki dört katmana karşılık geliyor: `Base` → `temel`, `Topografik` → `topografik`, `Siyasi` → `siyasi`, `Gece` → `gece`.

Stil dosyası (`hgm_uydu2.json`, 256 KB, **152 katman**) şu kaynak katmanlarını kullanıyor:

| Kaynak katman | Kullanım | Katman sayısı |
|---|---|---:|
| `donati_font_point` | Donatı/tesis etiketleri | 52 |
| `label3` | Yer adları | 35 |
| `noktalar` | POI | 26 |
| `yolorta_yurtdisi` | Yurt dışı yolları | 12 |
| `sinir_cizgileri` | İdari sınırlar | 10 |
| `cad_2021` | Binalar | 7 |
| `yerlesim` | Yerleşim alanları | 3 |
| `karayolu` | Karayolu ağı | 3 |
| `sounding` | Deniz derinliği | 1 |

Ölçülen karo boyutları ve davranışı:

| Karo | Boyut | Detay | Not |
|---|---:|---:|---|
| z6 Türkiye (`composite`) | 969 KB | 4.436 karayolu, 17.028 sınır | 13 katman |
| z8 İstanbul | 122 KB | 4.102 detay | |
| z10 İstanbul | 156 KB | 5.752 detay | `donati_alan` 3.653 |
| z12 İstanbul | 34 KB | 885 detay | |
| **z14 / z16 İstanbul** | **0,3 KB** | **0 detay** | Yalnızca `denizler` — vektör kaynağı bu zoom'da boş |
| z6 `label3` | 1.641 KB | `cad_2021` **50.000** bina | Sıkıştırılmamış, çok ağır |

**Yorum:** Vektör kaynağı ~z12/13'e kadar dolu, sonrasında boşalıyor. Bu yüzden vektörün bu projedeki gerçek faydası "tüm haritayı vektöre taşımak" değil; **uydu görüntüsü üzerine keskin etiket/POI/sınır çizmek**. Zaten HGM de tam olarak bunu yapıyor: `yolorta_uydu` raster etiket katmanı (projedeki `yol_yazi`) yerine vektör etiketler. Vektör karoların 1 MB'a varan boyutu ve `enc` token'ının niteliği belirsizliği nedeniyle bu, "P3 / deneysel" bir yol olmayı sürdürüyor.

### 3.3 HGM'nin diğer servisleri

HGM'nin `config.js` dosyasından (98 KB, genel erişime açık) çıkarılan envanter:

| Servis | Adres | Not |
|---|---|---|
| Stil dosyaları | `/style/hgm_varsayilan.json`, `hgm_uydu2`, `hgm_siyasi`, `hgm_dark`, `hgm_yukseklik`, `atlas_raster`, `hgm_empty` | MapLibre GL formatı |
| Glif / sprite | `/style/fonts/{fontstack}/{range}.pbf`, `/style/sprites/sprite` | Vektör etiketler için |
| Adres arama | `/search_yeni`, `/search?size=40` | Geocoder |
| Rota | `/analiz/rota/route/v1/` | OSRM benzeri |
| Deprem | `/atlasservice/getEarthquake`, `/webservis/deprem/{z}/{x}/{y}.jpg` | |
| Meteoroloji | `/api/Pbf/{z}/{x}/{y}.pbf?enc=…` | |
| Tarihsel ortofoto | `/tarihsel/raster/ecw/{z}/{x}/{y}?profile=…` | `config.historical: false` — kapalı |
| MEKSİS (TKGM) | `/megsiswebapi.v3/api/idariYapi/ilListe`, `…/parsel/`, `…/ortofoto/` | Tapu/kadastro entegrasyonu |

Bu envanter, projenin bugün kullandığı 10 katmanın HGM'nin kapasitesinin küçük bir bölümü olduğunu gösteriyor.

### 3.4 Hukuki çerçeve

HGM Atlas'ın belge sayfası (`/docs/Bilgi.md`) yalnızca şunu diyor:

> `© 2020 HGM - Her hakkı saklıdır`

Yayımlanmış bir kullanım koşulu, açık lisans veya API sözleşmesi bulunamadı. Bunun pratik sonuçları:

- **Kişisel/yerel kullanım** (bu projenin bugünkü hâli): düşük risk, ama yine de gri alan.
- **Herkese açık bir yayın** (kendi alan adınızda HGM karoları sunmak): telif ihlali ve HGM'nin sunucularına yük bindirme riski; kaçınılmalı.
- **Ticari ürün**: mutlaka resmî anlaşma/lisans gerekir.
- Anahtarların gizli olmaması, kullanım izni anlamına **gelmez**.

**Öneri:** README'ye kısa bir "Kullanım koşulları ve sorumluluk" bölümü ekleyin; `attribution` her katmanda görünür kalsın (`© Harita Genel Müdürlüğü` zaten var — koruyun); projeyi yalnızca yerel/kişisel kullanım için belgeleyin.

---

## 4. Bulgular: hatalar, riskler, tutarsızlıklar

Önem sırasına göre. Her bulgu için kanıt ve düzeltme yönü verilmiştir.

### B1 — 🔴 Kritik: kaynak kod ve önbellek dizini HTTP üzerinden okunabiliyor

`Isleyici`, `SimpleHTTPRequestHandler`'ı proje köküne bağlıyor (`sunucu.py:144-148`). `do_GET` yalnız `/t/` ve `/katmanlar.json` için özel; **diğer her şey** dosya sisteminden servis ediliyor.

```
GET /sunucu.py     → 200, 9.863 bayt   (içinde API_KEY, WS_KEY, HGM_HARITA_KEY)
GET /onbellek/     → 200, dizin listesi (10 alt dizin)
GET /BENIOKU.md    → 200, 1.975 bayt
GET /sunucu.log    → 200, 2,5 KB sunucu çıktısı
GET /INCELEME-VE-GELISTIRME-ONERILERI.md → 200, 43 KB  (bu raporun kendisi de yayında)
```

Yani `sunucu.py` çalışırken **proje kökündeki her dosya** HTTP üzerinden okunabilir; yeni eklenen her dosya otomatik olarak yayına girer.

Sunucu `127.0.0.1`/`::1` dinlediği için uzaktan erişim yok; ama **herhangi bir yerel uygulama veya tarayıcı süreci** bu dosyaları okuyabilir. `/t/` yanıtlarına `Access-Control-Allow-Origin: *` eklendiği için, CORS'u yanlış yapılandırılmış bir yerel vekil üzerinden dolaylı erişim de mümkün.

**Düzeltme:** statik servisi beyaz listeye alın (§6.1).

### B2 — 🔴 Kritik: önbelleğe yazılan veri doğrulanmıyor

`sunucu.py:121-125`: HGM `200` dönerse gövde **ne olursa olsun** diske yazılıyor. Bir HTML hata sayfası, boş gövde veya yarıda kesilmiş bir yanıt kalıcı olarak "karo" hâline gelir ve tarayıcıda kırık görüntü olarak kalır — sonsuza dek, çünkü `dosya.exists()` kontrolü her şeyden önce geliyor.

**Düzeltme:** PNG/JPEG imza kontrolü + minimum boyut; başarısızsa yazma, `502` dön (§6.2).

### B3 — 🟠 Yüksek: `.bos` negatif önbelleği süresiz

`sunucu.py:106-110`: Bir karo 404 aldığında `.bos` dosyası oluşturuluyor ve **süresiz** olarak "bu karo yok" kabul ediliyor. HGM geçici bir kesinti yaşadıysa, o karo kalıcı olarak boş kalır. Ayrıca z/x/y aralığı doğrulanmadığı için `z=30` gibi istekler de `.bos` üretip önbelleği kirletir.

**Düzeltme:** `.bos` için TTL (30 gün) + `?yenile=1` ile zorla tazeleme + koordinat doğrulaması (§6.3).

### B4 — 🟠 Yüksek: README ile kod çelişiyor

| `BENIOKU.md:56-57` diyor ki | `sunucu.py` gerçekte |
|---|---|
| "katman başına en çok **2** eşzamanlı istek" | `ESZAMANLI = 12` (satır 71) |
| "saniyede **~8** karo gönderir" | Hız sınırı **yok** — 12 iş parçacığı döngüde istek atar |
| "403 gelirse o katmana **90 sn** hiç gitmez" | `BEKLEME_403 = 30` (satır 72) |

Kod, dokümandan **6 kat** daha agresif. HGM'nin 403 ile katman kapatma davranışı göz önüne alındığında bu, hem dokümantasyon hatası hem de operasyonel risk.

**Düzeltme:** ya kodu dokümana çekin, ya dokümanı koda — ve gerçek bir hız sınırı ekleyin (§6.4).

### B5 — 🟠 Yüksek: yönlendirmeler işlenmiyor

`http.client` yönlendirme takip etmez. HGM bir `301/302` dönerse `do_GET` şu dalga giriyor:

```python
return self.gonder(durum, "text/plain", govde[:300])   # 302 + Location YOK
```

İstemci `Location` başlığı olmayan bir `302` alır; tarayıcı bunu hata sayar, bazı istemciler döngüye girer.

**Düzeltme:** 3xx'te en fazla 3 adım takip et; takip edilemiyorsa `502` dön (§6.5).

### B6 — 🟠 Orta: `HEAD` ve `OPTIONS` desteklenmiyor

`do_HEAD` tanımlı değil; istek `SimpleHTTPRequestHandler`'a düşüyor ve dosya sisteminde arıyor:

```
HEAD /t/temel/6/38/24 → 404 (text/html)
```

QGIS, bazı CLI araçları ve sağlık kontrolleri önce `HEAD` dener. `OPTIONS` da yok; CORS ön kontrolü gerekirse başarısız olur.

**Düzeltme:** `do_HEAD` (gövdesiz, aynı başlıklar) ve `do_OPTIONS` ekle (§6.6).

### B7 — 🟠 Orta: 403 bekletmesi yalnız `atlasapitest` için

`sunucu.py:130`:

```python
elif durum == 403 and host.startswith("atlasapitest"):
```

`atlas.harita.gov.tr` 403 dönerse (anahtar değişimi, Referer kuralı, kota) bekletme yok, devre kesici yok. Tarayıcı her karo için aynı 403'ü alır ve kullanıcı yalnızca "karo alınamadı" görür.

**Düzeltme:** 403'ü tüm host'lar için ele al; 3 ardışık 403'te katmanı geçici kapat ve log'a net mesaj yaz (§6.7).

### B8 — 🟡 Orta: 429/5xx için yeniden deneme ve `Retry-After` yok

`_cek()` (satır 88-99) yalnızca bağlantı hatalarında 2 kez deniyor. `429 Too Many Requests` veya `503` geldiğinde doğrudan istemciye geçiyor; üstel geri çekilme (exponential backoff) ve jitter yok.

### B9 — 🟡 Orta: önbellek sınırsız büyüyor, sürümleme yok

216 MB bugün sorun değil; 19 zoom'da Türkiye'nin tamamı gezildiğinde birkaç GB'a çıkar. Tahliye (eviction), boyut sınırı, sürüm anahtarı ve "HGM verisi güncellendi" durumunu yakalama yolu yok. HGM ortofoto güncellediğinde eski karolar sonsuza dek servis edilir.

**Düzeltme:** boyut sınırı + LRU (dosya `mtime` yeterli), `onbellek/v1/…` sürüm dizini, `?yenile=1`.

### B10 — 🟡 Orta: iş parçacığı sayısı sınırsız

`ThreadingMixIn` her bağlantı için thread açıyor (`sunucu.py:196`). `daemon_threads = True` ve `request_queue_size = 128` iyi düşünülmüş, ama üst sınır yok: yavaş HGM yanıtları birikirse thread sayısı hızla büyür. Ayrıca senkron disk I/O aynı thread içinde.

### B11 — 🟡 Orta: Windows'ta sessiz port çakışması

`allow_reuse_address = True` (satır 198) Windows'ta `SO_REUSEADDR`'a karşılık gelir ve **aynı porta ikinci kez bağlanmaya izin verir**. Ölçüm:

```
SO_REUSEADDR=True  ile ikinci bind → BAŞARILI (çakışma sessiz)
SO_REUSEADDR=False ile ikinci bind → reddedildi (beklenen)
```

Yani `python sunucu.py` iki kez çalıştırılabilir; istekler rastgele eski/yeni sürece gider. "Kodu değiştirdim ama davranış aynı" şikâyetinin muhtemel nedeni budur. (İnceleme sırasında 8833 portunda çalışan bir süreç vardı ve `sunucu.log` onun tarafından kilitliydi.)

**Düzeltme:** Windows'ta `SO_EXCLUSIVEADDRUSE` kullan veya başlangıçta portu yokla ve anlaşılır hata ver.

### B12 — 🟡 Orta: istemci yalnız `localhost`/`127.0.0.1` için çalışıyor

`index.html:37-41`:

```js
const SUNUCU = `:${location.port || 8833}`;
L.tileLayer(`http://{s}${SUNUCU}${yol}`, { subdomains: ["localhost", "127.0.0.1"] })
```

- Sayfa `192.168.1.x:8833` üzerinden açılırsa karolar gelmez (sunucu zaten yalnız loopback dinliyor).
- HTTPS arkasına konursa `http://` karışık içerik nedeniyle engellenir.
- Ters vekil 80/443'te çalışırsa `location.port` boş → `:8833` → kırılır.

Çift alt alan adı hilesi (6+6 bağlantı) zekice ama kırılgan. HTTP/1.1'de bile **göreli adres** kullanmak yeterli olurdu; 6 bağlantı sınırı modern tarayıcılarda alan adı başına 6'dır ve zaten `keep-alive` ile yönetilir.

### B13 — 🟢 Düşük: istemci detayları

- `localStorage`'a HTML içeren etiket yazılıyor (`"Fiziki (Raster)<small>z≤9</small>"`) — çalışıyor ama kırılgan.
- Permalink yok: konum/zoom paylaşılamıyor, sayfa yenilenince başa dönüyor.
- `k.url` `new URL()` ile ayrıştırılıp `%7B` → `{` çevriliyor; URL ayrıştırıcısına bağımlı, gereksiz. Doğrudan regex ile yol alınabilir.
- Katman opaklığı, lejant, ölçüm aracı, koordinat arama, tam ekran yok.
- Hata göstergesi `tileerror` sayıyor ama `503` (HGM kapalı) ile `404` (karo yok) ayrımını yapmıyor.
- Mobilde dokunmatik ve küçük ekran için özel bir şey yok.

### B14 — 🟢 Düşük: gözlemlenebilirlik ve bakım

- `print()` ile log; zaman damgası yok (`[yavas]` satırlarında hiç yok), seviye yok, döndürme yok.
- `/saglik` (health), `/istatistik` (hit/miss/hata/p95) uç noktası yok.
- Test yok, CI yok, `pyproject.toml` yok, `.gitignore` yok, Docker yok.
- `sunucu.log` boş ve kilitli — log hedefi tanımsız.

### B15 — 🟢 Düşük: küçük kod kokuları

- `TIPLER` yalnız `png`/`jpg`; yeni format eklenirse sessizce `KeyError`.
- Hata yanıtlarında `Content-Type: text/plain` (charset yok) → Türkçe karakterler bozulabilir.
- `_bos_png()` fonksiyonu içinde `import struct, zlib` — modül düzeyine taşınabilir.
- `_cek()` ikinci denemede `raise` ediyor ama `None` dönebilme ihtimali kod okuyucuyu yanıltıyor.
- `katman_listesi` içinde `tur` alanı `"altlik"/"ust"`; istemci `ust` kontrolü yapıyor — adlandırma tutarsız (`altlik` vs `ust`).

### B16 — 🟠 Orta: ilk gezinti 1-2 saniye gecikmeli

Önbellekte olmayan her karo HGM'den 1,0–2,0 s'de geliyor (log kanıtı §2.4). Bu, yeni bir bölgeye ilk kez bakıldığında "harita boş, sonra dolar" hissinin nedeni. `updateWhenZooming: false` ve `keepBuffer: 2` doğru tercihler ama yeterli değil.

**Düzeltme:** (1) eşzamanlılığı düşürüp sıra başına gecikmeyi azaltın (2 eşzamanlı + 8 karo/sn deneyin, ölçün), (2) `keepBuffer`'ı 3'e çıkarın, (3) z3–z8 arası düşük zoom'ları açılışta önden indirin (tüm Türkiye ~150 karo), (4) aynı karoya gelen eşzamanlı istekleri tek upstream isteğine birleştirin (request coalescing).

---

## 5. Geliştirme önerileri ve yol haritası

Aşağıdaki tablo, etki/efor oranına göre sıralanmıştır. Her satır tek başına uygulanabilir.

| # | Öneri | Öncelik | Efor | Etki |
|---|---|---|---|---|
| 1 | Statik servisi beyaz listeye al (§6.1) | P0 | 15 dk | Kritik güvenlik |
| 2 | Karo gövdesi doğrulaması (§6.2) | P0 | 20 dk | Önbellek bozulmasını engeller |
| 3 | `.bos` TTL + `?yenile=1` (§6.3) | P0 | 30 dk | Kalıcı boş karoları çözer |
| 4 | z/x/y doğrulaması | P0 | 10 dk | Önbellek kirliliği |
| 5 | README ↔ kod eşitleme | P0 | 15 dk | Yanlış beklenti |
| 6 | Token bucket hız sınırı (§6.4) | P1 | 45 dk | 403 ban riskini düşürür |
| 7 | 3xx takibi (§6.5) | P1 | 20 dk | Kırılganlık |
| 8 | HEAD/OPTIONS (§6.6) | P1 | 20 dk | QGIS/CLI uyumu |
| 9 | 403 devre kesici, tüm host'lar (§6.7) | P1 | 30 dk | Dayanıklılık |
| 10 | 429/5xx üstel geri çekilme + `Retry-After` | P1 | 30 dk | Dayanıklılık |
| 11 | Soğuk karo gecikmesi: eşzamanlılık ayarı + prefetch + coalescing (B16) | P1 | 2 saat | İlk izlenim |
| 12 | Yapılandırılmış log + `/saglik` + `/istatistik` | P1 | 1 saat | İşletilebilirlik |
| 13 | `pytest` testleri + sahte HGM | P1 | 3 saat | Regresyon güvenliği |
| 14 | `git init` + `.gitignore` (`onbellek/`, `*.log`, `.env`) | P1 | 10 dk | Sürüm kontrolü |
| 15 | Anahtarları `.env`'e taşı | P1 | 20 dk | Yapılandırma hijyeni |
| 16 | Önbellek boyut sınırı + LRU tahliye | P2 | 2 saat | Disk kontrolü |
| 17 | ETag + `If-None-Match` + `304` | P2 | 1 saat | Bant genişliği |
| 18 | Windows `SO_EXCLUSIVEADDRUSE` + net hata | P2 | 20 dk | Operasyon |
| 19 | `aiohttp`/`httpx` ile async vekil | P2 | 1-2 gün | Ölçeklenebilirlik |
| 20 | `/style.json` üret (MapLibre tüketebilsin) | P2 | 3 saat | Tek kaynak, çok istemci |
| 21 | WMTS `GetCapabilities` + TMS uç noktaları | P2 | 4 saat | QGIS/ArcGIS uyumu |
| 22 | MBTiles/PMTiles dışa aktarma | P2 | 1 gün | Çevrimdışı saha kullanımı |
| 23 | Docker + `pyproject.toml` | P2 | 2 saat | Kurulum kolaylığı |
| 24 | İstemci: göreli URL + permalink + API'dan stil | P3 | 4 saat | Kırılganlık + UX |
| 25 | İstemci: opaklık, lejant, ölçüm, arama, tam ekran | P3 | 1-2 gün | UX |
| 26 | Vektör etiket modu — yalnız uydu görünümü (MapLibre + raster altlık) | P3 | 1-2 hafta | Etiket kalitesi |
| 27 | Yedek kaynak (OSM/Esri) + swipe karşılaştırma | P3 | 3 saat | Kesinti dayanıklılığı |
| 28 | Erişilebilirlik (klavye, ARIA), koyu tema, i18n | P3 | 1 gün | Kapsayıcılık |

### 5.1 P0 — Bugün yapılmalı (yaklaşık 1,5 saat)

Amaç: **açık kapıyı kapatmak ve önbelleğin güvenilirliğini sağlamak.** Yeni özellik yok.

1. Statik servis beyaz listesi (B1)
2. Karo imza doğrulaması (B2)
3. `.bos` TTL + `?yenile=1` (B3)
4. Koordinat aralığı doğrulaması (B3)
5. README'yi kodla eşitle (B4)

### 5.2 P1 — Bu hafta (yaklaşık 1 gün)

Amaç: **HGM'nin davranışına dayanıklı hâle gelmek ve regresyonları yakalamak.**

- Hız sınırı + üstel geri çekilme + devre kesici (B7, B8, #6)
- Soğuk karo gecikmesini düşür: eşzamanlılığı 2'ye çekip ölç, düşük zoom'ları önden indir (B16)
- 3xx, HEAD, OPTIONS (B5, B6)
- Log/health/stats (B14)
- Testler: en az 8 senaryo — önbellek isabeti, 404 → `.bos`, bozuk gövde reddi, 403 devre kesici, 3xx takibi, aralık doğrulaması, eşzamanlı aynı karo (tek upstream isteği), `.bos` TTL
- `git init`, `.gitignore`, `.env`

### 5.3 P2 — 2-4 hafta

Amaç: **mimariyi ölçeklenebilir ve standartlara uyumlu hâle getirmek.**

- Async vekil (`aiohttp`): tek süreçte yüksek eşzamanlılık, tek bağlantı havuzu, backpressure
- Önbellek yönetimi: boyut sınırı, LRU, sürüm dizini
- ETag/304, koşullu istek
- `/style.json` + WMTS + TMS: QGIS, ArcGIS, MapLibre, OpenLayers hepsi tek kaynaktan
- MBTiles/PMTiles: saha çalışması için çevrimdışı paket
- Docker + `pyproject.toml` + CI (ruff + pytest)

### 5.4 P3 — Ürünleşme

- İstemciyi ayır: `app.js` + `style.css` ayrı dosyalar, yapılandırma `/katmanlar.json`'dan
- Permalink (`#z/lat/lon`), arama, ölçüm, opaklık, lejant, tam ekran, mobil
- Yedek kaynak ile kesinti dayanıklılığı
- Erişilebilirlik ve i18n

### 5.5 P3+ — Vektör karo modu (deneysel)

**Neden:** Bugün uydu görüntüsü üzerine `yol_yazi` raster katmanı biniyor. Bu katman ancak tanımlandığı zoom'da keskin; üstünde büyütüldüğünde yazılar bulanıklaşıyor. Vektör etiketler her zoom'da keskin ve tema/etiket aç-kapa yeniden indirme gerektirmiyor.

**Nasıl:** Yalnız **uydu** görünümü için: HGM'nin `hgm_uydu2.json` stilini vekilden geçirip (`/style/uydu.json`), kaynak URL'lerini kendi `/cpbf/{z}/{x}/{y}.pbf` uç noktanıza yönlendirin; MapLibre GL JS istemciye ekleyin. Ortofoto altlığı ve `yolorta_uydu` raster katmanı yerinde kalsın; yalnız `label3`/`composite` vektör katmanları ekleyin. Vektör ~z12/13'te boşaldığı için sonrasında `yol_yazi` rasterına geri düşün.

**Riskler:**
- `enc` token'ı dile gömülü ve anlamı belirsiz; değişirse kırılır. Bu yüzden token'ı **yapılandırmaya** alın ve çalışmazsa raster moduna düşün.
- z6'da 969 KB, `label3`'te 1,6 MB karo — sıkıştırma (gzip) olmadan mobilde ağır.
- HGM'nin kendi uygulamasının token'larını kullanmak, hukuki riski artırır (bkz. §3.4). Kişisel kullanımda kalın.

---

## 6. Uygulanabilir kod örnekleri

Aşağıdaki örnekler mevcut kodun yapısına (Türkçe adlandırma, tek dosya) uyacak şekilde yazıldı.

### 6.1 Statik servisi beyaz listeye al (B1)

```python
# sunucu.py — sınıf düzeyinde
class Isleyici(http.server.SimpleHTTPRequestHandler):
    IZINLI_DOSYALAR = {"/", "/index.html"}
    IZINLI_DIZINLER = ("/leaflet/",)

    def do_GET(self):
        yol = self.path.split("?")[0]
        if yol == "/katmanlar.json":
            ...
        if yol.startswith("/t/"):
            ...
        # Geri kalan her şey: yalnız bilinen statik varlıklar
        if yol in self.IZINLI_DOSYALAR or yol.startswith(self.IZINLI_DIZINLER):
            return super().do_GET()
        return self.gonder(404, "text/plain; charset=utf-8", "yok".encode())
```

> Not: `do_HEAD` de aynı beyaz listeyi kullanmalı, aksi hâlde `HEAD /sunucu.py` hâlâ var olup olmadığını sızdırır.

### 6.2 Karo gövdesi doğrulaması (B2)

```python
IMZALAR = {"png": b"\x89PNG\r\n\x1a\n", "jpg": b"\xff\xd8\xff"}
EN_KUCUK = 64  # bundan küçük her şey şüpheli

def _gecerli_karo(uzanti, govde):
    imza = IMZALAR.get(uzanti)
    return bool(imza) and len(govde) >= EN_KUCUK and govde.startswith(imza)
```

`karo_getir` içinde:

```python
if durum == 200:
    if not _gecerli_karo(uzanti, govde):
        print(f"[uyari] {ad} {z}/{x}/{y}: HGM bozuk gövde döndürdü "
              f"({len(govde)} bayt, {govde[:16]!r}), önbelleğe yazılmadı", flush=True)
        return 502, b"HGM gecersiz karo dondurdu"
    dosya.parent.mkdir(parents=True, exist_ok=True)
    ...
```

### 6.3 `.bos` TTL + koordinat doğrulaması + `?yenile=1` (B3)

```python
BOS_TTL = 30 * 86400  # 30 gün

def _bos_gecerli(bos):
    try:
        return time.time() - bos.stat().st_mtime < BOS_TTL
    except OSError:
        return False
```

```python
# karo_getir başında
def karo_getir(ad, z, x, y, yenile=False):
    if not (0 <= z <= 22) or not (0 <= x < 2 ** z) or not (0 <= y < 2 ** z):
        return 400, b"z/x/y aralik disi"
    ...
    if not yenile and dosya.exists():
        return 200, dosya.read_bytes()
    if not yenile and bos.exists() and _bos_gecerli(bos):
        return 204, b""
```

`do_GET` içinde:

```python
sorgu = self.path.split("?")[1] if "?" in self.path else ""
yenile = "yenile=1" in sorgu
durum, govde = karo_getir(parca[0], z, x, y, yenile=yenile)
```

### 6.4 Token bucket hız sınırı (B4, #6)

```python
class JetonKovasi:
    """Saniyede `hiz` istek; en çok `kapasite` jeton birikir."""
    def __init__(self, hiz, kapasite=None):
        self.hiz = float(hiz)
        self.kapasite = float(kapasite or hiz)
        self.jeton = self.kapasite
        self.zaman = time.monotonic()
        self.kilit = threading.Lock()

    def al(self):
        while True:
            with self.kilit:
                simdi = time.monotonic()
                self.jeton = min(self.kapasite,
                                 self.jeton + (simdi - self.zaman) * self.hiz)
                self.zaman = simdi
                if self.jeton >= 1:
                    self.jeton -= 1
                    return
                bekle = (1 - self.jeton) / self.hiz
            time.sleep(bekle)   # kilit dışında uyu: diğer thread'ler beklemesin
```

Kullanım: `_hizlar = {ad: JetonKovasi(8, 16) for ad in KATMANLAR}` ve `_cek()` çağrısından hemen önce `_hizlar[ad].al()`.

> `ESZAMANLI` semaforunu da README'deki değere (2) çekin veya dokümanı 12'ye güncelleyin — ikisi aynı şeyi anlatmalı.

### 6.5 Yönlendirme takibi (B5)

```python
# _cek() dosyanın başında: import urllib.parse

def _cek(host, yol, en_fazla=3):
    for adim in range(en_fazla):
        b = _baglanti(host)
        try:
            b.request("GET", yol, headers=BASLIK)
            r = b.getresponse()
            govde = r.read()
            if r.status in (301, 302, 303, 307, 308):
                hedef = r.getheader("Location")
                if not hedef:
                    return 502, b"HGM Location'suz yonlendirme dondurdu"
                baglanti = urllib.parse.urlsplit(hedef)
                host = baglanti.netloc or host
                yol = baglanti.path + ("?" + baglanti.query if baglanti.query else "")
                continue
            return r.status, govde
        except (http.client.HTTPException, OSError):
            b.close()
            _yerel.havuz.pop(host, None)
    return 502, b"HGM cok fazla yonlendirme dondurdu"
```

### 6.6 HEAD / OPTIONS (B6)

```python
def do_HEAD(self):
    yol = self.path.split("?")[0]
    if not (yol in self.IZINLI_DOSYALAR or yol.startswith(self.IZINLI_DIZINLER)):
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()
        return
    super().do_HEAD()

def do_OPTIONS(self):
    self.send_response(204)
    self.send_header("Allow", "GET, HEAD, OPTIONS")
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
    self.send_header("Content-Length", "0")
    self.end_headers()
```

### 6.7 403 devre kesici, tüm host'lar (B7)

`karo_getir` içindeki mevcut `if durum == 200 / elif durum == 404 / elif durum == 403` zincirini şöyle değiştirin:

```python
_403_sayaci = {ad: 0 for ad in KATMANLAR}

# 200 dalının başında sayacı sıfırla:
if durum == 200:
    _403_sayaci[ad] = 0
    ...

# 404 dalının yanına: 403'ü artık tüm host'lar için ele al
elif durum == 403:
    _403_sayaci[ad] += 1
    if _403_sayaci[ad] >= 3:
        _kapali_bitis[ad] = time.time() + BEKLEME_403
        _403_sayaci[ad] = 0
        print(f"[uyari] '{ad}' icin ardisik 403: HGM istegi reddediyor "
              f"(anahtar/Referer/kota). {BEKLEME_403} sn ara verildi.", flush=True)
```

`do_GET` içinde `503` yanıtına `Retry-After` ekleyin:

```python
if durum == 503:
    self.send_response(503)
    self.send_header("Retry-After", str(int(_kapali_bitis[ad] - time.time()) + 1))
    ...
```

### 6.8 İstemci: göreli adres + permalink (B12, B13)

```js
// index.html — alt alan adı hilesi ve mutlak http:// yerine göreli adres
function karoKatmani(k) {
  const yol = k.url.replace(/^https?:\/\/[^/]+/, "");   // "/t/temel/{z}/{x}/{y}"
  const katman = L.tileLayer(yol, {
    minZoom: 3, maxZoom: 19,
    minNativeZoom: k.minZoom, maxNativeZoom: k.maxNativeZoom,
    attribution: "© Harita Genel Müdürlüğü",
    updateWhenZooming: false,
    keepBuffer: 2,
  });
  katman.on("tileerror", () => hataGoster(k.ad));
  return katman;
}

// Permalink: #z/lat/lon
function konumuYaz() {
  const c = harita.getCenter();
  history.replaceState(null, "", `#${harita.getZoom()}/${c.lat.toFixed(5)}/${c.lng.toFixed(5)}`);
}
harita.on("moveend", konumuYaz);

const parca = location.hash.slice(1).split("/").map(Number);
if (parca.length === 3 && parca.every(Number.isFinite)) {
  harita.setView([parca[1], parca[2]], parca[0]);
}
```

### 6.9 Yapılandırma ve sağlık uçları (#11, #14)

```python
# .env  (git'e eklenmez)
HGM_API_KEY=...
HGM_WS_KEY=...
HGM_HARITA_KEY=...
PORT=8833
ESZAMANLI=2
HIZ_SINIRI=8
```

```python
import os
PORT = int(os.environ.get("PORT", 8833))
API_KEY = os.environ["HGM_API_KEY"]   # yoksa açılışta anlaşılır hata
```

```python
if yol == "/saglik":
    return self.gonder(200, "application/json; charset=utf-8",
                       json.dumps({"durum": "ayakta", "katman": len(KATMANLAR),
                                   "onbellek_mb": _onbellek_mb()}).encode())
```

---

## 7. REA değerlendirmesi

### 7.1 Nedir

[morluto/rea](https://github.com/morluto/rea), ajanlar ve terminal için bir **tersine mühendislik MCP sunucusu + CLI**. Yerel olarak çalışır; hedefin kaynak kodu olmadan davranışını anlamayı, kanıt (Evidence) üretmeyi ve o kanıtı bir ajana aktarmayı amaçlar.

| Özellik | Değer |
|---|---|
| Paket | `rea-agents` (npm), sürüm **6.10.1** |
| Lisans | MIT |
| Boyut | 186 MB açılmış, 10.490 dosya |
| Çalışma ortamı | Node.js `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1` |
| Derin analiz | Hopper, Ghidra, IDA, Kuna, JADX (isteğe bağlı) |
| Statik JS/.NET | Yerleşik, ek araç gerekmez |
| Web sitesi analizi | Chrome tabanlı tarayıcı gerekir |
| GitHub | 476 bin yıldız, 116 bin çatal, 1.175 açık konu (24.11.2026) |

### 7.2 Bu proje için ne yapar, ne yapmaz — ölçülmüş sonuç

| İş | REA ile | Bu oturumda sonuç |
|---|---|---|
| HGM Atlas'ın ağ davranışını kanıtlamak | ✅ Tarayıcı gözlemi | **Başarılı**: 137 istek, 87 benzersiz URL, 11,3 s |
| Varsayımları çürütmek | ✅ Kanıt | **Başarılı**: "HGM vektör kullanıyor" varsayımımı düzeltti (§3.2) |
| Statik bundle analizi (uç nokta çıkarma) | ⚠️ Kısmi | Çalıştı ama JS işçisi hata verdi: 0 betik ayrıştırıldı, `endpoints` boş |
| Bu 221 satırlık Python vekilini analiz etmek | ❌ | Kaynak zaten elimizde — gereksiz |
| Çalışan sunucunun davranışını ölçmek | ❌ | `curl` + basit betikler daha hızlı |

### 7.3 Bu oturumda çalıştırıldı — ne oldu

Başlangıçta REA reddetti (Node `v26.3.0` < `26.12.1`). Çözüm: **taşınabilir Node 26.13.1 LTS** (resmî zip, 41 MB) yanına kuruldu, sistem npm'i **12.0.2 → 12.2.3** güncellendi.

```powershell
# Taşınabilir Node 26.13.1 (yönetici izni gerekmez)
$N = "$env:TEMP\node-v26.13.1-win-x64"
$env:PATH = "$N;" + $env:PATH
npm install -g rea-agents@latest      # 186 MB, ~15 sn
rea --version                          # 6.10.1
rea doctor                             # node: healthy, host: healthy
```

`rea doctor` sonucu: `node 26.13.1 ✅`, `host win32 x64 ✅`; Hopper/Ghidra/IDA/JADX **yok** — bu iş için gerekmiyor (web gözlemi yerleşik).

Chrome tarafında iki sürtünme çıktı:

1. **crashpad engeli:** Chrome, sandbox altında `crashpad_client_win.cc: OpenProcess: Erişim engellendi` hatasıyla kendini kapatıyor. Tam erişimle başlatılınca çalıştı.
2. **Playwright launch modu başarısız:** `rea capture-browser-scenario` kendi Chrome'unu başlatamadı (`execution_failure`). **Connect modu** çözüm oldu: Chrome `--remote-debugging-port=9222` ile ayrı başlatıldı, REA bağlandı.

```powershell
# 1) Chrome'u hata ayıklama portuyla başlat
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --headless=new --remote-debugging-port=9222 --user-data-dir="$env:TEMP\rea-chrome" about:blank

# 2) Sayfayı CDP ile aç ve hedef kimliğini al
$id = (Invoke-WebRequest -UseBasicParsing -Method Put `
       'http://127.0.0.1:9222/json/new?https://atlas.harita.gov.tr/').Content | ConvertFrom-Json | % id

# 3) Ağ gözlemini yakala (senaryoda "mode": "connect" kullanılıyor)
rea capture-browser-scenario hgm-ag-senaryo.json --detail summary --evidence_output hgm-ag.json --json

# 4) Bundle'ı statik analiz et
rea analyze-web-bundle http://127.0.0.1:9222 $id --allowed-origins https://atlas.harita.gov.tr `
    --detail summary --evidence_output hgm-bundle.json `
    --view '{"kind":"web-bundle","collection":"endpoints","offset":0,"limit":100}' --json
```

Sonuçlar:

| Adım | Sonuç |
|---|---|
| `capture-browser-scenario` (connect) | ✅ 137 işlem, 681 olay, 11,3 s, 825 KB kanıt dosyası |
| `analyze-web-bundle` | ⚠️ Kanıt üretildi (11 KB) ama `parsed_scripts: 0`; `javascript_analysis` açık "unknown" olarak işaretlendi: *"Owned web-script analysis failed"* |

React/webpack bundle'ı için statik işçi bu sayfada çalışmadı. REA bunu gizlemedi, **açık bilinmeyen** olarak raporladı — kanıt disiplininin iyi tarafı bu. Ama pratikte uç nokta çıkarma işini ağ gözlemi yaptı, statik analiz değil.

### 7.4 REA'nın HGM için ürettiği kanıt

**Kaynak dağılımı (137 işlem):**

| Kaynak | İşlem |
|---|---:|
| `atlas.harita.gov.tr` | 86 |
| `atlasapitest.harita.gov.tr` | 36 |
| `fonts.gstatic.com` | 6 |
| `fonts.googleapis.com` | 4 |
| `www.googletagmanager.com` | 4 |
| `www.google-analytics.com` | 1 |

**Kaynak türü:** image 44, fetch 43, script 30, stylesheet 10, font 8, document 2. **Durum:** 133 × 2xx, 2 × 4xx, 2 × başarısız.

**Yakalanan uç noktalar (projeyle karşılaştırma):**

| Yakalanan | Adet | Projede |
|---|---:|---|
| `atlasapitest…/Layers/Base/{z}/{x}/{y}.png?key=…` | 18 | ✅ `temel` katmanıyla **aynı kaynak** |
| `/config.js`, `/app.js`, `/vendors.js`, `/styles.js` | 1'er | — |
| `/style/hgm_varsayilan.json` | 1 | — |
| `/style/sprites/sprite.json` + `.png` | 1 | — |
| `/assets/lib/geocoder-latest.js` | 1 | — |
| `bundle.js` | **2 × 404** | HGM'nin kendi sitesinde kırık referans |

**Üç somut çıktı:**

1. **Doğrulama:** Projenin `temel` katmanı, HGM'nin kendi varsayılan haritasıyla **birebir aynı** kaynağı kullanıyor. Yani katman seçimi keyfi değil, doğru.
2. **Düzeltme:** "HGM vektör kullanıyor" iddiam yalnızca **Uydu** haritası için doğruymuş; diğer dört harita saf raster (§3.2).
3. **Küçük bulgu:** HGM'nin kendi sayfası `bundle.js` için 404 alıyor (`ERR_ABORTED`) — HGM tarafında da bakım borcu var.

### 7.5 Dürüst değerlendirme

- **Güçlü yönü:** Kanıt disiplini gerçekten işliyor. Yanlış varsayımımı çürüttü, çalışmayan adımı "bilinmeyen" olarak işaretledi, her sonuca kanıt kimliği (`evidence_id`) verdi.
- **Zayıf yönü:** Kurulum sürtünmesi yüksek — Node sürüm kapısı, npm önbellek yolu, Chrome crashpad/sandbox, Playwright launch hatası. Dört ayrı engel; her biri sıradan bir kullanıcıyı durdurabilir.
- **Kırılganlık:** `analyze-web-bundle` bu sayfada JS işçisini çalıştıramadı. Modern bundler'larda bu tür "worker_failure" olasılığı, aracın değerini ağ gözlemine indirgiyor.
- **Öneri:** REA'yı bu projenin bağımlılığı yapmayın; **ayda bir çalıştırılan denetim** olarak tutun. Taşınabilir Node klasörünü kalıcı bir yere taşıyın (`%LOCALAPPDATA%\rea-tools`), `PATH`'e eklemeyin, yalnızca gerektiğinde kullanın. Günlük iş için `pytest` + `curl` yeterli.

> Not: `rea setup` **çalıştırılmadı** — ajan yapılandırmasını değiştirdiği için bu oturumda gereksizdi. MCP üzerinden ajan içinden kullanmak isterseniz `rea setup` gerekir.

---

## 8. Başarı ölçütleri

Aşağıdaki eşikler, önerilerin gerçekten işe yaradığını ölçmek için kullanılabilir.

| Ölçüt | Bugün | Hedef (P1 sonrası) | Hedef (P2 sonrası) |
|---|---|---|---|
| Önbellek isabet oranı (tekrar gezintide) | ~%99 (ölçülmedi, dolaylı) | ≥ %95 ölçülür durumda | ≥ %98 |
| HGM 403 oranı | Bilinmiyor | < %0,1 | < %0,05 |
| Önbellekten p95 yanıt | 22 ms | ≤ 20 ms | ≤ 15 ms |
| Soğuk karo p95 (HGM'den) | 1,0–2,0 s | ≤ 1,5 s | ≤ 1,0 s |
| Bozuk karo (imza hatası) | Tespit edilemiyor | 0 kabul | 0 kabul |
| `.bos` yanlış negatif ömrü | Sonsuz | 30 gün | 30 gün |
| Statik dosya sızıntısı | proje kökündeki her dosya | 0 | 0 |
| Test kapsamı (vekil) | %0 | ≥ %70 | ≥ %80 |
| Çalışan ikinci süreç | Sessizce mümkün | Anlaşılır hata | Anlaşılır hata |

---

## 9. Ekler

### 9.1 İncelemede kullanılan komutlar

```powershell
# Yerel sunucu davranışı
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8833/katmanlar.json
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8833/sunucu.py          # B1
Invoke-WebRequest -UseBasicParsing -Method Head http://127.0.0.1:8833/t/temel/6/38/24   # B6

# Önbellek envanteri
Get-ChildItem onbellek -Directory | ForEach-Object {
  $f = Get-ChildItem $_.FullName -Recurse -File
  [pscustomobject]@{ Katman=$_.Name; Adet=$f.Count; MB=[math]::Round((($f|Measure-Object Length -Sum).Sum)/1MB,1) }
}
Get-ChildItem onbellek -Recurse -Filter *.bos | Measure-Object     # 59
```

```python
# HGM envanteri (atlas.harita.gov.tr isteklerinde Referer gönderin)
import urllib.request, json
H = {"Referer": "https://atlas.harita.gov.tr/", "User-Agent": "Mozilla/5.0"}
for ad in ["hgm_varsayilan", "hgm_uydu2", "hgm_siyasi", "hgm_dark", "atlas_raster"]:
    u = f"https://atlas.harita.gov.tr/style/{ad}.json"
    j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30))
    print(ad, list(j["sources"]), len(j["layers"]), "katman")
```

### 9.2 Kaynaklar

| Kaynak | Adres |
|---|---|
| Proje kodu | `sunucu.py`, `index.html`, `BENIOKU.md` |
| REA ağ kanıtı (137 istek) | `rea-kanit/hgm-ag.json` (825 KB) |
| REA bundle kanıtı | `rea-kanit/hgm-bundle.json` |
| REA tek kayıt kanıtı (environment-build girdisi) | `rea-kanit/hgm-ag-tekil.json` |
| REA senaryo dosyaları | `rea-kanit/hgm-ag-senaryo.json`, `rea-kanit/hgm-senaryo.json` |
| HGM Atlas | https://atlas.harita.gov.tr/ |
| HGM config | https://atlas.harita.gov.tr/config.js |
| HGM stilleri | https://atlas.harita.gov.tr/style/hgm_uydu2.json |
| REA | https://github.com/morluto/rea |
| REA CLI belgesi | https://github.com/morluto/rea/blob/main/docs/getting-started/cli.md |
| REA hedef matrisi | https://github.com/morluto/rea/blob/main/docs/reference/supported-targets.md |
| REA web gözlemi | https://github.com/morluto/rea/blob/main/docs/guides/web/browser-observation.md |

### 9.3 Terimler

| Terim | Anlam |
|---|---|
| XYZ / TMS | Zoom/kolon/satır tabanlı karo adresleme şeması |
| MVT / PBF | Mapbox Vector Tile; protobuf ile kodlanmış vektör karo |
| WMTS | OGC'nin standart karo servis protokolü |
| PMTiles / MBTiles | Tek dosyada karo arşivi (çevrimdışı) |
| Negative cache | "Bu karo yok" bilgisinin önbelleklenmesi (`.bos`) |
| Circuit breaker | Ardışık hatalardan sonra kaynağa geçici olarak ara verme |
| Token bucket | Saniyedeki istek sayısını sınırlayan algoritma |

---

## 10. REA ile ne geliştirebiliriz

Bu bölüm, REA'nın **gerçekten çalıştığı doğrulanmış** yeteneklerine dayanır. Spekülatif olanlar ayrıca işaretlendi.

### 10.1 Kısa cevap

REA bu projede bir "kod yazma aracı" değil; **dış dünyayı (HGM'yi) ölçen bir test ve keşif aracı**. Bu yüzden en yüksek getirili fikirler, projenin en zayıf olduğu yerle — test yokluğu ve dış bağımlılığın sessizce bozulması — örtüşüyor.

| # | Fikir | Ne yapar | Efor | Değer |
|---|---|---|---|---|
| 1 | **Katman sözleşmesi dedektörü** | Ayda bir HGM'yi izler, `KATMANLAR` tablosuyla karşılaştırır, sapmada uyarır | 4 saat | ⭐⭐⭐ |
| 2 | **Görsel regresyon** | Harita ekran görüntüsünü sürüm öncesi/sonrası karşılaştırır | 2 saat | ⭐⭐⭐ |
| 3 | **İstemci E2E testleri** | Katman değiştir/zoom yap/URL doğrula senaryolarını otomatik koşturur | 1 gün | ⭐⭐⭐ |
| 4 | **JSON servis envanteri** | `search_yeni`, rota, deprem uçlarının sözleşmesini kaydeder | 3 saat | ⭐⭐ |
| 5 | **Paketlenmiş sürüm denetimi** | Masaüstü/paket sürümünde sızan anahtar arar | 2 saat | ⭐⭐ (ürün olursa) |
| 6 | **HGM mobil istemcisi analizi** | APK varsa uç nokta/anahtar envanteri | 3 saat | ⭐ (niş) |

### 10.2 Fikir 1 — Katman sözleşmesi dedektörü (en yüksek getiri)

**Sorun:** HGM bir katmanı yeniden adlandırırsa, anahtarı döndürürse veya zoom sınırını değiştirirse proje **sessizce** bozulur. Bugün bunu fark edecek hiçbir mekanizma yok; `BENIOKU.md`'deki tablonun doğruluğu bile elle doğrulandı.

**Nasıl:**
1. `git init` + `.gitignore` (ön koşul — proje henüz sürüm kontrolünde değil)
2. `araclar/hgm-denetim.ps1`: Chrome'u CDP ile açar → `rea capture-browser-scenario` → kanıttan karo URL'lerini çıkarır → `sunucu.py`'deki `KATMANLAR` ile karşılaştırır
3. Sapma varsa: `denetim/<tarih>.json` yazar ve çıkış kodu 1
4. Ayda bir zamanlanmış görev (veya CI)

**Karşılaştırma için** `rea compare-web-captures <önce> <sonra>` de kullanılabilir; yeni/kaybolan uç noktaları kanıt düzeyinde verir.

**Neden değerli:** Raporun B4 bulgusu (README ↔ kod çelişkisi) tam bu sınıftan bir hataydı — dış dünya ile kod arasındaki sessiz kayma.

### 10.3 Fikir 2 — Görsel regresyon

**Nasıl:** `rea capture-web-screenshot` ile haritanın ekran görüntüsünü al; CSS/Leaflet sürümü değişikliğinden sonra tekrar al; `rea compare-web-screenshots` ile karşılaştır. Fark varsa incele.

**Neden değerli:** `index.html`'de yapılacak her değişiklik (göreli URL, permalink, katman paneli) görsel olarak gerileyebilir; bunu yakalayan hiçbir şey yok.

### 10.4 Fikir 3 — İstemci E2E testleri

**Nasıl:** `capture-browser-scenario` senaryoları `click`, `select_option`, `press`, `wait_for` eylemlerini destekliyor. Üç senaryo yeterli:

1. Açılış → harita yüklenir, `temel` katmanı gelir (karo istekleri 2xx)
2. Katman değiştir → `siyasi` seçilir, `maxZoom` 17'ye sınırlanır
3. Sayfa yenile → `localStorage`'daki katman korunur

Bu, sıfır testi olan bir istemci için gerçek bir kazanç; ayrıca B12/B13'teki kırılganlıkların regresyonunu engeller.

### 10.5 Fikir 4 — JSON servis envanteri

**Denendi:** Mevcut kanıtla `rea environment-build` çalıştırıldı. Sonuç: **2 araç** üretildi, 22 grup dışlandı. Nedeni açık — yakalanan trafiğin çoğu **ikili karo** (PNG/JPEG) ve REA'nın ortam modeli JSON araçları hedefliyor.

Bu yüzden bu fikir karo vekili için değil, HGM'nin **JSON servisleri** için anlamlı: `search_yeni` (arama), `/analiz/rota/route/v1/` (rota), `/atlasservice/getEarthquake` (deprem), MEKSİS parsel. Bunların sözleşmesini bir kez kaydetmek, ileride "arama ekleyelim" dediğinizde tahmin yerine kanıtla başlamayı sağlar.

> Not: Tam ortam üretmek için yakalamada `capture.network.response_body: true` seçilmeli; bu olmadan durum türetilemiyor (`unsupported_target` uyarısı aldım).

### 10.6 Fikir 5 — Paketlenmiş sürüm denetimi (ileriye dönük)

Proje bir masaüstü uygulamasına (Tauri/Electron) dönüşürse `rea audit-release-exposure` ve `analyze-javascript-application`, **yayınlanan pakette sızan anahtar/sır** arar. B1 bulgusunun (kaynak kodun HTTP'den okunması) paketlenmiş sürümdeki karşılığını yakalar. Bu, projenin bugünkü hâli için değil, ürünleşme senaryosu için geçerli.

### 10.7 REA'nın bu projede yapamadıkları

| Yapamaz | Neden |
|---|---|
| Python vekilini analiz etmek | Kaynak analizi hedefi değil; zaten elimizde |
| Karo trafiğini "ortam" olarak modellemek | Ortam modeli JSON araç odaklı; ikili karolar dışlanıyor (ölçüldü: 2 araç) |
| Bu bundle'da statik uç nokta çıkarmak | `analyze-web-bundle` JS işçisi düştü (`parsed_scripts: 0`) |
| Native ikili analizi | Hopper/Ghidra/IDA kurulu değil (bu iş için de gerekmiyor) |
| HGM'ye yük bindirmeden ölçekli tarama | Her koşum gerçek istek atar; hukuki risk §3.4'te |

### 10.8 Önerilen sıra

1. `git init` + `.gitignore` (10 dk) — her şeyin ön koşulu
2. Fikir 2 (görsel regresyon, 2 saat) — en hızlı geri dönüş
3. Fikir 1 (katman dedektörü, 4 saat) — en yüksek kalıcı değer
4. Fikir 3 (E2E, 1 gün) — P1 testlerinin yerini kısmen doldurur
5. Fikir 4 — yalnız yeni bir HGM servisi entegre etmeden önce

---

*Bu rapor, çalışan sunucu ve HGM servisleri üzerinde yapılan canlı ölçümlere dayanır. HGM tarafındaki uç noktalar haber verilmeden değişebilir; §9.1'deki komutlarla envanter yeniden doğrulanmalıdır.*
