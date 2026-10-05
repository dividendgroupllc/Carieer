"""Test (demo) ma'lumotlari: tizimni to'liq sinab ko'rish uchun bir buyruq bilan butun bir haftalik ish.

Faqat SINOV saytida ishlating (haqiqiy ish uchun toza sayt oching):
  bench --site SITE execute carieer.install.setup_karer --kwargs "{'karer_company': 'Eko Karer', 'beton_company': 'Eko Beton'}"
  bench --site SITE execute carieer.demo.make_demo

Nima yaratiladi (oxirgi 7 kun bo'yicha, ketma-ket):
  - mijozlar, ta'minotchilar, haydovchilar (Employee), sotuv narxlari (Item Price), USD kursi
  - Karer: qazib olish -> omborda Шебень / Қум / Клинец / Тош (tan narx 0)
  - Beton: Purchase Receipt (Цемент, Хим.добавка) -> Purchase Invoice (ta'minotchiga qarz) -> qisman to'lov
  - Karer -> Beton firmalararo sotuv (Шебень, Қум) -> Beton'da avtomatik Purchase Invoice
  - BOM (Бетон М200, М300) -> beton ishlab chiqarish
  - sotuvlar (naqd, bank, USD, qisman, qarzga, narxi Item Price'dan), Kassa kirim / chiqim / o'tkazma,
    Начисление (самосвал xizmati), firmalararo to'lov, yoqilg'i, texnikalar va bugungi GPS yo'llari
  - har bir rol uchun test foydalanuvchilar (parol: Demo12345!)
"""

from datetime import timedelta
from itertools import pairwise

import frappe
from frappe import _
from frappe.utils import add_days, flt, now_datetime, nowdate

DEMO = "DEMO"
PAROL = "Demo12345!"

MIJOZLAR = ["Олим ака", "Бахром Строй", "Тошкент Қурилиш", "Кэш (нақд)"]
TAMINOTCHILAR = ["Цемент завод", "Кимё савдо", "Заправка АЗС", "Султон (самосвал)"]
HAYDOVCHILAR = ["Жасур Каримов", "Бобур Алиев", "Азиз Раҳимов", "Шерзод Тошев"]
NARXLAR = {
	"Шебень": 110000,
	"Қум": 90000,
	"Клинец": 120000,
	"Тош": 70000,
	"Бетон М200": 750000,
	"Бетон М300": 850000,
}
USD_KURS = 12700

# Xarita uchun koordinatalar (karer -> shahar yo'li)
KARER = (41.0640, 69.6390)
BETON_ZAVOD = (41.2465, 69.3410)
YOL_KARER_SHAHAR = [
	KARER,
	(41.1000, 69.5800),
	(41.1600, 69.4800),
	(41.2200, 69.3800),
	(41.2600, 69.3100),
	(41.2995, 69.2401),
]
QURILISH = (41.3260, 69.2870)


def day(n: int) -> str:
	return add_days(nowdate(), -n)


