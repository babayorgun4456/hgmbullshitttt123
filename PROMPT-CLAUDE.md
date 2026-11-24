# Claude için geliştirme prompt'u

Aşağıdaki metni `--- PROMPT BAŞLANGIÇ ---` ile `--- PROMPT SON ---` arasından kopyalayıp Claude'a verin.
Prompt kendi kendine yeterlidir: projeyi tanıtır, doğrulanmış bulguları taşır, görevleri kabul kriterleriyle listeler.

---

--- PROMPT BAŞLANGIÇ ---

Sen kıdemli bir Python/coğrafi veri geliştiricisisin. Bir Windows makinesinde, `C:\Users\user\Desktop\hgm-harita` dizinindeki küçük bir projeyi güçlendireceksin. Amacın yeni özellik eklemek değil; **mevcut davranışı bozmadan güvenlik, dayanıklılık ve test edilebilirlik kazandırmak.**

## 1. Proje nedir

HGM (Harita Genel Müdürlüğü) Atlas karolarını yerel bir vekil üzerinden sunan, tek dosyalık bir Python sunucusu + Leaflet istemcisi.

```
Tarayıcı (Leaflet 1.9.4)  →  sunucu.py :8833  →  HGM (atlas.harita.gov.tr)
                              ↓
                        onbellek/<katman>/<z>/<x>/<y>.<png|jpg>
```

Dosyalar:

| Dosya | Boyut | İçerik |
|---|---|---|
| `sunucu.py` | 221 satır | Vekil + disk önbelleği + statik sunucu |
| `index.html` | 78 satır | Leaflet istemcisi, satır içi JS |
| `BENIOKU.md` | 58 satır | Kurulum ve entegrasyon notları |
| `leaflet/` | — | Leaflet 1.9.4 yerel kopya |
| `onbellek/` | 14.819 dosya, 216,5 MB | Karon önbelleği — **dokunma, silme** |
| `rea-kanit/` | 819 KB | REA ölçüm kanıtları — **referans, değiştirme** |

Kritik kod bölgeleri (`sunucu.py`):

- `30-32` API anahtarları (gömülü)
- `35-46` `KATMANLAR` sözlüğü — 10 katman
- `48-54` `BASLIK` (Referer/Origin/User-Agent)
- `71-72` `ESZAMANLI = 12`, `BEKLEME_403 = 30`
- `88-99` `_cek()` — HGM'ye istek
- `102-133` `karo_getir()` — önbellek mantığı
- `144-193` `Isleyici` sınıfı — HTTP işleyici
- `196-221` sunucu ve başlatma

## 2. Doğrulanmış gerçekler (bunları yeniden araştırma)

Bu bulgular canlı ölçümle doğrulandı; varsayım değil.

**HGM tarafı:**

- Katman tablosu **doğru**: `temel` → `/Layers/Base/`, `topografik` → `/Layers/Topografik/`, `siyasi` → `/Layers/Siyasi/`, `gece` → `/Layers/Gece/` (hepsi `atlasapitest.harita.gov.tr`, Referer gerekmez, `CORS: *`).
- `atlas.harita.gov.tr/webservis/*` uçları **Referer zorunlu** (yoksa 403). `BASLIK` bu yüzden gerekli; koru.
- Zoom sınırları doğru: fiziki 1-9, siyasi 1-9, topografik_raster 1-13, hgm_harita 1-16, diğerleri 19.
- Vektör karo (`/CPbf/…pbf`) **yalnız uydu görünümünde** kullanılıyor; bu proje için P3 dışında gereksiz.
- Anahtarlar HGM'nin kendi genel `config.js`/stil dosyalarında açık — "sır" değiller. Yine de koda gömülü olmamalı.

**Proje ölçümleri:**

- Önbellekten servis: 87 karo/sn sıralı, p95 **22 ms** — bu tarafta performans sorunu yok.
- HGM'den soğuk karo: **1,0-2,0 sn** (log kanıtı). Eşzamanlılık 12 muhtemelen fazla.
- Önbellek: 14.819 karo / 216,5 MB; 59 adet `.bos` (hepsi `topografik_raster`, Türkiye dışı).

## 3. Bilinen hatalar (düzeltilecek)

