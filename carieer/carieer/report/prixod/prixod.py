# Prixod ("Приход"): firmaga kirgan hamma narsa - tovar, xizmat, asosiy vosita - bitta jadvalda,
# Google Sheets'dagi «Приход» varag'i ustunlarida:
#   Месяц | Дата | Наименование | Кол-во | Ед-изм | Цена | Валюта | Сумма | Поставщик | Курс | Сумма $ | Тип | Цех
# Manbalar (hammasi tasdiqlangan hujjatlar):
#   Xarid fakturasi (Purchase Invoice)            - tovar va xizmat
#   Qabul (Purchase Receipt), hisob-fakturasi yo'q - tovar keldi, faktura hali kiritilmagan (ikki marta sanalmaydi)
#   Начисление «Закуп услуга»                     - xizmat (samosval, ekskavator ...)
#   Приход ОС                                     - asosiy vosita
# «Курс» - shu kungi USD kursi (Currency Exchange), «Сумма $» = so'mdagi summa / kurs (dollardagi hujjat - o'zi).

import frappe
from frappe import _
from frappe.utils import flt, getdate

from carieer.carieer.report.common import bold, prepare, usd_rate

OYLAR = (
	"января", "февраля", "марта", "апреля", "мая", "июня",
	"июля", "августа", "сентября", "октября", "ноября", "декабря",
)  # fmt: skip
TOVAR, XIZMAT, OS = _("Tovar"), _("Xizmat"), _("Asosiy vosita")
TURI_FILTR = {"Tovar": TOVAR, "Xizmat": XIZMAT, "Asosiy vosita": OS}