def make_demo():
	frappe.only_for("System Manager")
	karer = frappe.db.get_value("Zavod", "Karer", "company")
	beton = frappe.db.get_value("Zavod", "Beton", "company")
	if not karer or not beton:
		frappe.throw(_("Avval setup_karer ni ishga tushiring (Zavod Karer va Beton kerak)"))
	if frappe.db.exists("Sotuv", {"izoh": DEMO}):
		frappe.throw(_("Demo ma'lumotlar allaqachon kiritilgan"))

	kz = frappe.get_doc("Zavod", "Karer")
	bz = frappe.get_doc("Zavod", "Beton")
	masters(karer, beton)

	# ---------------------------------------------------------------- 6 kun oldin: ombor to'ldiriladi
	qazib = submit(
		{
			"doctype": "Qazib Olish",
			"company": karer,
			"posting_date": day(6),
			"izoh": DEMO,
			"items": [
				{"item_code": "Шебень", "qty": 600},
				{"item_code": "Қум", "qty": 400},
				{"item_code": "Клинец", "qty": 200},
				{"item_code": "Тош", "qty": 150},
			],
		}
	)
	pr = submit(
		{
			"doctype": "Purchase Receipt",
			"company": beton,
			"supplier": "Цемент завод",
			"posting_date": day(6),
			"set_posting_time": 1,
			"set_warehouse": bz.xomashyo_ombori,
			"remarks": DEMO,
			"items": [
				{"item_code": "Цемент", "qty": 30, "rate": 1200000, "warehouse": bz.xomashyo_ombori},
				{"item_code": "Хим.добавка", "qty": 500, "rate": 15000, "warehouse": bz.xomashyo_ombori},
			],
		}
	)
	from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice

	pi = make_purchase_invoice(pr.name)
	pi.posting_date = day(6)
	pi.set_posting_time = 1
	pi.bill_no = "DEMO-001"
	pi.insert()
	pi.submit()

	# Yoqilg'i ombori (zapravkadan sotib olingan solyarka)
	submit(
		{
			"doctype": "Purchase Invoice",
			"company": karer,
			"supplier": "Заправка АЗС",
			"posting_date": day(6),
			"set_posting_time": 1,
			"update_stock": 1,
			"set_warehouse": kz.yoqilgi_ombori,
			"remarks": DEMO,
			"items": [{"item_code": "Солярка", "qty": 3000, "rate": 12000, "warehouse": kz.yoqilgi_ombori}],
		}
	)

	# ---------------------------------------------------------------- 5 kun oldin: karer -> beton, retsept, ishlab chiqarish
	ichki_mijoz = frappe.db.get_value("Customer", {"is_internal_customer": 1, "represents_company": beton})
	sotuv(
		"Karer",
		ichki_mijoz,
		day(5),
		[("Шебень", 120, 80000), ("Қум", 80, 60000)],
		mashina="01A100AA",
	)
	bom300 = make_bom(
		beton, "Бетон М300", [("Шебень", 0.8), ("Қум", 0.5), ("Цемент", 0.35), ("Хим.добавка", 3)]
	)
	bom200 = make_bom(
		beton, "Бетон М200", [("Шебень", 0.8), ("Қум", 0.6), ("Цемент", 0.25), ("Хим.добавка", 2)]
	)
	for bom, qty, n in ((bom300, 40, 5), (bom200, 30, 4)):
		submit({"doctype": "Beton Ishlab Chiqarish", "bom": bom, "qty": qty, "posting_date": day(n)})

	# ---------------------------------------------------------------- sotuvlar
	sotuv(
		"Karer",
		"Олим ака",
		day(4),
		[("Шебень", 15, 110000)],
		[("Доставка", 1, 150000)],
		[("Наличные", 1800000)],
		mashina="40A555AA",
		dostavka="Да",
	)
	sotuv(
		"Karer", "Бахром Строй", day(4), [("Қум", 30, 90000)], tolovlar=[("Р/С", 1000000)], mashina="01B777BB"
	)
	sotuv(
		"Karer",
		"Тошкент Қурилиш",
		day(3),
		[("Клинец", 20, 120000)],
		[("Погрузчик", 1, 100000)],
		mashina="10C123CC",
	)
	sotuv(
		"Karer",
		"Кэш (нақд)",
		day(3),
		[("Тош", 10, 70000)],
		tolovlar=[("Наличные", 700000)],
		mashina="30D321DD",
	)
	sotuv(
		"Karer",
		"Олим ака",
		day(2),
		[("Шебень", 25, 110000)],
		tolovlar=[("Наличные $", 100)],
		mashina="40A555AA",
	)
	sotuv(
		"Karer",
		"Бахром Строй",
		day(1),
		[("Шебень", 40, 105000)],
		tolovlar=[("Карта", 4200000)],
		mashina="01B777BB",
	)
	# narx kiritilmagan -> Item Price'dan (Қум = 90 000)
	sotuv("Karer", "Кэш (нақд)", day(0), [("Қум", 8, 0)], tolovlar=[("Наличные", 720000)], mashina="70E987EE")
	sotuv(
		"Beton",
		"Бахром Строй",
		day(2),
		[("Бетон М300", 12, 850000)],
		[("Миксер доставка", 2, 250000)],
		[("Р/С", 5000000)],
		dostavka="Да",
	)
	sotuv("Beton", "Тошкент Қурилиш", day(1), [("Бетон М200", 15, 750000)], dostavka="Да")
	sotuv("Beton", "Кэш (нақд)", day(0), [("Бетон М300", 3, 850000)], tolovlar=[("Наличные", 2550000)])
	# Post operatori saqlagan, hali yakunlanmagan sotuv
	sotuv("Karer", "Тошкент Қурилиш", day(0), [("Шебень", 10, 110000)], mashina="10C123CC", submit_doc=False)

	# ---------------------------------------------------------------- kassa, начисление, firmalararo
	kassa(
		karer, day(1), "Kirim", "Наличные", 1500000, "Customer", "Тошкент Қурилиш", "Клиент", "qarzdan to'lov"
	)
	kassa(
		karer, day(2), "Chiqim", "Р/С", 3000000, "Xarajat", None, "Зарплата Производства", "ish haqi (avans)"
	)
	kassa(karer, day(1), "Chiqim", "Наличные", 350000, "Xarajat", None, "Питание", "ishchilar ovqati")
	kassa(karer, day(0), "Chiqim", "Наличные", 120000, "Xarajat", None, "Хоз.расход", "kanselyariya")
	submit(
		{
			"doctype": "Kassa",
			"company": karer,
			"sana": day(0),
			"turi": "O'tkazma",
			"mode_of_payment": "Наличные",
			"mode_of_payment_to": "Р/С",
			"amount": 1000000,
			"izoh": DEMO,
		}
	)
	submit(
		{
			"doctype": "Nachislenie",
			"company": karer,
			"sana": day(3),
			"turi": "Закуп услуга",
			"kategoriya": "Самосвал услуга",
			"party_type": "Supplier",
			"party": "Султон (самосвал)",
			"qty": 3,
			"rate": 400000,
			"izoh": DEMO + ": 3 reys",
		}
	)
	kassa(
		karer,
		day(1),
		"Chiqim",
		"Наличные",
		800000,
		"Supplier",
		"Султон (самосвал)",
		"Самосвал услуга",
		"самосвал xizmati uchun",
	)
	kassa(beton, day(1), "Chiqim", "Р/С", 2000000, "Supplier", "Цемент завод", "Поставщик", "sement uchun")
	submit(
		{
			"doctype": "Firmalararo Tolov",
			"posting_date": day(1),
			"tolovchi_firma": beton,
			"tolovchi_kassa": "Р/С",
			"oluvchi_firma": karer,
			"oluvchi_kassa": "Р/С",
			"summa": 3000000,
			"izoh": DEMO,
		}
	)

	# ---------------------------------------------------------------- texnika, yoqilg'i, GPS
	vehicles = texnikalar(karer, beton)
	for vehicle, qty, odometr in ((vehicles[0], 120, 125400), (vehicles[2], 60, None)):
		submit(
			{
				"doctype": "Yoqilgi Hisobi",
				"company": karer,
				"posting_date": day(1),
				"vehicle": vehicle,
				"turi": "Dizel (солярка)",
				"manba": "Ombordan",
				"item_code": "Солярка",
				"qty": qty,
				"odometr": odometr,
				"izoh": DEMO,
			}
		)
	gps_yollar(vehicles)
	frappe.db.commit()

	users = foydalanuvchilar()
	return {
		"qazib_olish": qazib.name,
		"purchase_receipt": pr.name,
		"purchase_invoice": pi.name,
		"sotuvlar": frappe.db.count("Sotuv", {"izoh": DEMO}),
		"texnikalar": vehicles,
		"foydalanuvchilar": users,
		"parol": PAROL,
	}