| # | Önem | Hata | Yer |
|---|---|---|---|
| B1 | Kritik | Proje kökündeki **her dosya** HTTP'den okunabiliyor (`/sunucu.py` → 200, anahtarlar; `/onbellek/` → dizin listesi; `/sunucu.log` → 200) | `144-148`, `193` |
| B2 | Kritik | HGM `200` dönerse gövde doğrulanmadan önbelleğe yazılıyor — bozuk yanıt kalıcı olur | `121-125` |
| B3 | Yüksek | `.bos` negatif önbelleği **süresiz**; ayrıca `z/x/y` aralığı doğrulanmıyor | `105-110`, `174` |
| B4 | Yüksek | `BENIOKU.md` "2 eşzamanlı / 8 karo-sn" diyor; kodda 12 ve hız sınırı yok | `71-72` |
| B5 | Yüksek | 3xx yönlendirme izlenmiyor → `Location` başlıksız 302 dönüyor | `88-99`, `192` |
| B6 | Orta | `HEAD /t/...` → **404** (QGIS/CLI uyumsuz); `OPTIONS` yok | sınıf düzeyinde |
| B7 | Orta | 403 bekletmesi yalnız `atlasapitest` için; `atlas.harita.gov.tr` 403'ünde devre kesici yok | `130` |
| B8 | Orta | 429/5xx yeniden deneme yok, `Retry-After` yok | `88-99` |
| B9 | Orta | Önbellek sınırsız büyüyor, tahliye/sürümleme yok | — |
| B10 | Orta | Bağlantı başına thread, üst sınır yok | `196-204` |
| B11 | Orta | Windows'ta `allow_reuse_address` **sessiz port çakışmasına** izin veriyor (ölçüldü) | `198` |
| B12 | Orta | İstemci mutlak `http://` + `localhost/127.0.0.1` alt alan adı hilesi kullanıyor; LAN/ters vekil/mobil kırılır | `index.html:37-41` |
| B13 | Düşük | Permalink yok; `localStorage`'a HTML etiketli anahtar yazılıyor | `index.html:69-72` |
| B14 | Düşük | Log'da zaman damgası yok; `/saglik`, `/istatistik` yok; test/CI yok | — |

## 4. Görevler

Sırayla ilerle. Her paket bitince **dur, test sonuçlarını bildir**, sonra devam et.

### PAKET 0 — Güvenlik ve doğruluk (öncelik: en yüksek)

**0.1 Statik servisi beyaz listeye al** (B1)
- Yalnız `/`, `/index.html`, `/leaflet/*` servis edilsin.
- `/sunucu.py`, `/BENIOKU.md`, `/sunucu.log`, `/onbellek/*`, `/*.md` → **404**.
- `do_HEAD` de aynı beyaz listeyi kullansın (yoksa `HEAD` hâlâ varlık sızdırır).
- Kritik: `KOK` dizinini `SimpleHTTPRequestHandler`'a vermeye devam et ama `translate_path` yerine `do_GET`/`do_HEAD` içinde kapı koy.

**0.2 Karo gövdesi doğrulaması** (B2)
- PNG imzası `b"\x89PNG\r\n\x1a\n"`, JPEG imzası `b"\xff\xd8\xff"`.
- Boyut eşiği: 64 bayttan küçük gövde geçersiz.
- Geçersizse: **önbelleğe yazma**, `502` dön, log'a `[uyari]` yaz.

**0.3 `.bos` TTL + tazeleme** (B3)
- `BOS_TTL = 30 * 86400`. `mtime` bu süreyi geçtiyse `.bos` yok say.
- `?yenile=1` sorgu parametresi hem `.bos` hem karo önbelleğini atlar.
- `0 <= z <= 22`, `0 <= x < 2**z`, `0 <= y < 2**z`; değilse `400`.

**0.4 Anahtarları yapılandırmaya taşı**
- `.env` benzeri basit bir dosya (ör. `ayar.env`) veya ortam değişkeni: `HGM_API_KEY`, `HGM_WS_KEY`, `HGM_HARITA_KEY`, `PORT`.
- Anahtar yoksa açılışta **anlaşılır hata** ver (hangi değişken eksik).
- `.env`/`ayar.env` `git`'e eklenmesin; `ayar.env.ornek` ekle.

**0.5 README'yi kodla eşitle** (B4)
- `BENIOKU.md`'deki eşzamanlılık/hız/403 süreleri kodla birebir aynı olsun.
- "Neden vekil" bölümünü düzelt: Referer zorunluluğu yalnız `webservis/*` için; `Layers/*` CORS açık; gerçek gerekçeler önbellek + tek biçimli adres + 403 koruması.

**Kabul kriterleri (Paket 0):**
- `GET /sunucu.py` → 404 · `GET /sunucu.log` → 404 · `GET /onbellek/` → 404 · `GET /` → 200 · `GET /leaflet/leaflet.js` → 200
- `HEAD /t/temel/6/38/24` → 200 ve `Content-Type: image/png`
- Bozuk gövde senaryosu: `502`, önbellekte dosya oluşmamış
- `GET /t/temel/6/38/24?yenile=1` → HGM'ye yeniden gider
- `GET /t/temel/99/0/0` → 400
- Anahtar eksikken `python sunucu.py` → anlaşılır hata, çökme yok

