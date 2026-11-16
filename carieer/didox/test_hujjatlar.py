import frappe
from frappe.tests import UnitTestCase

from carieer.didox.factura import qator_summalari
from carieer.didox.hujjatlar import build_ishonchnoma, build_shartnoma, build_ttn, nuqta, pinfl
from carieer.didox.sync import hujjat_malumoti

BIZ = {
	"shortName": '"EKO KARER" MCHJ',
	"address": "Samarqand, Karer ko'chasi 1",
	"director": "DIREKTOR D.",
	"directorPinfl": "30101900000011",
	"oked": "08120",
	"account": "20208000100000000001",
	"mfo": "00401",
}
MIJOZ = {
	"shortName": '"QURILISH" MCHJ',
	"address": "Toshkent",
	"director": "XARIDOR X.",
	"directorPinfl": "30202900000022",
	"oked": "41200",
	"account": "20208000200000000002",
	"mfo": "00974",
}
REGIONS = [{"regionId": 18, "name": "САМАРКАНДСКАЯ ОБЛАСТЬ"}, {"regionId": 26, "name": "ГОРОД ТАШКЕНТ"}]
DISTRICTS = [
	{"regionId": 18, "districtCode": 2, "name": "САМАРКАНДСКИЙ РАЙОН"},
	{"regionId": 26, "districtCode": 3, "name": "ЮНУСАБАДСКИЙ РАЙОН"},
]
QUM = frappe._dict(
	nomi="Qum", mxik="02517002003000000", mxik_nomi="Песок из отсевов дробления",
	qadoq_kod="1462637", qadoq="кубический метр", miqdor=10, narx=50000,
)


class TestYordamchi(UnitTestCase):
	def test_pinfl(self):
		self.assertEqual(pinfl(" 3010 1900 000011 ", "Haydovchi"), "30101900000011")
		with self.assertRaises(frappe.ValidationError):
			pinfl("12345", "Haydovchi")

	def test_nuqta(self):
		n = nuqta(26, 3, "Amir Temur 1", REGIONS, DISTRICTS)
		self.assertEqual((n["regionId"], n["regionName"], n["districtCode"]), (26, "ГОРОД ТАШКЕНТ", 3))
		self.assertEqual((n["districtName"], n["address"]), ("ЮНУСАБАДСКИЙ РАЙОН", "Amir Temur 1"))
		with self.assertRaises(frappe.ValidationError):
			nuqta(26, 99, "x", REGIONS, DISTRICTS)


class TestTTN(UnitTestCase):
	def ttn(self, tashuvchi="Mijoz"):
		v = frappe._dict(
			raqam="SOT-1", sana="2026-11-16", shartnoma_raqami="D-1", shartnoma_sanasi="2026-01-10",
			tashuvchi=tashuvchi, mashina_raqami="30 A 123 BC", mashina_modeli="HOWO",
			haydovchi_fio="ALIYEV ALI", haydovchi_pinfl="30303900000033",
			yuklash_viloyat=18, yuklash_tuman=2, yuklash_manzil="Karer",
			yuklash_masul_pinfl="30404900000044", yuklash_masul_fio="OMBORCHI O.",
			tushirish_viloyat=26, tushirish_tuman=3, tushirish_manzil="Obyekt",
			tushirish_masul_pinfl="30505900000055", tushirish_masul_fio="QABUL Q.",
			masofa=320, km_narxi=1000,
		)
		return build_ttn(v, [QUM], "309584422", BIZ, "302936161", MIJOZ, REGIONS, DISTRICTS)

	def test_tuzilma(self):
		js = self.ttn()
		self.assertEqual(js["WaybillDoc"], {"WaybillNo": "SOT-1", "WaybillDate": "2026-11-16"})
		self.assertEqual(js["Consignor"]["TinOrPinfl"], "309584422")
		self.assertEqual(js["Consignee"]["Name"], '"QURILISH" MCHJ')
		# mijozning o'z mashinasi - tashuvchi mijoz
		self.assertEqual(js["Carrier"]["TinOrPinfl"], "302936161")
		road = js["Roadway"]
		self.assertEqual(road["Truck"], {"RegNo": "30 A 123 BC", "Model": "HOWO"})
		self.assertEqual(road["Driver"], {"pinfl": "30303900000033", "FullName": "ALIYEV ALI"})
		g = road["ProductGroups"][0]
		self.assertEqual(g["LoadingPoint"]["regionName"], "САМАРКАНДСКАЯ ОБЛАСТЬ")
		self.assertEqual(g["UnloadingTrustee"], {"Pinfl": "30505900000055", "FullName": "QABUL Q."})
		p = g["ProductInfo"]["products"][0]
		self.assertEqual((p["CatalogCode"], p["Amount"], p["Price"], p["DeliverySum"]), (QUM.mxik, "10", "50000.00", "500000.00"))
		self.assertEqual(g["ProductInfo"]["TotalDeliverySum"], 500000)
		self.assertEqual((js["TotalDistance"], js["DeliveryCost"], js["TotalDeliveryCost"]), ("320.00", "1000.00", "320000.00"))
		self.assertIsNone(js["Railway"])

	def test_karer_tashiydi(self):
		self.assertEqual(self.ttn(tashuvchi="Karer")["Carrier"]["TinOrPinfl"], "309584422")