# ==================================================================== yordamchilar
def submit(data: dict):
	doc = frappe.get_doc(data)
	doc.insert()
	doc.submit()
	return doc


def masters(karer: str, beton: str):
	if not frappe.db.exists("Currency Exchange", {"from_currency": "USD", "to_currency": "UZS"}):
		frappe.get_doc(
			{
				"doctype": "Currency Exchange",
				"date": day(30),
				"from_currency": "USD",
				"to_currency": "UZS",
				"exchange_rate": USD_KURS,
				"for_buying": 1,
				"for_selling": 1,
			}
		).insert()

	customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
	for name in MIJOZLAR:
		if not frappe.db.exists("Customer", name):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": name,
					"customer_type": "Company" if "Строй" in name or "Қурилиш" in name else "Individual",
					"customer_group": customer_group,
					"territory": territory,
				}
			).insert()

	supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
	for name in TAMINOTCHILAR:
		if not frappe.db.exists("Supplier", name):
			frappe.get_doc(
				{"doctype": "Supplier", "supplier_name": name, "supplier_group": supplier_group}
			).insert()

	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"
	for item, rate in NARXLAR.items():
		if not frappe.db.exists("Item Price", {"item_code": item, "price_list": price_list}):
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": item,
					"price_list": price_list,
					"price_list_rate": rate,
				}
			).insert()

	for i, name in enumerate(HAYDOVCHILAR):
		if frappe.db.exists("Employee", {"employee_name": name}):
			continue
		first, last = name.split(" ", 1)
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": first,
				"last_name": last,
				"gender": "Male",
				"date_of_birth": "1990-01-01",
				"date_of_joining": day(365),
				"company": beton if i == 3 else karer,
				"designation": None,
				"status": "Active",
			}
		).insert()


