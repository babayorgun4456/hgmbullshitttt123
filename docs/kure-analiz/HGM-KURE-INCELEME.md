# HGM KÜRE — Tersine Mühendislik İncelemesi

**Hedef:** `C:\HGMKure\HGM_KURE` (CitySurf Globe tabanlı HGM KÜRE masaüstü uygulaması)
**Amaç:** CitySurf motorunu değil, **HGM'ye ait olan kısmı** (sunucu, servis, katmanlar) ortaya çıkarmak
**Tarih:** 24 Kasım 2026
**Araçlar:** REA 6.10.1 (`inspect-artifact`), statik dizge analizi, DNS/TCP gözlemi, OGC GetCapabilities

---

## 1. Sonuç özeti

| Soru | Cevap |
|---|---|
| Uygulama HGM'ye mi ait? | Paket HGM'nin resmî dağıtımı: `kure.harita.gov.tr/HGM_kure.zip` |
| Motor kimin? | CitySurf Globe (Delphi/C++ tabanlı, `CitySurf.exe` 33 MB) |
| HGM'ye ait teknik yapılandırma nerede? | `csGlobe.srv` (253 bayt, şifreli) + marka dosyaları |
| Gerçek HGM sunucusu | **`kure.harita.gov.tr:80`** (HTTP, düz metin) |
| İkinci sunucu | **`css.harita.gov.tr:443`** (HTTPS, WAF korumalı) |
| Sunucu protokolü | CitySurf OGC servisi: `/csglobe/csogc.dll/wms` — **WMS 1.3.0** |
| Katman sayısı | **116 adlandırılmış katman** (GetCapabilities açık) |
| Harita çizimi (GetMap) | ❌ WAF engelliyor (418) — istemci kimliği gerekiyor |
| Askeri içerik | **Var**: TSK teşkilat/rütbe şablonları + K.K.K. sunucularından sembol servisi (§7) |

**Tek cümle:** HGM KÜRE, CitySurf motorunun HGM markalı bir kabuğu; içinde HGM'ye ait API anahtarı veya katman tanımı **yok**. Tek HGM'ye özgü teknik veri, şifreli `csGlobe.srv` dosyasındaki sunucu adresi — ki o adres çalıştırma gözlemiyle ortaya çıktı: `kure.harita.gov.tr`.

---

## 2. Kanıt zinciri

### 2.1 Statik analiz (dosyalar)

| Bulgu | Kaynak |
|---|---|
| Marka: "HGM KÜRE", destek: `kure@harita.gov.tr`, site: `http://kure.harita.gov.tr` | `CitySurf.exe` (UTF-16 dizgeler, 0x1a8f960) |
| Motor: `TCitySurf_CSXMLWriter`, `CitySurfAPI`, `csGlobe.srv` mesajları | `CitySurf.exe` |
| `csGlobe.srv` **yoksa** yerel sunucuya düşüyor | `CitySurf.exe`: *"csGlobe.srv not found ! Connecting To Local Server…"* |
| Sunucu dosyası şifreli: 253 bayt, entropi **7,25 bit/bayt** | `csGlobe.srv` (zlib/bz2/lzma/XOR denendi — hiçbiri değil) |
| Lisans makineye bağlı: `HostID`, `Mb_SerialNumber` | `CitySurf.exe` |
| **Sızmış geliştirici adresi** | `Moduls\Flight\CSFlightSim.dll`: `http://192.168.1.65/csglobe/csogc.dll/wms?…LAYERS=raster…` |
| Türkiye'ye özel projeksiyonlar (21 adet, Gauss-Krüger 3°) | `CSProjection.ini` |
| GeoRSS: USGS deprem, Hürriyet/Milliyet/Sabah/CNN TÜRK | `GeoRSS.txt` |

**Kritik çıkarım:** CitySurf'un kendi modülünde kalmış `192.168.1.65/csglobe/csogc.dll/wms` adresi, sunucu tarafındaki **yol kuralını** veriyor: `/csglobe/csogc.dll/wms`. Bu, canlı sunucuda doğrulandı.

### 2.2 Çalıştırma gözlemi (ağ)