class TestIshonchnoma(UnitTestCase):
	def test_tuzilma(self):
		v = frappe._dict(
			raqam="1", sana="2026-11-16", muddat="2026-11-26", shartnoma_raqami="S-5", shartnoma_sanasi="2026-02-01",
			agent_pinfl="30606900000066", agent_fio="AGENT A.",
			buxgalter_pinfl="30707900000077", buxgalter_fio="BUX B.",
		)
		js = build_ishonchnoma(v, "309584422", BIZ, "302936161", MIJOZ, [QUM])
		self.assertEqual(js["EmpowermentDoc"], {"No": "1", "DateOfIssue": "2026-11-16", "DateOfExpire": "2026-11-26"})
		# biz - xaridor, ishonch bildirilgan xodimimiz tovarni yetkazib beruvchidan oladi
		self.assertEqual(js["Buyer"]["TinOrPinfl"], "309584422")
		self.assertEqual(js["Buyer"]["Director"], {"Pinfl": "30101900000011", "FullName": "DIREKTOR D."})
		self.assertEqual(js["Buyer"]["Accountant"], {"Pinfl": "30707900000077", "FullName": "BUX B."})
		self.assertEqual(js["Seller"]["TinOrPinfl"], "302936161")
		self.assertEqual(js["Agent"], {"Pinfl": "30606900000066", "FullName": "AGENT A."})
		self.assertEqual(js["Products"][0]["Amount"], 10)


class TestShartnoma(UnitTestCase):
	def test_tuzilma(self):
		v = frappe._dict(
			nomi="Yetkazib berish shartnomasi", raqam="D-1", sana="2026-11-16", muddat="2027-11-16", joyi="Samarqand",
			bolimlar=[{"title": "1. Predmet", "body": "Tovar yetkaziladi"}],
		)
		firma = frappe._dict(qqs_tolovchi=1, qqs_stavka=12, narx_qqs_bilan=1)
		js = build_shartnoma(v, firma, "309584422", BIZ, "302936161", MIJOZ, [QUM])
		self.assertEqual(js["ContractDoc"]["ContractNo"], "D-1")
		self.assertEqual((js["Owner"]["Tin"], js["Owner"]["FizTin"], js["Owner"]["BankId"]), ("309584422", "30101900000011", "00401"))
		self.assertEqual((js["Clients"][0]["Tin"], js["Clients"][0]["Fio"]), ("302936161", "XARIDOR X."))
		self.assertEqual(js["Parts"], [{"ordno": 1, "title": "1. Predmet", "body": "Tovar yetkaziladi"}])
		p = js["Products"][0]
		# narx QQS bilan: 50000 ichida 12% QQS - summalar hisob-faktura bilan bir xil hisoblanadi
		self.assertEqual({k: p[k] for k in ("Count", "Summa", "VatSum", "DeliverySumWithVat")}, {
			k: v for k, v in qator_summalari(10, 50000, True, 12, True).items()
			if k in ("Count", "Summa", "VatSum", "DeliverySumWithVat")
		})
		self.assertEqual(p["VatRate"], "12")
		self.assertIs(p["WithoutVat"], False)
		self.assertTrue(js["HasVat"])

	def test_bolimsiz_bolmaydi(self):
		v = frappe._dict(nomi="x", raqam="1", sana="2026-11-16", muddat="2027-11-16", joyi="x", bolimlar=[])
		with self.assertRaises(frappe.ValidationError):
			build_shartnoma(v, frappe._dict(qqs_tolovchi=0), "1", BIZ, "2", MIJOZ, [QUM])


class TestHujjatMalumoti(UnitTestCase):
	"""Sinxron: har xil hujjat turidan raqam, sana, kontragent va summa."""

	def test_ttn(self):
		js = build_ttn(
			frappe._dict(
				raqam="SOT-1", sana="2026-11-16", shartnoma_raqami="D", shartnoma_sanasi="2026-01-10", tashuvchi="Mijoz",
				mashina_raqami="X", mashina_modeli="Y", haydovchi_fio="Z", haydovchi_pinfl="30303900000033",
				yuklash_viloyat=18, yuklash_tuman=2, yuklash_manzil="a", yuklash_masul_pinfl="30404900000044",
				yuklash_masul_fio="b", tushirish_viloyat=26, tushirish_tuman=3, tushirish_manzil="c",
				tushirish_masul_pinfl="30505900000055", tushirish_masul_fio="d", masofa=1, km_narxi=0,
			),
			[QUM], "309584422", BIZ, "302936161", MIJOZ, REGIONS, DISTRICTS,
		)
		m = hujjat_malumoti(lower(js), owner=1)
		self.assertEqual((m.raqam, m.sana, m.kontragent_inn, m.summa), ("SOT-1", "2026-11-16", "302936161", 500000))

	def test_faktura(self):
		js = {
			"facturadoc": {"facturano": "F-1", "facturadate": "2026-11-01"},
			"sellertin": "302936161", "seller": {"name": "S"}, "buyertin": "309584422", "buyer": {"name": "B"},
			"productlist": {"products": [{"deliverysum": "100", "vatsum": "12"}]},
		}
		m = hujjat_malumoti(js, owner=0)
		self.assertEqual((m.raqam, m.kontragent_inn, m.kontragent_nomi, m.summa, m.qqs), ("F-1", "302936161", "S", 100, 12))


def lower(x):
	"""Didox saqlangan JSON'ni kichik harfli kalitlar bilan qaytaradi."""
	if isinstance(x, dict):
		return {k.lower(): lower(v) for k, v in x.items()}
	if isinstance(x, list):
		return [lower(v) for v in x]
	return x
