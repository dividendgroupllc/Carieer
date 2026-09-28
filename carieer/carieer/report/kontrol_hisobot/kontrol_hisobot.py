# Kontrol Hisobot: karer sotuvlari (kun, mijoz, mashina, tovar bo'yicha) + to'lov/qarz nazorati.

import frappe
from frappe import _
from frappe.utils import flt

GROUPS = {
	"Mijoz": ("customer", _("Mijoz"), "Link", "Customer"),
	"Tovar": ("item_code", _("Tovar"), "Link", "Item"),
	"Kun": ("posting_date", _("Sana"), "Date", None),
	"Mashina": ("mashina_raqami", _("Mashina"), "Data", None),
	"Valyuta": ("currency", _("Valyuta"), "Link", "Currency"),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	group_by = filters.get("group_by")
	if group_by and group_by in GROUPS:
		columns, data = grouped(data, group_by)
	else:
		columns = get_columns()
	return columns, data, None, get_chart(filters), get_summary(filters)


def conditions(filters):
	cond = ["docstatus = 1", "posting_date between %(from_date)s and %(to_date)s"]
	for f in ("company", "customer", "item_code", "warehouse", "status", "currency"):
		if filters.get(f):
			cond.append(f"{f} = %({f})s")
	if filters.get("mashina_raqami"):
		cond.append("mashina_raqami like %(mashina_like)s")
		filters.mashina_like = f"%{filters.mashina_raqami}%"
	return " and ".join(cond)


def get_data(filters):
	return frappe.db.sql(
		f"""select name, posting_date, posting_time, customer, customer_name, mashina_raqami, haydovchi,
			item_code, item_name, qty, uom, stock_qty, rate, currency, amount, base_amount,
			total_paid, outstanding_amount, status, warehouse
		from `tabKarer Sotuv` where {conditions(filters)}
		order by posting_date, posting_time, name""",
		filters,
		as_dict=True,
	)


def get_columns():
	return [
		{"fieldname": "posting_date", "label": _("Sana"), "fieldtype": "Date", "width": 95},
		{"fieldname": "name", "label": _("Hujjat"), "fieldtype": "Link", "options": "Karer Sotuv", "width": 140},
		{"fieldname": "customer", "label": _("Mijoz"), "fieldtype": "Link", "options": "Customer", "width": 160},
		{"fieldname": "mashina_raqami", "label": _("Mashina"), "fieldtype": "Data", "width": 100},
		{"fieldname": "item_code", "label": _("Tovar"), "fieldtype": "Link", "options": "Item", "width": 120},
		{"fieldname": "qty", "label": _("Miqdor"), "fieldtype": "Float", "width": 90},
		{"fieldname": "uom", "label": _("Birlik"), "fieldtype": "Data", "width": 70},
		{"fieldname": "currency", "label": _("Valyuta"), "fieldtype": "Link", "options": "Currency", "width": 70},
		{"fieldname": "rate", "label": _("Narx"), "fieldtype": "Currency", "options": "currency", "width": 100},
		{"fieldname": "amount", "label": _("Summa"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "total_paid", "label": _("To'langan"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "outstanding_amount", "label": _("Qarz"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "base_amount", "label": _("Summa (UZS)"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "status", "label": _("Holat"), "fieldtype": "Data", "width": 110},
	]


def grouped(rows, group_by):
	key, label, ftype, options = GROUPS[group_by]
	out = {}
	for r in rows:
		k = (r[key], r.currency)
		g = out.setdefault(
			k,
			frappe._dict(group=r[key], currency=r.currency, count=0, stock_qty=0, amount=0, total_paid=0,
						 outstanding_amount=0, base_amount=0),
		)
		g.count += 1
		for f in ("stock_qty", "amount", "total_paid", "outstanding_amount", "base_amount"):
			g[f] += flt(r[f])
	col = {"fieldname": "group", "label": label, "fieldtype": ftype, "width": 180}
	if options:
		col["options"] = options
	columns = [
		col,
		{"fieldname": "count", "label": _("Reyslar soni"), "fieldtype": "Int", "width": 100},
		{"fieldname": "stock_qty", "label": _("Miqdor (ombor birligida)"), "fieldtype": "Float", "width": 150},
		{"fieldname": "currency", "label": _("Valyuta"), "fieldtype": "Link", "options": "Currency", "width": 80},
		{"fieldname": "amount", "label": _("Summa"), "fieldtype": "Currency", "options": "currency", "width": 140},
		{"fieldname": "total_paid", "label": _("To'langan"), "fieldtype": "Currency", "options": "currency", "width": 140},
		{"fieldname": "outstanding_amount", "label": _("Qarz"), "fieldtype": "Currency", "options": "currency", "width": 140},
		{"fieldname": "base_amount", "label": _("Summa (UZS)"), "fieldtype": "Currency", "width": 140},
	]
	return columns, sorted(out.values(), key=lambda d: (str(d.group), d.currency))


def get_summary(filters):
	rows = frappe.db.sql(
		f"""select currency, sum(amount) amount, sum(total_paid) paid, sum(outstanding_amount) debt, count(*) cnt
		from `tabKarer Sotuv` where {conditions(filters)} group by currency""",
		filters,
		as_dict=True,
	)
	summary = []
	for r in rows:
		summary += [
			{"label": _("Sotuv") + f" ({r.currency})", "value": r.amount, "datatype": "Currency", "currency": r.currency, "indicator": "Blue"},
			{"label": _("To'langan") + f" ({r.currency})", "value": r.paid, "datatype": "Currency", "currency": r.currency, "indicator": "Green"},
			{"label": _("Qarz") + f" ({r.currency})", "value": r.debt, "datatype": "Currency", "currency": r.currency, "indicator": "Red"},
		]
	if rows:
		summary.append({"label": _("Reyslar"), "value": sum(r.cnt for r in rows), "datatype": "Int"})
	return summary


def get_chart(filters):
	rows = frappe.db.sql(
		f"""select posting_date, sum(base_amount) total from `tabKarer Sotuv`
		where {conditions(filters)} group by posting_date order by posting_date""",
		filters,
		as_dict=True,
	)
	if not rows:
		return None
	return {
		"data": {
			"labels": [frappe.format(r.posting_date, "Date") for r in rows],
			"datasets": [{"name": _("Sotuv (UZS)"), "values": [flt(r.total) for r in rows]}],
		},
		"type": "bar",
		"fieldtype": "Currency",
	}
