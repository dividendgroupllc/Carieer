"""Kassa va Kassa Kategoriya qiymatlari lotinchadan kirillchaga (Excel «Касса» varag'idagidek):
Kirim -> Приход, Chiqim -> Расход, O'tkazma -> Перемещение, Konvertatsiya -> Конвертация;
kontragent turi Customer -> Клиент ... (ERPNext doctype - yangi party_doctype maydonida); holat -> Черновик / Проведён / Отменён."""

import frappe

TURI = {"Kirim": "Приход", "Chiqim": "Расход", "O'tkazma": "Перемещение", "Konvertatsiya": "Конвертация"}
STATUS = {"Draft": "Черновик", "Tasdiqlangan": "Проведён", "Bekor qilingan": "Отменён"}
PARTY_TYPE = {
	"Customer": ("Клиент", "Customer"),
	"Supplier": ("Поставщик", "Supplier"),
	"Employee": ("Сотрудник", "Employee"),
	"Xarajat": ("Статья расхода", None),
	"Daromad": ("Доход", None),
	"Dividend": ("Дивиденд", None),
	"Kapital": ("Капитал", None),
}
KATEGORIYA_TURI = {"Kirim": "Приход", "Chiqim": "Расход", "Ikkalasi": "Оба"}


def execute():
	for old, new in TURI.items():
		frappe.db.sql("update `tabKassa` set turi=%s where turi=%s", (new, old))
	for old, new in STATUS.items():
		frappe.db.sql("update `tabKassa` set status=%s where status=%s", (new, old))
	for old, (new, doctype) in PARTY_TYPE.items():
		frappe.db.sql(
			"update `tabKassa` set party_type=%s, party_doctype=%s where party_type=%s", (new, doctype, old)
		)
	# kontragent «Прочие лица» bo'lsa ham doctype - Supplier (kategoriya bo'yicha)
	frappe.db.sql(
		"""update `tabKassa` set party_type='Прочие лица'
		where party_doctype='Supplier' and lower(ifnull(kategoriya, ''))='прочие лица'"""
	)
	for old, new in KATEGORIYA_TURI.items():
		frappe.db.sql("update `tabKassa Kategoriya` set turi=%s where turi=%s", (new, old))