def make_bom(company: str, item: str, rows: list[tuple[str, float]]) -> str:
	name = frappe.db.get_value("BOM", {"item": item, "company": company, "docstatus": 1, "is_active": 1})
	if name:
		return name
	return submit(
		{
			"doctype": "BOM",
			"item": item,
			"company": company,
			"quantity": 1,
			"is_default": 1,
			"rm_cost_as_per": "Valuation Rate",
			"items": [{"item_code": code, "qty": qty} for code, qty in rows],
		}
	).name


def sotuv(
	tip, customer, date, items, xizmatlar=(), tolovlar=(), mashina=None, dostavka="Нет", submit_doc=True
):
	doc = frappe.get_doc(
		{
			"doctype": "Sotuv",
			"tip": tip,
			"customer": customer,
			"posting_date": date,
			"mashina_raqami": mashina,
			"dostavka": dostavka,
			"izoh": DEMO,
			"items": [{"item_code": i, "qty": q, "rate": r} for i, q, r in items],
			"xizmatlar": [{"xizmat": x, "qty": q, "rate": r} for x, q, r in xizmatlar],
			"tolovlar": [
				{"mode_of_payment": m, "summa": s, "sana": date, "kim": customer} for m, s in tolovlar
			],
		}
	)
	doc.insert()
	if submit_doc:
		doc.submit()
	return doc


def kassa(company, date, turi, mop, amount, party_type, party, kategoriya, izoh):
	return submit(
		{
			"doctype": "Kassa",
			"company": company,
			"sana": date,
			"turi": turi,
			"mode_of_payment": mop,
			"amount": amount,
			"party_type": party_type,
			"party": party,
			"kategoriya": kategoriya,
			"izoh": f"{DEMO}: {izoh}",
		}
	)


def employee(name: str) -> str | None:
	return frappe.db.get_value("Employee", {"employee_name": name}, "name")


def texnikalar(karer: str, beton: str) -> list[str]:
	rows = [
		# raqam, marka, model, turi, firma, imei, haydovchi
		("01K777KK", "Howo", "A7", "Samosval", karer, "860000000000001", HAYDOVCHILAR[0]),
		("01K888KK", "Shacman", "X3000", "Samosval", karer, "860000000000002", HAYDOVCHILAR[1]),
		("01E101EK", "Hitachi", "ZX330", "Ekskavator", karer, "860000000000003", HAYDOVCHILAR[2]),
		("01B500BB", "Howo", "Mikser 12m3", "Betonovoz (mikser)", beton, "860000000000004", HAYDOVCHILAR[3]),
	]
	out = []
	for plate, make, model, turi, company, imei, driver in rows:
		if not frappe.db.exists("Vehicle", plate):
			frappe.get_doc(
				{
					"doctype": "Vehicle",
					"license_plate": plate,
					"make": make,
					"model": model,
					"last_odometer": 125000,
					"fuel_type": "Diesel",
					"uom": "Литр",
					"company": company,
					"texnika_turi": turi,
					"gps_imei": imei,
					"employee": employee(driver),
				}
			).insert()
		out.append(plate)
	if not frappe.db.get_single_value("Karer Sozlamalari", "gps_token"):
		settings = frappe.get_doc("Karer Sozlamalari")
		settings.gps_token = "demo-token-123"
		settings.save()
	return out


