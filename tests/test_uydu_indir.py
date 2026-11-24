"""uydu_indir.py testleri. HGM'ye istek atılmaz: karolar sahte indiriciyle üretilir."""
import io
import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uydu_indir as u  # noqa: E402


def jpeg(im):
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=90)
    return b.getvalue()


def gurultu(z, x, y):
    """Gerçek ayrıntı yerine: karoya özgü, tekrarlanabilir rastgele doku."""
    r = random.Random(f"{z}/{x}/{y}")
    return Image.frombytes("L", (8, 8), bytes(r.randrange(256) for _ in range(64))).resize((256, 256), Image.NEAREST)


def sahte_indirici(gercek_ust=15, deniz=False, bozuk=()):
    """gercek_ust'e kadar gerçek doku, üstünde üst karonun büyütülmüşü (HGM'nin büyütme davranışı)."""
    def karo(z, x, y):
        if z <= gercek_ust:
            return gurultu(z, x, y)
        ust = karo(z - 1, x // 2, y // 2)
        return ust.crop((x % 2 * 128, y % 2 * 128, x % 2 * 128 + 128, y % 2 * 128 + 128)).resize((256, 256), Image.BILINEAR)

    def indir(katman, z, x, y):
        if (x, y) in bozuk:
            raise RuntimeError("geçici hata")
        if deniz:
            return x, y, jpeg(Image.new("L", (256, 256), 120))
        return x, y, jpeg(karo(z, x, y))
    return indir


class Testler(unittest.TestCase):
    def setUp(self):
        self.klasor = tempfile.mkdtemp()
        self.eski = os.getcwd()
        os.chdir(self.klasor)
        u.ISTEK_BEKLEME = 0

    def tearDown(self):
        os.chdir(self.eski)

    def test_bos_karo(self):
        self.assertTrue(u.bos_karo_mu(jpeg(Image.new("L", (256, 256), 120))))
        self.assertFalse(u.bos_karo_mu(jpeg(gurultu(15, 1, 1))))
        # koyu düz orman benzeri karo (std ~4) boş sayılmamalı
        r = random.Random(1)
        orman = Image.frombytes("L", (256, 256), bytes(37 + r.randrange(-7, 8) for _ in range(65536)))
        self.assertFalse(u.bos_karo_mu(jpeg(orman) + b"\x00" * 3000))

    def test_otomatik_zoom_gercek_ayrintinin_bittigi_seviyeyi_bulur(self):
        for ust in (14, 16, 18):
            depo = u.KaroDeposu("uydu", sahte_indirici(gercek_ust=ust))
            secilen, olcumler, _ = u.zoom_sec(depo, u.olcum_noktalari(32.83, 39.92, 32.845, 39.932, 3), 12, 10.0, 30)
            self.assertEqual(secilen, ust, olcumler)
            self.assertLessEqual(depo.indirilen, 30)

    def test_olcum_butcesi_asilmaz(self):
        depo = u.KaroDeposu("uydu", sahte_indirici(gercek_ust=19))
        u.zoom_sec(depo, u.olcum_noktalari(32.0, 39.0, 33.0, 40.0, 5), 12, 10.0, 12)
        self.assertLessEqual(depo.indirilen, 12)

    def test_deniz_bolgesi_zorla_olmadan_indirilmez(self):
        kod = u.main(["--bbox", "26.9,36.4,27.1,36.6", "--zoom", "12", "--cikti", "d.png"], sahte_indirici(deniz=True))
        self.assertEqual(kod, 2)
        self.assertFalse(Path("d.png").exists())
        kod = u.main(["--bbox", "26.9,36.4,27.1,36.6", "--zoom", "12", "--zorla", "--cikti", "d.png"], sahte_indirici(deniz=True))
        self.assertEqual(kod, 0)
        self.assertEqual(Image.open("d.png").mode, "RGBA")

    def test_az_hata_varsa_eksikle_devam(self):
        hedef = u.karo_araligi(32.83, 39.92, 32.845, 39.932, 17)
        bozuk = {(hedef[0], hedef[1])}
        kod = u.main(["--bbox", "32.83,39.92,32.845,39.932", "--zoom", "17", "--cikti", "m.png"], sahte_indirici(bozuk=bozuk))
        self.assertEqual(kod, 0)
        self.assertEqual(json.load(open("m.json", encoding="utf-8"))["eksik_karolar"], [list(next(iter(bozuk)))])

    def test_cok_hata_varsa_iptal(self):
        x0, y0, x1, y1 = u.karo_araligi(32.83, 39.92, 32.845, 39.932, 17)
        bozuk = {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y0 + 3)}
        with self.assertRaises(SystemExit):
            u.main(["--bbox", "32.83,39.92,32.845,39.932", "--zoom", "17", "--cikti", "m.png"], sahte_indirici(bozuk=bozuk))
        self.assertFalse(Path("m.png").exists())

    def test_ayni_komut_ayni_sonuc(self):
        arg = ["--bbox", "32.83,39.92,32.845,39.932", "--zoom", "17", "--otomatik-zoom"]
        u.main(arg + ["--cikti", "a.png"], sahte_indirici())
        u.main(arg + ["--cikti", "b.png"], sahte_indirici())
        self.assertEqual(Path("a.png").read_bytes(), Path("b.png").read_bytes())
        ja, jb = (json.load(open(f, encoding="utf-8")) for f in ("a.json", "b.json"))
        ja.pop("cekilme"), jb.pop("cekilme")
        self.assertEqual(ja, jb)

    def test_karo_siniri(self):
        with self.assertRaises(SystemExit):
            u.main(["--bbox", "32,39,33,40", "--zoom", "15", "--cikti", "x.png"], sahte_indirici())
        self.assertFalse(Path("x.png").exists())


if __name__ == "__main__":
    unittest.main()