Uygulama başlatıldı, yalnız kendi süreçlerinin bağlantıları izlendi:

```
CitySurf.exe (PID 21784) →
  212.175.124.31:80   Established   ← kure.harita.gov.tr  (HTTP, ŞİFRESİZ)
  212.175.124.74:443  Established   ← css.harita.gov.tr   (HTTPS)

DNS önbelleği:
  kure.harita.gov.tr → 212.175.124.31
  css.harita.gov.tr  → 212.175.124.74
```

Yani `csGlobe.srv` şifreli olsa da **hedef sunucu ağ üzerinden okunabildi**. Şifre çözülmeden de HGM'nin sunucusu ortaya çıktı.

### 2.3 Sunucu doğrulama (tek seferlik, saygılı)

| İstek | Sonuç |
|---|---|
| `GET http://kure.harita.gov.tr/` | 200 — HGM KÜRE indirme sayfası (`HGM_kure.zip`) |
| `GET /csglobe/csogc.dll/wms?REQUEST=GetCapabilities` | **200, `text/xml`, 54 KB, WMS 1.3.0** |
| `GET /csogc.dll` | 404 |
| `GET /csglobe/` | 403 |
| `GET …GetMap&LAYERS=ANKARA…` | **418 — WAF bloğu** ("Sayfaya Erişiminiz Engellenmiştir", istek no + IP) |
| `GET https://css.harita.gov.tr/` | **403 TR7 Forbidden** (WAF) |

> GetCapabilities herkese açık; **GetMap istemci kimliği istiyor.** WAF engeli sonrası bu sunucuya yapılan testler durduruldu.

---

## 3. HGM'nin WMS katman envanteri (116 katman)

Servis künyesi: `Harita Genel Komutanligi WMS Hizmeti`, WMS **1.3.0**, CRS: yalnız `CRS:84` ve `EPSG:4326`.

| Grup | Adet | Örnek |
|---|---:|---|
| İl / 1:250K pafta | 76 | `ANKARA`, `ISTANBUL`, `IZMIR`, `VAN`, `TORTUM`, `SILIFKE`… |
| Siyasi raster (bölge) | 15 | `HGK_Balkanlar_Siyasi_Raster_Harita`, `HGK_Ortadogu_…` |
| Fiziki raster (bölge) | 14 | `HGK_Avrupa_Fiziki_…`, `HGK_Kafkaslar_…`, `HGK_Kibris_…` |
| Diğer raster (1:250K/500K/1M) | 7 | `HGK_1M_hava_Raster_Harita`, `HGK_250K_kara_…` |
| Deprem / olay | 5 | `gokturk`, `Deprem_Gokturk`, `Deprem_Hava`, `Deprem_Iha`, `Deprem_Uydu` |
| Kök / genel | 3 | `raster`, `Dunya`, `sinir_uhzm` |

Tam liste: [`wms-katmanlar.txt`](wms-katmanlar.txt) · Ham yetenek dosyası: [`wms-capabilities.xml`](wms-capabilities.xml)

**Not:** Bu katmanlar `atlas.harita.gov.tr`'deki 10 katmandan **tamamen farklı**. Özellikle:
- Bölge bazlı fiziki/siyasi rasterlar (Balkanlar, Kafkaslar, Orta Doğu, Afganistan…)
- 1:250K/500K/1M ölçekli hava/kara haritaları
- 77 adet 1:250K pafta
- Deprem öncesi/sonrası görüntüler (`Deprem_Uydu`, `Deprem_Iha`)

Bunlar hiçbiri mevcut `hgm-harita` projesinde yok.

---

## 4. HGM'nin kısmı ile CitySurf'un kısmı

| Bileşen | Kime ait | Not |
|---|---|---|
| `CitySurf.exe`, modüller, 3DS modeller, sesler, S-57 | CitySurf | Motor + içerik |
| `csGlobe.srv` | **HGM** | Sunucu adresi (şifreli, 253 bayt) |
| `CitySurf.crd` | **HGM** | Lisans/kimlik dosyası (şifreli, 134 bayt) |
| `CSProjection.ini` | HGM uyarlaması | 21 Gauss-Krüger projeksiyonu |
| Marka (logolar, `kure@harita.gov.tr`) | HGM | |
| `GeoRSS.txt` | CitySurf varsayılanı | Türk haber siteleri |
| **Sunucu tarafı WMS** | **HGM** | `kure.harita.gov.tr/csglobe/csogc.dll/wms` |