def route_points(segments, start, step_s=60):
	"""segments: [("move", [(lat, lon), ...], km_soat) | ("stop", (lat, lon), daqiqa)] -> GPS nuqtalar."""
	from carieer.api import distance_m

	t = start
	out = []
	for seg in segments:
		if seg[0] == "stop":
			_kind, (lat, lon), mins = seg
			for k in range(0, int(mins * 60 / step_s) + 1):
				jitter = ((k * 7) % 5 - 2) * 0.00002  # telefon GPS'i joyida ham ozgina "sakraydi"
				out.append((t, lat + jitter, lon - jitter, 0))
				t += timedelta(seconds=step_s)
			continue
		_kind, path, speed = seg
		for (lat1, lon1), (lat2, lon2) in pairwise(path):
			meters = distance_m(lat1, lon1, lat2, lon2)
			steps = max(1, int(meters / (speed / 3.6 * step_s)))
			for k in range(steps):
				f = k / steps
				out.append((t, lat1 + (lat2 - lat1) * f, lon1 + (lon2 - lon1) * f, speed + (k % 5) - 2))
				t += timedelta(seconds=step_s)
	return out


def gps_yollar(vehicles: list[str]):
	from carieer.api import save_point

	now = now_datetime().replace(microsecond=0)
	shahar = list(reversed(YOL_KARER_SHAHAR))
	# 1) Samosval: karerda yuklash -> shaharga -> tushirish -> qaytmoqda (hozir harakatda)
	samosval = [
		("stop", KARER, 20),
		("move", YOL_KARER_SHAHAR, 55),
		("stop", YOL_KARER_SHAHAR[-1], 15),
		("move", shahar[:4], 50),
	]
	# 2) Ikkinchi samosval: ertalab bitta reys, hozir karerda turibdi (to'xtagan)
	samosval2 = [
		("move", YOL_KARER_SHAHAR[:3], 45),
		("stop", YOL_KARER_SHAHAR[2], 10),
		("move", list(reversed(YOL_KARER_SHAHAR[:3])), 45),
		("stop", KARER, 15),
	]
	# 4) Betonovoz: zavoddan qurilishga, tushirib, zavodga qaytgan (to'xtagan)
	mikser = [
		("stop", BETON_ZAVOD, 10),
		("move", [BETON_ZAVOD, (41.2900, 69.3100), QURILISH], 35),
		("stop", QURILISH, 25),
		("move", [QURILISH, (41.2900, 69.3100), BETON_ZAVOD], 35),
		("stop", BETON_ZAVOD, 12),
	]
	plans = {
		vehicles[0]: (samosval, timedelta(minutes=1)),
		vehicles[1]: (samosval2, timedelta(minutes=8)),
		vehicles[3]: (mikser, timedelta(minutes=0)),
	}
	for vehicle, (segments, end_gap) in plans.items():
		imei = frappe.db.get_value("Vehicle", vehicle, "gps_imei")
		pts = route_points(segments, now)
		shift = (now - end_gap) - pts[-1][0]
		for t, lat, lon, speed in pts:
			save_point(
				imei, vaqt=t + shift, latitude=lat, longitude=lon, tezlik=max(speed, 0), qurilma="Demo"
			)
	# 3) Ekskavator: kecha karerda ishlagan, bugun aloqa yo'q
	imei = frappe.db.get_value("Vehicle", vehicles[2], "gps_imei")
	kecha = now - timedelta(days=1)
	for t, lat, lon, speed in route_points(
		[("stop", KARER, 30), ("move", [KARER, (41.0660, 69.6420)], 5)], kecha
	):
		save_point(imei, vaqt=t, latitude=lat, longitude=lon, tezlik=speed, qurilma="Demo")


def foydalanuvchilar() -> list[str]:
	from carieer.install import setup_user

	rows = [
		("karer.operator@demo.uz", "Karer Operator", "Karer", "Operator"),
		("karer.kassir@demo.uz", "Karer Kassir", "Karer", "Kassir"),
		("karer.menejer@demo.uz", "Karer Menejer", "Karer", "Menejer"),
		("beton.operator@demo.uz", "Beton Operator", "Beton", "Operator"),
		("beton.menejer@demo.uz", "Beton Menejer", "Beton", "Menejer"),
		("post@demo.uz", "Post Operator", "Ikkalasi", "Operator"),
	]
	for email, full_name, zavod, lavozim in rows:
		setup_user(email, full_name, zavod, lavozim, password=PAROL)
	return [r[0] for r in rows]
