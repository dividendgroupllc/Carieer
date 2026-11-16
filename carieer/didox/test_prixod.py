import frappe
from frappe.tests import UnitTestCase

from carieer.didox.prixod import faktura_qatorlari, narxlar

JS = {
	"facturadoc": {"facturano": "F-77", "facturadate": "2026-11-10"},
	"productlist": {
		"products": [
			{
				"ordno": 1,
				"name": "Dizel yoqilg'isi",
				"catalogcode": "02710001001000000",
				"catalogname": "Дизельное топливо",
				"packagecode": "1500001",
				"packagename": "литр",
				"count": "1000",
				"summa": "10000",
				"deliverysum": "10000000.00",
				"vatrate": "12",
				"vatsum": "1200000.00",
				"deliverysumwithvat": "11200000.00",
			},
			{
				"ordno": 2,
				"name": "Filtr",
				"catalogcode": "08421001001000000",
				"packagename": "шт",
				"count": 3,
				"deliverysum": 150000,
				"vatsum": 0,
				"deliverysumwithvat": 0,
			},
		]
	},
}


class TestFakturaQatorlari(UnitTestCase):
	def test_qatorlar(self):
		q = faktura_qatorlari(JS)
		self.assertEqual(len(q), 2)
		self.assertEqual((q[0].ordno, q[0].nomi, q[0].mxik), (1, "Dizel yoqilg'isi", "02710001001000000"))
		self.assertEqual((q[0].miqdor, q[0].summa, q[0].qqs, q[0].jami), (1000, 10000000, 1200000, 11200000))
		self.assertEqual(q[0].qadoq, "литр")

	def test_jami_bolmasa_hisoblanadi(self):
		# deliverysumwithvat 0 kelsa - summa + qqs
		self.assertEqual(faktura_qatorlari(JS)[1].jami, 150000)

	def test_bosh_faktura(self):
		self.assertEqual(faktura_qatorlari({}), [])


class TestNarxlar(UnitTestCase):
	def test_qqs_tolovchi(self):
		# QQS to'lovchi: narx QQSsiz, QQS alohida soliq qatori
		rates, qqs = narxlar(faktura_qatorlari(JS), qqs_tolovchi=True)
		self.assertEqual(rates, [10000, 50000])
		self.assertEqual(qqs, 1200000)

	def test_qqs_tolamaydi(self):
		# QQS to'lovchi emas: QQS tannarxga kiradi, soliq qatori yo'q
		rates, qqs = narxlar(faktura_qatorlari(JS), qqs_tolovchi=False)
		self.assertEqual(rates, [11200, 50000])
		self.assertEqual(qqs, 0)

	def test_miqdor_nol(self):
		q = faktura_qatorlari({"productlist": {"products": [{"count": 0, "deliverysum": 5}]}})
		with self.assertRaises(frappe.ValidationError):
			narxlar(q, qqs_tolovchi=False)