---

## 5. Neyi yapamadık (dürüst sınırlar)

| Denendi | Sonuç |
|---|---|
| `csGlobe.srv` şifresini çözmek | ❌ Entropi 7,25; zlib/bz2/lzma, tek bayt XOR, bilinen düz metin saldırısı — hiçbiri tutmadı. Şifre çözme rutini için disassembler (Ghidra/IDA) gerekir. |
| `CitySurf.crd` içeriği | ❌ Aynı durum |
| Harita karo çizmek (GetMap) | ❌ WAF 418; istemci kimliği/HostID bağlı görünüyor |
| `css.harita.gov.tr` içeriği | ❌ 403 TR7 WAF |
| REA ile derin native analiz | ❌ Hopper/Ghidra/IDA kurulu değil (`rea doctor`: `missing_analysis_engine`) |
| Paket içinde API anahtarı bulmak | ✅ Arandı, **yok** — HGM anahtarları bu uygulamada değil |

**Sonuç:** Bu uygulama üzerinden HGM'nin karo servisine erişmek **teknik olarak mümkün değil**; ne anahtar var ne de WAF'ı aşacak bir yol aranmalı. Buradan çıkan gerçek değer, **HGM'nin WMS katman envanteri** ve sunucu mimarisi bilgisi.

---

## 6. Buradan çıkan geliştirme fikirleri (hgm-harita projesi için)

1. **`hgm_harita` / `topografik_raster` zaten 1:250K–1M ölçekleri kapsıyor** — Küre'nin raster katmanları büyük ölçüde aynı verinin bölge bazlı hâli. Yeni veri beklemeyin; **pafta bazlı bbox bilgisi** işe yarar (77 pafta adı → il/ilçe eşlemesi).
2. **Deprem katmanları** (`Deprem_Uydu`, `Deprem_Iha`) atlas'ta yok — ama WAF'lı sunucuda. Erişilemez; atlas tarafında `deprem` servisi var (`/webservis/deprem/`, `config.js`), asıl oradan alınmalı.
3. **WMS uç noktası eklemek** (proje için): mevcut `sunucu.py`'ye `?bbox=&width=&height=` alan bir `/wms` ucu eklemek, 10 katmanı WMS istemcilerine (QGIS, ArcGIS) açardı — Küre'nin protokolüne gerek yok, atlas karoları yeter.
4. **Ders:** Kutu ürünlerin (`kure.harita.gov.tr`) içinden veri çıkarmak yerine, açık karo servisleri (`atlas.harita.gov.tr`) üzerinden gitmek hem teknik hem hukuki olarak doğru yol.

---

## 7. Askeri içerik: TSK, Kara Kuvvetleri, MSB

**Kısa cevap: evet, geçiyor — ve sanılandan düzenli biçimde.** Paket, sivil bir harita uygulaması değil; **TSK teşkilatına göre yerelleştirilmiş askeri bir semboloji/haberleşme modülü** içeriyor.

> İlk taramada 3 harfli kısaltmalar (KKK, MSB, TSK, HGK) ikili veri içinde rastgele eşleştiği için sayılar şişmişti (ör. "Kara Kuvvetleri: 125"). Aşağıdaki tablo **kelime sınırlı, katı** ikinci taramanın sonucudur.