def execute(filters=None):
	filters = prepare(filters, period="month")
	data = get_data(filters)
	return get_columns(), with_total(data), None, None, get_summary(data, filters)


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency"}
	return [
		{"label": _("Месяц"), "fieldname": "oy", "fieldtype": "Data", "width": 110},
		{"label": _("Дата"), "fieldname": "sana", "fieldtype": "Date", "width": 95},
		{"label": _("Наименование"), "fieldname": "nomi", "fieldtype": "Data", "width": 190},
		{"label": _("Кол-во"), "fieldname": "qty", "fieldtype": "Float", "width": 85},
		{"label": _("Ед-изм"), "fieldname": "uom", "fieldtype": "Data", "width": 70},
		{"label": _("Цена"), "fieldname": "rate", **cur, "width": 115},
		{"label": _("Валюта"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 65},
		{"label": _("Сумма"), "fieldname": "amount", **cur, "width": 130},
		{"label": _("Поставщик"), "fieldname": "party", "fieldtype": "Link", "options": "Supplier", "width": 170},
		{"label": _("Курс"), "fieldname": "kurs", "fieldtype": "Float", "precision": "0", "width": 80},
		{"label": _("Сумма $"), "fieldname": "amount_usd", "fieldtype": "Float", "precision": "2", "width": 110},
		{"label": _("Тип"), "fieldname": "tip", "fieldtype": "Data", "width": 110},
		{"label": _("Цех (ombor)"), "fieldname": "ombor", "fieldtype": "Data", "width": 140},
		{"label": _("Сумма (сўм)"), "fieldname": "base_amount", "fieldtype": "Currency", "width": 130},
		{"label": "", "fieldname": "doctype", "fieldtype": "Data", "hidden": 1},
		{"label": _("Hujjat"), "fieldname": "hujjat", "fieldtype": "Dynamic Link", "options": "doctype", "width": 150},
	]


def get_data(filters):
	values = dict(filters)
	supplier_cond = " and doc.supplier = %(supplier)s" if filters.get("supplier") else ""
	item_cond = " and i.item_code = %(item_code)s" if filters.get("item_code") else ""
	# Qabul (Receipt) - faqat fakturasi yo'q qismi: faktura Qabul'dan yoki Qabul fakturadan yaratilgan bo'lsa ham
	# billed_amt yangilanadi, Xarid fakturasi qatori esa birinchi qismda bor - ikki marta sanalmaydi
	rows = frappe.db.sql(
		f"""select 'Purchase Invoice' doctype, doc.name hujjat, doc.posting_date sana, doc.supplier party,
			doc.currency, doc.conversion_rate, i.item_code, i.item_name nomi, i.qty, i.uom, i.rate, i.amount,
			i.base_amount, i.warehouse, it.item_group, it.is_stock_item, i.is_fixed_asset, doc.creation
		from `tabPurchase Invoice` doc join `tabPurchase Invoice Item` i on i.parent = doc.name
			left join `tabItem` it on it.name = i.item_code
		where doc.docstatus = 1 and doc.company = %(company)s
			and doc.posting_date between %(from_date)s and %(to_date)s{supplier_cond}{item_cond}
		union all
		select 'Purchase Receipt', doc.name, doc.posting_date, doc.supplier, doc.currency, doc.conversion_rate,
			i.item_code, i.item_name, i.qty, i.uom, i.rate, i.amount - ifnull(i.billed_amt, 0),
			i.base_amount * (i.amount - ifnull(i.billed_amt, 0)) / i.amount,
			i.warehouse, it.item_group, it.is_stock_item, i.is_fixed_asset, doc.creation
		from `tabPurchase Receipt` doc join `tabPurchase Receipt Item` i on i.parent = doc.name
			left join `tabItem` it on it.name = i.item_code
		where doc.docstatus = 1 and doc.company = %(company)s
			and doc.posting_date between %(from_date)s and %(to_date)s{supplier_cond}{item_cond}
			and i.amount - ifnull(i.billed_amt, 0) > 0.01""",
		values,
		as_dict=True,
	)
	if not filters.get("item_code"):
		party_cond = " and party = %(supplier)s" if filters.get("supplier") else ""
		rows += frappe.db.sql(
			f"""select 'Nachislenie' doctype, name hujjat, sana, party, currency, kurs conversion_rate,
				null item_code, ifnull(kategoriya, %(xizmat)s) nomi, qty, '' uom, rate, amount, base_amount,
				'' warehouse, %(xizmat_guruh)s item_group, 0 is_stock_item, 0 is_fixed_asset, creation
			from `tabNachislenie`
			where docstatus = 1 and company = %(company)s and turi = 'Закуп услуга'
				and sana between %(from_date)s and %(to_date)s{party_cond}""",
			{**values, "xizmat": _("Услуга"), "xizmat_guruh": "Услуга"},
			as_dict=True,
		)
		os_cond = " and supplier = %(supplier)s" if filters.get("supplier") else ""
		rows += frappe.db.sql(
			f"""select 'Prixod OS' doctype, name hujjat, sana, supplier party, currency, kurs conversion_rate,
				null item_code, nomi, qty, '' uom, rate, amount, base_amount, '' warehouse,
				%(os)s item_group, 0 is_stock_item, 1 is_fixed_asset, creation
			from `tabPrixod OS`
			where docstatus = 1 and company = %(company)s and sana between %(from_date)s and %(to_date)s{os_cond}""",
			{**values, "os": "Основное средство"},
			as_dict=True,
		)

	want = TURI_FILTR.get(filters.get("turi"))
	rates = {}
	out = []
	for r in sorted(rows, key=lambda r: (r.sana, r.creation)):
		r.turi = OS if r.is_fixed_asset else (TOVAR if r.is_stock_item else XIZMAT)
		if want and r.turi != want:
			continue
		sana = getdate(r.sana)
		r.oy = f"{OYLAR[sana.month - 1]}\\{sana.year}"
		r.tip = r.item_group or r.turi
		r.ombor = r.warehouse or ""
		r.base_amount = flt(r.base_amount) or flt(r.amount) * flt(r.conversion_rate or 1)
		kurs = usd_rate(filters.company, r.sana, rates)
		r.kurs = flt(r.conversion_rate) if r.currency == "USD" else kurs
		r.amount_usd = flt(r.amount) if r.currency == "USD" else (flt(r.base_amount) / kurs if kurs else None)
		if r.doctype == "Purchase Receipt":
			r.tip = f"{r.tip} · " + _("faktura yo'q")
			if flt(r.rate):
				r.qty = flt(r.amount) / flt(r.rate)  # qisman fakturalangan bo'lsa - qolgan miqdor
		out.append(r)
	return out


def with_total(rows):
	if not rows:
		return rows
	return [
		*rows,
		{
			"oy": bold(_("ЖАМИ")),
			"base_amount": sum(flt(r.base_amount) for r in rows),
			"amount_usd": sum(flt(r.amount_usd) for r in rows),
		},
	]


def get_summary(rows, filters):
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")

	def card(label, value, indicator):
		return {"label": label, "value": value, "datatype": "Currency", "currency": currency, "indicator": indicator}

	out = [card(_("Jami kirim (сўм)"), sum(flt(r.base_amount) for r in rows), "Blue")]
	for turi, indicator in ((TOVAR, "Green"), (XIZMAT, "Orange"), (OS, "Purple")):
		value = sum(flt(r.base_amount) for r in rows if r.turi == turi)
		if value:
			out.append(card(turi, value, indicator))
	faktura_yoq = sum(flt(r.base_amount) for r in rows if r.doctype == "Purchase Receipt")
	if faktura_yoq:
		out.append(card(_("Qabul qilingan, faktura yo'q"), faktura_yoq, "Red"))
	return out
