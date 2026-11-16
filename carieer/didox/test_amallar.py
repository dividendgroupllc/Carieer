import base64
import json

import frappe
from frappe.tests import UnitTestCase

from carieer.didox.common import bekor_qilinadimi, imzo_uchun, kiruvchi_imzolanadimi


def hujjat(**kw):
	return frappe._dict({"yonalish": "Kiruvchi", "hujjat_kodi": "002", "status_kod": 2, **kw})


class TestImzoUchun(UnitTestCase):
	def test_ixcham_json_base64(self):
		data = {"FacturaId": "6afae3a9", "SellerTin": "309584422", "Notes": "narx noto'g'ri, қайта юборинг"}
		matn = base64.b64decode(imzo_uchun(data)).decode()
		# bo'sh joysiz, kalitlar tartibi saqlanadi, kirill harflari \u ko'rinishiga o'tmaydi
		self.assertEqual(matn, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
		self.assertIn("қайта", matn)
		self.assertTrue(matn.startswith('{"FacturaId"'))

	def test_obyekt_bolmasa_xato(self):
		with self.assertRaises(frappe.ValidationError):
			imzo_uchun("MIAG...")


class TestAmallar(UnitTestCase):
	def test_kiruvchi_kutmoqda(self):
		self.assertTrue(kiruvchi_imzolanadimi(hujjat()))
		self.assertTrue(kiruvchi_imzolanadimi(hujjat(status_kod=1)))

	def test_kiruvchi_tugagan(self):
		for kod in (0, 3, 4, 5, 40, 50, 55):
			self.assertFalse(kiruvchi_imzolanadimi(hujjat(status_kod=kod)), kod)

	def test_chiquvchi_qabul_qilinmaydi(self):
		self.assertFalse(kiruvchi_imzolanadimi(hujjat(yonalish="Chiquvchi")))

	def test_ttn_va_yangi_ishonchnoma_alohida(self):
		self.assertFalse(kiruvchi_imzolanadimi(hujjat(hujjat_kodi="041")))
		self.assertFalse(kiruvchi_imzolanadimi(hujjat(hujjat_kodi="062")))

	def test_bekor_qilish(self):
		self.assertTrue(bekor_qilinadimi(hujjat(yonalish="Chiquvchi", status_kod=1)))
		self.assertFalse(bekor_qilinadimi(hujjat(yonalish="Chiquvchi", status_kod=0)))
		self.assertFalse(bekor_qilinadimi(hujjat(yonalish="Chiquvchi", status_kod=3)))
		self.assertFalse(bekor_qilinadimi(hujjat(yonalish="Kiruvchi", status_kod=1)))