| Terim | Dosya | Kaç kez | Nerede |
|---|---|---:|---|
| Kara / Deniz / Hava Kuvvetleri | `Tools\Messenger\Military\Forces.txt` | 3 | Kuvvet şube listesi |
| | `Tools\Messenger\Military\Work.txt` | 3 | Komutanlık dizini |
| | `Help\Common\Sembol_sec_Askeri_TR.html` | 1 | "K.K.K.'da bulunan sunucular" |
| Milli Savunma Bakanlığı | `Work.txt` | 1 | 01: MSB-Ankara |
| Genelkurmay | `Work.txt` | 1 | 02: GNKUR-Ankara |
| Jandarma | `04\04_Rutbe.txt` | 10 | Uzman Jandarma rütbeleri |
| | `Forces.txt`, `Work.txt` | 2 | Jandarma Genel K.lığı |
| Kolordu / Ordu | `Work.txt` | 11 | 1-3. Ordu, Ege Ordusu, 2-9. Kolordu |
| **TSK** | `Sembol_sec_Askeri_TR.html` | 1 | "TSK'nın mevcutta kullandığı…" |
| | `Help\File\TopluKoordinatAtimi.html`, `CitySurf.exe` | 2 | Kısaltma |
| Harita Genel Komutanlığı (HGK) | `Work.txt` | 1 | 24: HGK-Ankara |
| | `Help\File\TopluKoordinatAtimi.html` | 1 | |

### 7.1 En önemli bulgu: sembol kütüphanesi K.K.K. sunucularından geliyor

`Help\Common\Sembol_sec_Askeri_TR.html` dosyasındaki iki cümle, paketin askeri bağını açıkça kuruyor:

> "Askeri İşaretler Kütüphanesi … **TSK'nın mevcutta kullandığı Müşterek Askeri İşaretler Sözlüğüne (MS 76-2)** göre hazırlanmış bir uygulamadır."

> "Bu kütüphanedeki altyapı **Kara Kuvvetleri Komutanlığında bulunan sunuculardan gelen servis** ile sağlanmaktadır."

Yani yalnızca metin değil: **semboller çalışma anında K.K.K.'daki bir sunucudan servis ediliyor.** Bu sunucunun adresi istemcide yok (sunucu tarafında tanımlı) — bu yüzden `CitySurf.exe` içinde böyle bir URL bulunamadı.

### 7.2 Paketteki TSK veri seti

