# Material Hisobot (материальный отчёт): tovar + ombor bo'yicha
# boshlang'ich qoldiq -> kirim (qazib olindi / ishlab chiqarildi / xarid / firmalararo / boshqa)
# -> chiqim (sotildi / ishlab chiqarishga sarf / texnikaga / boshqa) -> yakuniy qoldiq va qiymati.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.utils import check_report_company

IN_COLS = [
	("kirim_qazish", _("Qazib olindi")),
	("kirim_ishlab", _("Ishlab chiqarildi")),
	("kirim_xarid", _("Xarid")),
	("kirim_kochirish", _("Ko'chirib kelindi")),
	("kirim_boshqa", _("Boshqa kirim")),
]
OUT_COLS = [
	("chiqim_sotuv", _("Sotildi")),
	("chiqim_ishlab", _("Ishlab chiqarishga")),
	("chiqim_kochirish", _("Boshqa omborga ko'chirildi")),
	("chiqim_boshqa", _("Boshqa chiqim (texnika, spisaniye)")),
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	check_report_company(filters)
	return get_columns(), get_data(filters)


def get_columns():
	cols = [
		{"fieldname": "item_code", "label": _("Tovar"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Nomi"), "fieldtype": "Data", "width": 140},
		{"fieldname": "warehouse", "label": _("Ombor"), "fieldtype": "Link", "options": "Warehouse", "width": 150},
		{"fieldname": "stock_uom", "label": _("Birlik"), "fieldtype": "Data", "width": 60},
		{"fieldname": "opening_qty", "label": _("Boshlang'ich qoldiq"), "fieldtype": "Float", "width": 120},
	]
	for f, label in IN_COLS + OUT_COLS:
		cols.append({"fieldname": f, "label": label, "fieldtype": "Float", "width": 110})
	cols += [
		{"fieldname": "closing_qty", "label": _("Yakuniy qoldiq"), "fieldtype": "Float", "width": 120},
		{"fieldname": "closing_value", "label": _("Qoldiq qiymati"), "fieldtype": "Currency", "width": 130},
	]
	return cols


def get_data(filters):
	cond = ["sle.is_cancelled = 0", "sle.posting_date <= %(to_date)s"]
	if filters.get("company"):
		cond.append("sle.company = %(company)s")
	if filters.get("item_code"):
		cond.append("sle.item_code = %(item_code)s")
	if filters.get("warehouse"):
		lft, rgt = frappe.db.get_value("Warehouse", filters.warehouse, ["lft", "rgt"])
		cond.append(f"sle.warehouse in (select name from `tabWarehouse` where lft >= {int(lft)} and rgt <= {int(rgt)})")

	rows = frappe.db.sql(
		f"""select sle.item_code, sle.warehouse, sle.posting_date, sle.actual_qty, sle.stock_value_difference,
			sle.voucher_type, sle.voucher_no, se.purpose
		from `tabStock Ledger Entry` sle
		left join `tabStock Entry` se on sle.voucher_type = 'Stock Entry' and se.name = sle.voucher_no
		where {" and ".join(cond)}""",
		filters,
		as_dict=True,
	)

	qazish_se = set(frappe.get_all("Qazib Olish", filters={"docstatus": 1}, pluck="stock_entry"))
	from_date = frappe.utils.getdate(filters.from_date)
	out = {}
	for r in rows:
		key = (r.item_code, r.warehouse)
		d = out.setdefault(key, frappe._dict(item_code=r.item_code, warehouse=r.warehouse, opening_qty=0, closing_qty=0, closing_value=0))
		qty = flt(r.actual_qty)
		d.closing_qty += qty
		d.closing_value += flt(r.stock_value_difference)
		if r.posting_date < from_date:
			d.opening_qty += qty
			continue
		col = classify(r, qty, qazish_se)
		d[col] = flt(d.get(col)) + abs(qty)

	items = {}
	if out:
		for it in frappe.get_all(
			"Item", filters={"name": ["in", list({k[0] for k in out})]}, fields=["name", "item_name", "stock_uom"]
		):
			items[it.name] = it

	data = []
	for (item_code, _wh), d in sorted(out.items()):
		it = items.get(item_code) or {}
		d.item_name = it.get("item_name")
		d.stock_uom = it.get("stock_uom")
		if not filters.get("show_zero") and not any(
			flt(d.get(f)) for f in ["opening_qty", "closing_qty"] + [c[0] for c in IN_COLS + OUT_COLS]
		):
			continue
		data.append(d)
	return data


def classify(r, qty, qazish_se):
	vt, purpose = r.voucher_type, r.purpose
	if qty > 0:
		if vt == "Stock Entry" and r.voucher_no in qazish_se:
			return "kirim_qazish"
		if vt == "Stock Entry" and purpose in ("Manufacture", "Repack"):
			return "kirim_ishlab"
		if vt in ("Purchase Receipt", "Purchase Invoice"):
			return "kirim_xarid"
		if vt == "Stock Entry" and purpose == "Material Transfer":
			return "kirim_kochirish"
		return "kirim_boshqa"
	if vt in ("Sales Invoice", "Delivery Note", "POS Invoice"):
		return "chiqim_sotuv"
	if vt == "Stock Entry" and purpose in ("Manufacture", "Repack", "Material Consumption for Manufacture"):
		return "chiqim_ishlab"
	if vt == "Stock Entry" and purpose == "Material Transfer":
		return "chiqim_kochirish"
	return "chiqim_boshqa"
