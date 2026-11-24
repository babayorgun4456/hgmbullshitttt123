"""sunucu.py testleri. HGM'ye hiç istek atılmaz: bütün istekler yerel sahte sunucuya gider,
HTTPS bağlantısı da engellenir (yanlışlıkla gerçek HGM'ye gidilirse test patlar).

Sahte HGM, karo adresindeki x değerine göre davranır:
  x=1 geçerli PNG          x=2 404               x=3 403
  x=4 200 + HTML gövde     x=5 önce 500 sonra PNG
  x=6 302 -> x=1           x=7 302, Location yok  x=8 0,3 sn bekleyip PNG
  x=9 önce 429 (Retry-After: 0) sonra PNG        x=10 kendine 302 (sonsuz)
"""
import collections
import http.client
import json
import http.server
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sunucu  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
TEST_ENC = "AbC/d+e="
SAHTE_STIL = {
    "version": 8, "glyphs": "https://atlas.harita.gov.tr/style/fonts/{fontstack}/{range}.pbf",
    "sprite": "https://atlas.harita.gov.tr/style/sprites/sprite",
    "sources": {
        "composite": {"type": "vector", "tiles": ["https://atlas1.harita.gov.tr/CPbf/{z}/{x}/{y}.pbf?enc=AbC%2Fd%2Be%3D"]},
        "atlas_kara_orman": {"type": "raster", "tiles": ["https://atlas.harita.gov.tr/tile/atlas_kara_orman/{z}/{x}/{y}.png"]},
        "yolorta": {"type": "raster", "tiles": ["https://atlas.harita.gov.tr/webservis/harita/yolorta_varsayilan/{z}/{x}/{y}.png?apikey=x"]},
    },
    "layers": [
        {"id": "background", "type": "background"},
        {"id": "kara_raster", "type": "raster", "source": "atlas_kara_orman"},
        {"id": "karalar", "type": "fill", "source": "composite", "source-layer": "karalar", "minzoom": 7},
        {"id": "corona", "type": "fill", "source": "composite", "source-layer": "corona"},
        {"id": "yolorta", "type": "raster", "source": "yolorta"},
    ],
}