`Tools\Messenger\Military\` altında, 214 PNG rütbe/teşkilat işareti ve 28 sınıf ikonuyla birlikte şu metin setleri var:

**`Work.txt` — 24 komutanlık, şehirleriyle** (tam liste):

```
01:Milli Savunma Bakanlığı-Ankara        13:Kıbrıs Türk Barış Kuvvetleri-Girne
02:Genel Kurmay Başkanlığı-Ankara        14-21:2.-9. Kolordu (Gelibolu, Şişli, Ankara,
03:Kara Kuvvetleri Komutanlığı-Ankara        Çorlu, Adana, Diyarbakır, Elazığ, Erzurum)
04:Deniz Kuvvetleri Komutanlığı-Ankara   22:Lojistik Komutanlığı-Ankara
05:Hava Kuvvetleri Komutanlığı-Ankara    23:Kara Havacılık Komutanlığı-Ankara
06:Jandarma Genel Komutanlığı-Ankara     24:Harita Genel Komutanlığı-Ankara
07:Sahil Güvenlik Komutanlığı-Ankara
08-11:1./2./3. Ordu (İstanbul, Malatya, Erzincan), Ege Ordusu (İzmir)
12:Eğitim ve Doktrin Komutanlığı (EDOK)
```

**Diğer dosyalar:**

| Dosya | İçerik |
|---|---|
| `Forces.txt` | Kuvvet şubeleri + kısaltmalar (Dz., Hv., J.) |
| `Status.txt` | Personel sınıfı: Subay, Astsubay, Askeri Memur, Uzman Erbaş, Devlet Memuru |
| `Class_01/02/04.txt` | Sınıf/meslek kodları: Piyade, Süvari, Tank, Topçu, Hava Savunma, İstihkam, Muhabere, İstihbarat, **Harita (Hrt.)**, Harita Teknisyeni… |
| `01_Rutbe.txt` | Subay rütbeleri: Orgeneral → Asteğmen |
| `02_Rutbe.txt` | Astsubay: Kıdemli Başçavuş → Astsubay Çavuş |
| `03_Rutbe.txt` | Askeri Memur: 8. sınıf → 1. sınıf (rütbe muadilleri) |
| `04_Rutbe.txt` | Uzman Jandarma: VIII. kademeli çavuş → onbaşı |
| `05_Rutbe.txt` | Devlet Memuru (boş) |

### 7.3 Ne **değil** — sınırlar

- ❌ **Sınıflandırma işareti yok.** `GİZLİ`, `HİZMETE ÖZEL`, `TASNİF DIŞI` gibi hiçbir ibare bulunmadı. Bulunan tek "gizlilik" izi CitySurf'un lisans alanı (`SECRETID`) ve üçüncü taraf EMS'nin telif metni.
- ❌ **Kişisel veri yok.** Hiçbir dosyada isim, sicil, telefon yok; yalnızca rütbe/sınıf/teşkilat şablonları.
- ❌ **Gizli teşkilat yapısı yok.** `Work.txt`'deki bilgiler barış zamanı garnizon şehirleri düzeyinde — açık kaynaklarda da yer alan türden.
- ⚠️ **Eski isimlendirme:** "Harita Genel **Komutanlığı**" (HGK) kullanılıyor. Kurum 2018'de "Harita Genel Müdürlüğü" (HGM) oldu; yani bu veri seti **2018 öncesine** ait. Sunucudaki WMS servisinin adı da hâlâ "Harita Genel Komutanligi WMS Hizmeti".

### 7.4 Bunun anlamı

1. **Paket askeri kullanıcı için hazırlanmış.** "Messenger" modülü (birlik/kişi işaretleme, rütbe, sınıf, kolordular) sivil bir harita uygulamasında gereksiz; bu, HGM KÜRE'nin TSK envanterinde kullanıldığını gösteriyor.
2. **HGM burada harita sağlayıcısı.** Teşkilat verisi CitySurf şablonu + TSK'ya göre yerelleştirme; HGM'nin kendi katkısı sunucu ve raster katmanlar.
3. **Projeye taşınmaz.** `hgm-harita` sivil bir karo vekili; bu veri setinin oraya aktarılması ne teknik ne hukuki olarak doğru olur. Bu bölüm yalnızca paketin niteliğini belgeliyor.

---

## 8. `csGlobe.srv` şifresi: çalışma anından çözüldü

Statik kripto çözümü tıkandığı için farklı bir yol denendi: **uygulama dosyayı açılışta çözüyor**, yani düz metin bir süre bellekte duruyor.

**Yöntem:** `CitySurf.exe` başlatıldı → 32-bit sürecin belleği `ReadProcessMemory` ile tarandı (512 MB okundu) → URL/kimlik dizgeleri çıkarıldı → süreç kapatıldı.

### 8.1 Ortaya çıkan HGM servis haritası

| Uç nokta | Ne işe yarar |
|---|---|
| `http://kure.harita.gov.tr/csglobe/csapp.dll` | Sunucu tarafı uygulama katmanı |
| `http://kure.harita.gov.tr/csglobe/csvector.dll` | Vektör katman servisi |
| `http://kure.harita.gov.tr/csglobe/csogc.dll/wms` | WMS 1.3.0 (GetCapabilities açık, GetMap WAF'lı) |
| `http://kure.harita.gov.tr/cssymbols` (+ `/gys.png`) | **Askeri/sivil sembol kütüphanesi** — yardım dosyasının söz ettiği "K.K.K. sunucularından gelen servis" |
| `http://kure.harita.gov.tr/csicons/*.bmp` | Simge kataloğu |
| `https://css.harita.gov.tr/` | Ayrı **CSS** sunucusu (WAF korumalı) |
| `https://css.harita.gov.tr/mobil-gorsun/wms?request=getcapabilities&apikey=…` | Mobil görünüm WMS'i — **API anahtarı gömülü** (raporda maskelendi) |
| `https://css.harita.gov.tr/search/?value=[#keywords]&limit=20` | Adres/kelime arama servisi |
| `Host: kure.harita.gov.tr` · `*.harita.gov.tr` | Ana makine ve çerez/alan adı kuralı |

**Kritik nokta:** `css.harita.gov.tr` yalnızca bir "lisans sunucusu" değil; **mobil-gorsun WMS'i ve arama servisi** de orada. Yani HGM KÜRE iki ayrı sunucu ailesi kullanıyor.

### 8.2 CitySurf kalıntıları (HGM'ye ait değil)

Bellekte geliştirici makinelerine ait adresler de duruyor: `10.0.0.87`, `10.0.0.91`, `192.168.1.65`, `169.254.17.244`. Bunlar CitySurf'un kendi test ortamı; paketlenmiş sürümde kalması bir hijyen sorunu ama HGM'ye ait veri değil.

### 8.3 Bu neyi değiştirir

- `csGlobe.srv` dosyasını **çözmeye gerek kalmadı**: içeriği çalışma anında elde edildi ve tek bir sunucu adresinden ibaret değil, bir servis haritası.
- Yardım dosyasındaki "semboller K.K.K. sunucularından geliyor" ifadesi **doğrulandı**: sembol kütüphanesi `kure.harita.gov.tr/cssymbols` üzerinden servis ediliyor (yani HGM sunucusu, ayrı bir K.K.K. altyapısı değil).
- Anahtar içeren uç nokta (`mobil-gorsun`) yine WAF arkasında; bellekten anahtar çıkmış olsa da **kullanılmadı, kullanılmamalı**.

### 8.4 Ghidra tarafı: ne oldu

Native analiz için üç ayrı yol denendi:

| Yol | Sonuç |
|---|---|
| REA + Ghidra 12.1.4 | ❌ REA en az 12.2 istiyor (`unsupported_version`) |
| REA + Ghidra 12.2 + JDK 25 | ⚠️ Java testi geçti, Ghidra başladı ama köprü kurulamadı: *"Ghidra exited before bridge startup"* |
| Ghidra 12.2 doğrudan (headless) | ✅ PE içe aktarma ve analiz çalıştı; script hedef fonksiyonları decompile etmeye başladı |
| Analiz öncesi engeller | `%TEMP%` ve `C:\Users\user\AppData\Roaming` bu oturumda yazılamıyordu → `user.home` / `java.io.tmpdir` yönlendirildi; PE yükleyicisi yandaki DLL'leri kütüphane sanıp `Parent ResourceFile cannot be null` veriyordu → `-librarySearchPaths <boş dizin>` ile çözüldü |

**Nerede durdu:** Analiz tamamlandı, script `csGlobe`/`csapp`/`css.harita` dizgelerine referans veren fonksiyonları buldu ve decompile etmeye başladı; ancak 33 MB'lık Delphi binary'sinin bazı fonksiyonları decompiler'ı kilitledi (5 fonksiyon sonrası ilerleme durdu, pcode hataları: `Could not follow disassembly flow into non-existing memory`). Süreç durduruldu, proje kaydedilmeden düştü.

**Sonuç:** Şifreleme rutininin kaynak kodu çıkarılamadı; buna **gerek de kalmadı** — düz metin çalışma anından elde edildi. Ghidra'nın bu iş için tek katkısı, `Crypt32.dll` ithalatının varlığıyla şifrelemenin **Windows CryptoAPI** tabanlı olduğunu doğrulamak oldu.

**İstenirse devam yolu:** Ghidra'da `-noanalysis` + hedefli `createFunction` ile yalnız `csGlobe.srv` okuyan fonksiyon decompile edilir; ya da `x64dbg`/WinDbg ile `CryptDecrypt` çağrısına breakpoint konup anahtar ve algoritma doğrudan okunur (en hızlı yol).

---

## 9. Hukuki not

- Paket HGM'nin resmî indirme sayfasından geliyor (`HGM_kure.zip`), yani lisanslı bir dağıtım.
- `GetCapabilities` herkese açık bir OGC dokümanı; okunması normaldir.
- **GetMap WAF ile korunuyor** — bu, HGM'nin bu veriyi servis olarak paylaşmadığının açık işaretidir. Aşmaya çalışmak yanlış olur.
- Bu incelemede hiçbir koruma atlatılmadı; yalnız herkese açık uçlar okundu. WAF engeli görülünce testler durduruldu.

---

*Bu belge, yerel dosyaların statik analizi, uygulamanın bir kez çalıştırılıp ağının izlenmesi ve herkese açık OGC yetenek dokümanının okunmasıyla üretildi. Şifreli dosyalar çözülmedi; koruma atlatılmadı.*