### PAKET 1 — Dayanıklılık ve testler

**1.1 Hız sınırı** (B4)
- Katman başına token bucket: varsayılan **8 karo/sn**, kapasite 16.
- `ESZAMANLI`'yı 2'ye çek ve **ölç**: soğuk karo gecikmesi 1,0-2,0 sn'den düşüyor mu? Düşmüyorsa 4'ü dene, hangisi iyiyse onu bırak ve sonucu yorum olarak yaz.

**1.2 403 devre kesici, tüm host'lar** (B7)
- Ardışık 3 × 403 → katmanı `BEKLEME_403` saniye kapat.
- `200` gelince sayaç sıfırlansın.
- `503` yanıtına `Retry-After` başlığı ekle.

**1.3 429/5xx yeniden deneme** (B8)
- En çok 3 deneme, üstel geri çekme (0,5 sn → 1 sn → 2 sn) + jitter.
- `429`/`503` yanıtındaki `Retry-After` varsa ona uy.

**1.4 3xx takibi** (B5)
- En çok 3 yönlendirme; `Location` yoksa `502`; aşılırsa `502`.

**1.5 HEAD/OPTIONS** (B6)
- `HEAD`: gövdesiz, aynı başlıklar, aynı durum kodu (karo için HGM'ye gitmeden önbellekten).
- `OPTIONS`: `204` + `Allow: GET, HEAD, OPTIONS` + CORS başlıkları.

**1.6 Windows port çakışması** (B11)
- Windows'ta `SO_EXCLUSIVEADDRUSE` kullan; port doluysa `Port 8833 zaten kullanımda` deyip çık.
- Diğer platformlarda `SO_REUSEADDR` kalsın.

**1.7 Gözlemlenebilirlik** (B14)
- Log satırları: `ISO8601 zaman | seviye | olay | ayrıntı`. `[yavas]` satırlarında da zaman olsun.
- `GET /saglik` → `{"durum":"ayakta","katman":10,"onbellek_mb":216.5}`
- `GET /istatistik` → isabet/ıskaca/upstream hata sayıları, p50/p95 gecikme.

**1.8 Testler** (B14)
- `tests/` klasörü, `pytest` (yoksa `unittest`).
- Sahte upstream: yerel `http.server` ile PNG/404/403/bozuk gövde/5xx taklidi.
- En az 10 test: önbellek isabeti · 404→`.bos` · `.bos` TTL · bozuk gövde reddi · aralık doğrulaması · 403 devre kesici · 3xx takibi · HEAD · statik beyaz liste · eşzamanlı aynı karo (tek upstream isteği).
- Testler HGM'ye **hiç istek atmamalı**.

**1.9 Sürüm kontrolü**
- `git init`, `.gitignore` (`onbellek/`, `*.log`, `ayar.env`, `__pycache__/`, `.pytest_cache/`), ilk commit.
- `onbellek/` commit edilmemeli (216 MB).

**Kabul kriterleri (Paket 1):**
- `pytest -q` → tümü geçer, hiçbir test ağa çıkmaz
- `python sunucu.py` iki kez çalıştırıldığında ikincisi anlaşılır hata verir
- `curl -I http://127.0.0.1:8833/t/temel/6/38/24` → 200
- `/istatistik` gerçek sayılar döner

### PAKET 2 — Önbellek ve arayüzler (yeni bağımlılık ekleme)

- **2.1** Önbellek boyut sınırı (varsayılan 3 GB) + LRU tahliye (`mtime` yeterli). Sınır aşılınca en eski karolar silinsin, log'lansın.
- **2.2** `ETag` + `If-None-Match` → `304` (karo `mtime`+boyut'tan üret).
- **2.3** `/katmanlar.json`'a `bounds` (Türkiye: `[35.8, 25.6, 42.2, 44.8]`), `attribution`, `format` alanları ekle.
- **2.4** `GET /tms/<katman>/{z}/{x}/{y}.png` — TMS (y ekseni ters) uç noktası; QGIS için.
- **2.5** `GET /style.json` — MapLibre'nin doğrudan tüketebileceği raster stil üret.
- **2.6** `pyproject.toml` + `README` güncelle.

### PAKET 3 — İstemci (yalnız 0-2 bittikten sonra)

- **3.1** Göreli adres kullan: `k.url.replace(/^https?:\/\/[^/]+/, "")`. Alt alan adı hilesini kaldır.
- **3.2** Permalink: `#z/lat/lon`; açılışta oku, `moveend`'de yaz.
- **3.3** `localStorage`'da HTML değil `k.id` sakla.
- **3.4** Katman opaklığı kaydırıcısı, ölçek, tam ekran.
- **3.5** Hata göstergesi `503` (HGM kapalı) ile `404` (karo yok) ayrımını yapsın.
- **3.6** JS'i `app.js`'e, CSS'i `style.css`'e ayır.

## 5. Kod kuralları

- **Mevcut üslubu koru**: Türkçe tanımlayıcılar (`karo_getir`, `_kapali_bitis`, `gonder`), Türkçe docstring'ler, tek dosya yapısı (Paket 3'e kadar).
- **Yeni bağımlılık yok** (Paket 0-2). Yalnız standart kütüphane. Paket 3'te de yok.
- **Atomik yazma korunmalı**: `gecici.replace(dosya)` deseni.
- **HTTP sözleşmesi değişmemeli**: `/t/<katman>/{z}/{x}/{y}` biçimi, `200 + image/png`, `CORS: *` — Leaflet istemcisi bozulmasın.
- **`onbellek/` ve `rea-kanit/` içeriğine dokunma.**
- Her değişiklikten sonra sunucuyu yeniden başlatıp test et; çalışan bir örnek varsa önce onu durdur (port çakışması Windows'ta sessiz olabilir).
- Türkçe yorum yaz: neden yapıldığını anlat, ne yapıldığını değil.

## 6. Yapma listesi

- ❌ Sıfırdan yeniden yazma; mevcut yapıyı evrimleştir.
- ❌ FastAPI/Flask/aiohttp gibi çerçeve ekleme (Paket 2'de tartışılır, kendin karar verme).
- ❌ Karoları internete açma, herkese açık yayın için yapılandırma.
- ❌ Anahtarları commit etme, log'a yazma, hata mesajında gösterme.
- ❌ HGM'ye test sırasında gerçek istek atma (testler sahte upstream kullanmalı).
- ❌ `onbellek/` silme veya taşıma.
- ❌ Vektör karo (`/CPbf`) entegrasyonu — P3 dışı, kapsam dışı.

## 7. REA sonuçlarının koda yansıması

`rea-kanit/` klasöründe bir ölçüm var: 24.11.2026'da HGM Atlas'ın 137 isteği yakalandı.

- `hgm-ag.json` — tam kayıt (bugünkü **referans taban**)
- `hgm-ag-tekil.json` — tek kayıt biçimi
- `hgm-ag-senaryo.json` — tekrar üretme tarifi

**Bu dosyaları değiştirme.** İşin bitince, ayrı bir küçük görev olarak:

**`araclar/hgm-denetim.ps1`** yaz (PowerShell, ~150 satır):
1. Chrome'u `--remote-debugging-port=9222` + geçici profil ile başlat (crashpad hatası alırsa tam erişim gerektiğini logla).
2. `http://127.0.0.1:9222/json/new?https://atlas.harita.gov.tr/` ile sekme aç.
3. `rea capture-browser-scenario` çağır (senaryo: `rea-kanit/hgm-ag-senaryo.json`, `mode: connect`).
4. Çıkan kanıttan karo URL'lerini çıkar (`/Layers/` içerenler).
5. `sunucu.py`'deki `KATMANLAR` ile karşılaştır: eksik/fazla katman, değişen zoom sınırı.
6. `denetim/<tarih>.json` yaz; sapma varsa **çıkış kodu 1**.
7. Chrome'u kapat (yalnız kendi başlattığını).

Not: REA'yı bu projenin **çalışma zamanı bağımlılığı yapma**. Bekçi script'i REA kurulu değilse "REA bulunamadı, denetim atlandı" deyip 0 ile çıkmalı.

## 8. Teslim formatı

Bitirdiğinde şunu raporla:

1. **Değişen dosyalar** — her biri için tek satır ne değişti.
2. **Kabul kriterleri tablosu** — her kriter ✅/❌ ve nasıl doğrulandığı.
3. **Test sonucu** — `pytest -q` çıktısının özeti.
4. **Ölçüm** — Paket 0 öncesi/sonrası soğuk karo gecikmesi (varsa).
5. **Bilinen sınırlar** — yapamadığın veya emin olmadığın şeyler. Uydurma, açıkça yaz.
6. **Sonraki adım önerisi** — 1-2 madde.

Her paket sonunda kısa bir durum raporu ver ve **onay bekle**; hepsini tek seferde bitirmeye çalışma.

--- PROMPT SON ---

## Kullanım notu

- Prompt tek başına yeterli; Claude'un projeyi önce okumasına gerek yok, ama `sunucu.py`'yi açıp satır numaralarını doğrulamasını isteyebilirsiniz.
- Paket 0 yaklaşık 1,5 saatlik iş; Claude'a "yalnız Paket 0" diyerek başlatmak en güvenli yol.
- `rea-kanit/` klasörünü silmeyin: prompt'taki referans taban oradan okunuyor.