class SahteHGM(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    sayac = collections.Counter()
    kilit = threading.Lock()

    def log_message(self, *a):
        pass

    def yanit(self, kod, govde=b"", baslik=None):
        self.send_response(kod)
        for k, v in (baslik or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def do_GET(self):
        yol = self.path.split("?")[0]
        with self.kilit:
            self.sayac[yol] += 1
            kacinci = self.sayac[yol]
        if yol.startswith("/style/"):
            if yol == "/style/corona.json":
                return self.yanit(200, json.dumps(SAHTE_STIL).encode())
            if yol == "/style/sprites/sprite.json":
                return self.yanit(200, b"{}")
            return self.yanit(404, b"yok")
        parca = yol.split("/")
        z, x = parca[-3], int(parca[-2])
        y = parca[-1].split(".")[0]
        if x == 1:
            return self.yanit(200, PNG, {"Content-Type": "image/png"})
        if x == 2:
            return self.yanit(404, b"yok")
        if x == 3:
            return self.yanit(403, b"yasak")
        if x == 4:
            return self.yanit(200, b"<html>bakim</html>" * 10, {"Content-Type": "image/png"})
        if x == 5:
            return self.yanit(500, b"hata") if kacinci == 1 else self.yanit(200, PNG)
        if x == 6:
            return self.yanit(302, b"", {"Location": "/".join(parca[:-2] + ["1", parca[-1]])})
        if x == 7:
            return self.yanit(302, b"")
        if x == 8:
            time.sleep(0.3)
            return self.yanit(200, PNG)
        if x == 9:
            return self.yanit(429, b"", {"Retry-After": "0"}) if kacinci == 1 else self.yanit(200, PNG)
        if x == 10:
            return self.yanit(302, b"", {"Location": yol})
        return self.yanit(500, b"bilinmeyen")


class _HttpsYasak(http.client.HTTPSConnection):
    def connect(self):
        raise AssertionError(f"test gercek bir HTTPS sunucusuna ({self.host}) gitmeye calisti")


class Temel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ust = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SahteHGM)
        threading.Thread(target=cls.ust.serve_forever, daemon=True).start()
        cls.eski_https = http.client.HTTPSConnection
        http.client.HTTPSConnection = _HttpsYasak
        sunucu.UST_ADRES = f"http://127.0.0.1:{cls.ust.server_address[1]}"
        sunucu.GERI_CEKME_TABAN = 0.01
        cls.s4, _ = sunucu.baslat(port=0, ipv6=False)
        threading.Thread(target=cls.s4.serve_forever, daemon=True).start()
        cls.adres = f"http://127.0.0.1:{cls.s4.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.s4.shutdown()
        cls.ust.shutdown()
        http.client.HTTPSConnection = cls.eski_https

    def setUp(self):
        self.klasor = Path(tempfile.mkdtemp())
        sunucu.ONBELLEK = self.klasor
        SahteHGM.sayac.clear()
        sunucu._ardisik_403.clear()
        for ad in sunucu.KATMANLAR:
            sunucu._kapali_bitis[ad] = 0.0
        sunucu.ISTATISTIK = sunucu.Istatistik()

    def tearDown(self):
        shutil.rmtree(self.klasor, ignore_errors=True)

    def ust_sayisi(self, x, y=7, z=5):
        return sum(v for k, v in SahteHGM.sayac.items() if k.endswith(f"/{z}/{x}/{y}.png"))

    def iste(self, yol, metod="GET"):
        req = urllib.request.Request(self.adres + yol, method=metod)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()


class KaroTestleri(Temel):
    def test_onbellek_isabeti_hgmye_ikinci_kez_gitmez(self):
        self.assertEqual(sunucu.karo_getir("temel", 5, 1, 7)[0], 200)
        self.assertEqual(sunucu.karo_getir("temel", 5, 1, 7)[0], 200)
        self.assertEqual(self.ust_sayisi(1), 1)
        self.assertTrue((self.klasor / "temel/5/1/7.png").exists())

    def test_404_bos_kaydi_olusturur_ve_tekrar_sorulmaz(self):
        self.assertEqual(sunucu.karo_getir("temel", 5, 2, 7)[0], 204)
        self.assertEqual(sunucu.karo_getir("temel", 5, 2, 7)[0], 204)
        self.assertEqual(self.ust_sayisi(2), 1)
        self.assertTrue((self.klasor / "temel/5/2/7.bos").exists())

    def test_bos_kaydi_suresi_dolunca_hgmye_yeniden_sorulur(self):
        sunucu.karo_getir("temel", 5, 2, 7)
        bos = self.klasor / "temel/5/2/7.bos"
        os.utime(bos, (time.time() - sunucu.BOS_TTL - 10,) * 2)
        sunucu.karo_getir("temel", 5, 2, 7)
        self.assertEqual(self.ust_sayisi(2), 2)

    def test_bozuk_govde_reddedilir_ve_diske_yazilmaz(self):
        self.assertEqual(sunucu.karo_getir("temel", 5, 4, 7)[0], 502)
        self.assertEqual(list(self.klasor.rglob("*.*")), [])

    def test_yenile_onbellegi_atlar(self):
        sunucu.karo_getir("temel", 5, 1, 7)
        durum, _, _ = self.iste("/t/temel/5/1/7?yenile=1")
        self.assertEqual(durum, 200)
        self.assertEqual(self.ust_sayisi(1), 2)

    def test_403_devre_kesici_uc_ardisiktan_sonra_acilir(self):
        for _ in range(3):
            sunucu.karo_getir("temel", 5, 3, 7)
        self.assertEqual(self.ust_sayisi(3), 3)
        durum, baslik, _ = self.iste("/t/temel/5/3/7")
        self.assertEqual(durum, 503)
        self.assertGreaterEqual(int(baslik["Retry-After"]), 1)
        self.assertEqual(self.ust_sayisi(3), 3, "kapaliyken HGM'ye gidilmemeli")
        # başka katman etkilenmez
        self.assertEqual(sunucu.karo_getir("uydu", 5, 1, 7)[0], 502)  # uydu jpg bekler, PNG gelir

    def test_403_sayaci_200_ile_sifirlanir(self):
        sunucu.karo_getir("temel", 5, 3, 7)
        sunucu.karo_getir("temel", 5, 3, 7)
        sunucu.karo_getir("temel", 5, 1, 7)
        sunucu.karo_getir("temel", 5, 3, 7)
        self.assertEqual(sunucu.kapali_kalan("temel"), 0.0)

    def test_yonlendirme_izlenir(self):
        self.assertEqual(sunucu.karo_getir("temel", 5, 6, 7)[0], 200)
        self.assertEqual(sunucu.karo_getir("temel", 5, 7, 7)[0], 502)
        self.assertEqual(sunucu.karo_getir("temel", 5, 10, 7)[0], 502)
        self.assertEqual(self.ust_sayisi(10), sunucu.EN_COK_YONLENDIRME + 1)

    def test_5xx_ve_429_yeniden_denenir(self):
        self.assertEqual(sunucu.karo_getir("temel", 5, 5, 7)[0], 200)
        self.assertEqual(self.ust_sayisi(5), 2)
        self.assertEqual(sunucu.karo_getir("temel", 5, 9, 7)[0], 200)
        self.assertEqual(self.ust_sayisi(9), 2)

    def test_ayni_karoya_eszamanli_istek_hgmye_tek_gider(self):
        sonuc = []
        isler = [threading.Thread(target=lambda: sonuc.append(sunucu.karo_getir("temel", 5, 8, 7)[0]))
                 for _ in range(8)]
        for t in isler:
            t.start()
        for t in isler:
            t.join()
        self.assertEqual(sonuc, [200] * 8)
        self.assertEqual(self.ust_sayisi(8), 1)


class HttpTestleri(Temel):
    def test_aralik_disi_koordinat_400(self):
        for yol in ("/t/temel/99/0/0", "/t/temel/3/8/0", "/t/temel/3/-1/0", "/t/temel/a/b/c"):
            self.assertEqual(self.iste(yol)[0], 400, yol)
        self.assertEqual(self.iste("/t/yok/1/0/0")[0], 404)

    def test_statik_beyaz_liste(self):
        for yol in ("/sunucu.py", "/ayar.env", "/BENIOKU.md", "/onbellek/", "/leaflet/",
                    "/leaflet/../sunucu.py", "/leaflet/%2e%2e/sunucu.py", "/tests/test_sunucu.py"):
            self.assertEqual(self.iste(yol)[0], 404, yol)
            self.assertEqual(self.iste(yol, "HEAD")[0], 404, yol)
        for yol in ("/", "/index.html", "/leaflet/leaflet.js", "/katmanlar.json"):
            self.assertEqual(self.iste(yol)[0], 200, yol)

    def test_head_govdesiz_ayni_baslik(self):
        sunucu.karo_getir("temel", 5, 1, 7)
        durum, baslik, govde = self.iste("/t/temel/5/1/7", "HEAD")
        self.assertEqual((durum, baslik["Content-Type"], govde), (200, "image/png", b""))
        self.assertEqual(int(baslik["Content-Length"]), len(PNG))

    def test_options_204(self):
        durum, baslik, _ = self.iste("/t/temel/5/1/7", "OPTIONS")
        self.assertEqual(durum, 204)
        self.assertEqual(baslik["Allow"], "GET, HEAD, OPTIONS")
        self.assertEqual(baslik["Access-Control-Allow-Origin"], "*")

    def test_bos_karo_seffaf_png_doner(self):
        durum, baslik, govde = self.iste("/t/temel/5/2/7")
        self.assertEqual((durum, baslik["Content-Type"]), (200, "image/png"))
        self.assertEqual(govde, sunucu.BOS_PNG)

    def test_saglik_ve_istatistik(self):
        self.iste("/t/temel/5/1/7")
        self.iste("/t/temel/5/1/7")
        saglik = __import__("json").loads(self.iste("/saglik")[2])
        self.assertEqual((saglik["durum"], saglik["katman"]), ("ayakta", len(sunucu.KATMANLAR)))
        ist = __import__("json").loads(self.iste("/istatistik")[2])
        self.assertEqual((ist["sayac"]["isabet"], ist["sayac"]["iskaca"]), (1, 1))
        self.assertIsNotNone(ist["hgm_gecikme_ms"]["p95"])

    def test_dolu_port_hata_verir(self):
        with self.assertRaises(OSError):
            sunucu.baslat(port=self.s4.server_address[1], ipv6=False)


class VektorTestleri(Temel):
    def setUp(self):
        super().setUp()
        self.eski_enc = dict(sunucu.ENC_KATMAN)
        self.eski_katman = sunucu.KATMANLAR.get("hgm_vektor")
        sunucu.ENC_KATMAN.clear()
        sunucu.ENC_KATMAN[TEST_ENC] = "hgm_vektor"
        sunucu.KATMANLAR["hgm_vektor"] = ("v", "atlas1.harita.gov.tr", "/CPbf/{z}/{x}/{y}.pbf?enc=x", "pbf", 0, 21, "vektor")
        sunucu._kilitler.setdefault("hgm_vektor", threading.Semaphore(4))
        sunucu._kovalar.setdefault("hgm_vektor", sunucu.Kova(1000, 1000))
        sunucu._kapali_bitis.setdefault("hgm_vektor", 0.0)

    def tearDown(self):
        sunucu.ENC_KATMAN.clear()
        sunucu.ENC_KATMAN.update(self.eski_enc)
        if self.eski_katman:
            sunucu.KATMANLAR["hgm_vektor"] = self.eski_katman
        else:
            sunucu.KATMANLAR.pop("hgm_vektor", None)
        super().tearDown()

    def test_pbf_govde_dogrulamasi(self):
        self.assertTrue(sunucu.gecerli_govde("pbf", b""))
        self.assertTrue(sunucu.gecerli_govde("pbf", b"\x1a\x05abcde"))
        self.assertFalse(sunucu.gecerli_govde("pbf", b"<html>hata</html>"))
        self.assertFalse(sunucu.gecerli_govde("pbf", b'{"message":"x"}'))

    def test_stil_adresleri_yerele_cevrilir(self):
        durum, _, govde = self.iste("/stil/hgm_vektor.json")
        self.assertEqual(durum, 200)
        stil = json.loads(govde)
        self.assertEqual(stil["sources"]["composite"]["tiles"], [self.adres + "/t/hgm_vektor/{z}/{x}/{y}"])
        self.assertEqual(stil["sources"]["yolorta"]["tiles"], [self.adres + "/t/yol_yazi_acik/{z}/{x}/{y}"])
        self.assertNotIn("atlas_kara_orman", stil["sources"])
        idler = [l["id"] for l in stil["layers"]]
        self.assertNotIn("kara_raster", idler)
        self.assertNotIn("corona", idler)
        self.assertIn("kara_z7_alti_ulkeler", idler)
        self.assertTrue(stil["glyphs"].startswith(self.adres + "/hgm-stil/fonts/"))
        self.assertNotIn("harita.gov.tr", json.dumps(stil), "stilde HGM adresi kalmamali")

    def test_stil_varligi_beyaz_liste(self):
        self.assertEqual(self.iste("/hgm-stil/sprites/sprite.json")[0], 200)
        for yol in ("/hgm-stil/corona.json", "/hgm-stil/../sunucu.py", "/hgm-stil/fonts/a/../../x.pbf",
                    "/stil/yok.json"):
            self.assertEqual(self.iste(yol)[0], 404, yol)


class KovaTesti(unittest.TestCase):
    def test_token_bucket_hizi_sinirlar(self):
        kova = sunucu.Kova(hiz=50, kapasite=5)
        t0 = time.monotonic()
        for _ in range(15):  # 5 hemen, kalan 10 tanesi 50/sn ile ~0,2 sn
            kova.al()
        self.assertGreater(time.monotonic() - t0, 0.15)


if __name__ == "__main__":
    unittest.main()
