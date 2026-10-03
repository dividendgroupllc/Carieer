# Sotuv yangi tuzilmaga o'tdi (bitta tovar -> Товары / Услуги / Оплаты jadvallari).
# Eski yozuvlarning tovari (eski ustunlar bazada qolgan) Товары jadvaliga, to'lovlari (Payment Entry) Оплаты jadvaliga ko'chiriladi.
# Sotuv posti sozlamasi (Karer / Beton firmasi) va standart xizmatlar (Погрузчик, Доставка) yaratiladi.

import frappe
from frappe.utils import flt

XIZMATLAR = ("Погрузчик", "Доставка")


def execute():
	set_post_firmalar()
	make_xizmatlar()
	columns = set(frappe.db.get_table_columns("Sotuv"))
	if "item_code" not in columns:
		return
	tip_by_company = {
		frappe.db.get_single_value("Karer Sozlamalari", "karer_firma"): "Karer",
		frappe.db.get_single_value("Karer Sozlamalari", "beton_firma"): "Beton",
	}
	for d in frappe.db.sql(
		"""select name, company, item_code, item_name, qty, uom, rate, amount, conversion_factor, stock_qty,
			warehouse, currency, sales_invoice, docstatus
		from `tabSotuv`""",
		as_dict=True,
	):
		frappe.db.set_value(
			"Sotuv", d.name, {"tip": tip_by_company.get(d.company, "Karer"), "itog": d.amount, "xizmat_jami": 0},
			update_modified=False,
		)
		if d.item_code and not frappe.db.exists("Sotuv Tovar", {"parent": d.name}):
			row = frappe.get_doc(
				{
					"doctype": "Sotuv Tovar",
					"parent": d.name,
					"parenttype": "Sotuv",
					"parentfield": "items",
					"idx": 1,
					"item_code": d.item_code,
					"item_name": d.item_name,
					"qty": d.qty,
					"uom": d.uom,
					"rate": d.rate,
					"amount": d.amount,
					"conversion_factor": d.conversion_factor,
					"stock_qty": d.stock_qty,
					"warehouse": d.warehouse,
					"currency": d.currency,
				}
			)
			row.db_insert()
		if d.sales_invoice and not frappe.db.exists("Sotuv Tolov", {"parent": d.name}):
			pes = frappe.db.sql(
				"""select distinct pe.name, pe.posting_date, pe.mode_of_payment, pe.paid_to_account_currency cur,
					pe.received_amount, per.allocated_amount
				from `tabPayment Entry` pe join `tabPayment Entry Reference` per on per.parent = pe.name
				where per.reference_name = %s and pe.docstatus = 1 order by pe.posting_date, pe.creation""",
				d.sales_invoice,
				as_dict=True,
			)
			for idx, pe in enumerate(pes, 1):
				kurs = flt(pe.allocated_amount) / flt(pe.received_amount) if flt(pe.received_amount) else 1
				frappe.get_doc(
					{
						"doctype": "Sotuv Tolov",
						"parent": d.name,
						"parenttype": "Sotuv",
						"parentfield": "tolovlar",
						"idx": idx,
						"sana": pe.posting_date,
						"mode_of_payment": pe.mode_of_payment,
						"valyuta": pe.cur,
						"summa": pe.received_amount,
						"kurs": kurs,
						"sotuv_summa": pe.allocated_amount,
						"payment_entry": pe.name,
						"currency": d.currency,
					}
				).db_insert()


def set_post_firmalar():
	settings = frappe.get_single("Karer Sozlamalari")
	companies = [r.company for r in settings.firmalar]
	changed = False
	if not settings.karer_firma:
		settings.karer_firma = next((c for c in companies if "beton" not in c.lower()), companies[0] if companies else None)
		changed = True
	if not settings.beton_firma:
		settings.beton_firma = next((c for c in companies if "beton" in c.lower()), settings.karer_firma)
		changed = True
	if changed:
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)


def make_xizmatlar():
	group = "Services" if frappe.db.exists("Item Group", "Services") else frappe.db.get_value("Item Group", {"is_group": 0}, "name")
	uom = "Nos" if frappe.db.exists("UOM", "Nos") else "Unit"
	for name in XIZMATLAR:
		if not frappe.db.exists("Item", name):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": name,
					"item_name": name,
					"item_group": group,
					"stock_uom": uom,
					"is_stock_item": 0,
					"is_sales_item": 1,
					"is_purchase_item": 1,
				}
			).insert(ignore_permissions=True)
