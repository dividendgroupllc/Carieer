from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from carieer.didox.factura import build_factura, qator_summalari

SELLER = {
	"shortName": '"EKO KARER" MCHJ',
	"VATRegCode": "326080220838",
	"account": "20208000905656222001",
	"mfo": "00401",
	"address": "Samarqand",
	"director": "DIREKTOR",
	"accountant": "BUXGALTER",
	"VATRegStatus": 20,
}
BUYER = {"name": '"QURILISH" MCHJ', "mfo": "00974", "director": "XARIDOR", "VATRegCode": None}


def firma(**kw):
	return frappe._dict({"inn": "309584422", "qqs_tolovchi": 1, "qqs_stavka": 12, "narx_qqs_bilan": 1, **kw})


def sotuv(items, xizmatlar=(), kurs=1):
	return SimpleNamespace(
		name="SOT-2026-00001",
		posting_date="2026-10-23",
		conversion_rate=kurs,
		items=[frappe._dict(r) for r in items],
		xizmatlar=[frappe._dict(r) for r in xizmatlar],
	)


ITEMS = {
	"_Test Didox Sheben": dict(mxik_kod="06901001001000000", upakovka_kod="1505731", is_stock_item=1),
	"_Test Didox Dostavka": dict(mxik_kod="10112008001000001", upakovka_kod="1209782", is_stock_item=0),
	"_Test Didox MXIKsiz": dict(mxik_kod="", upakovka_kod="1505731", is_stock_item=1),
}


def item_malumoti(item_code):
	return frappe._dict(mxik_nomi=item_code + " MXIK", upakovka_nomi="кубический метр", **ITEMS[item_code])


class TestQatorSummalari(UnitTestCase):
	def test_qqs_narx_ichida(self):
		self.assertEqual(
			qator_summalari(20, 112000, True, 12, True),
			{
				"Count": 20,
				"Summa": "100000.00",
				"DeliverySum": "2000000.00",
				"VatRate": "12",
				"VatSum": "240000.00",
				"DeliverySumWithVat": "2240000.00",
			},
		)

	def test_qqs_narx_ustiga(self):
		r = qator_summalari(1.5, 100000, True, 12, False)
		self.assertEqual((r["Summa"], r["DeliverySum"], r["VatSum"]), ("100000.00", "150000.00", "18000.00"))

	def test_qqs_tolamaydi(self):
		r = qator_summalari(24.9, 70000, False, 12, True)
		self.assertEqual(r["VatRate"], "0")
		self.assertEqual(r["VatSum"], "0.00")
		self.assertEqual(r["DeliverySum"], "1743000.00")
		self.assertEqual(r["DeliverySumWithVat"], "1743000.00")

	def test_yaxlitlash(self):
		r = qator_summalari(3, 100000, True, 12, True)
		# 100000 / 1.12 = 89285.714... -> 89285.71; DeliverySum = Count * Summa
		self.assertEqual((r["Summa"], r["DeliverySum"], r["VatSum"]), ("89285.71", "267857.13", "32142.86"))


class TestBuildFactura(UnitTestCase):
	def build(self, doc, f=None):
		with patch("carieer.didox.factura.item_malumoti", item_malumoti):
			return build_factura(
				doc, f or firma(), SELLER, "302936161", BUYER, {"raqam": "D-12", "sana": "2026-01-10"}
			)

	def test_tuzilma(self):
		doc = sotuv(
			[{"item_code": "_Test Didox Sheben", "item_name": "Sheben", "qty": 20, "rate": 112000}],
			[{"xizmat": "_Test Didox Dostavka", "qty": 1, "rate": 0}],
		)
		js = self.build(doc)
		self.assertEqual(js["FacturaDoc"], {"FacturaNo": "SOT-2026-00001", "FacturaDate": "2026-10-23"})
		self.assertEqual(js["ContractDoc"], {"ContractNo": "D-12", "ContractDate": "2026-01-10"})
		self.assertEqual((js["SellerTin"], js["BuyerTin"]), ("309584422", "302936161"))
		self.assertEqual(js["Seller"]["Name"], '"EKO KARER" MCHJ')
		self.assertEqual(js["Buyer"]["VatRegCode"], "")
		self.assertIsNone(js["FacturaRentDoc"])
		self.assertIsNone(js["ForeignCompany"])

		products = js["ProductList"]["Products"]
		# narxi 0 bo'lgan xizmat fakturaga tushmaydi
		self.assertEqual(len(products), 1)
		p = products[0]
		self.assertEqual((p["OrdNo"], p["Name"], p["CatalogCode"]), (1, "Sheben", "06901001001000000"))
		self.assertEqual((p["PackageCode"], p["Origin"]), ("1505731", 1))
		self.assertIs(p["WithoutVat"], False)
		self.assertTrue(js["ProductList"]["HasVat"])
		self.assertNotIn("MeasureId", p)

	def test_xizmat_va_dollar(self):
		doc = sotuv(
			[{"item_code": "_Test Didox Sheben", "item_name": "Sheben", "qty": 2, "rate": 10}],
			[{"xizmat": "_Test Didox Dostavka", "qty": 1, "rate": 5}],
			kurs=12700,
		)
		products = self.build(doc, firma(qqs_tolovchi=0))["ProductList"]["Products"]
		self.assertEqual([p["Summa"] for p in products], ["127000.00", "63500.00"])
		self.assertEqual([p["Origin"] for p in products], [1, 3])
		self.assertNotIn("WithoutVat", products[0])

	def test_mxiksiz_tovar(self):
		doc = sotuv([{"item_code": "_Test Didox MXIKsiz", "qty": 1, "rate": 1000}])
		with self.assertRaises(frappe.ValidationError):
			self.build(doc)
