# Kontrol Hisobot: karer sotuvlari (kun, mijoz, mashina, tovar bo'yicha) + to'lov/qarz nazorati.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.utils import check_report_company

GROUPS = {
	"Mijoz": ("customer", _("Mijoz"), "Link", "Customer"),
	"Tovar": ("item_code", _("Tovar"), "Link", "Item"),
	"Kun": ("posting_date", _("Sana"), "Date", None),
	"Mashina": ("mashina_raqami", _("Mashina"), "Data", None),
	"Valyuta": ("currency", _("Valyuta"), "Link", "Currency"),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	check_report_company(filters)
	data = get_data(filters)
	group_by = filters.get("group_by")
	if group_by and group_by in GROUPS:
		columns, data = grouped(data, group_by)
	else:
		columns = get_columns()
	return columns, data, None, get_chart(filters), get_summary(filters)


def conditions(filters, alias="ks"):
	cond = [f"{alias}.docstatus = 1", f"{alias}.posting_date between %(from_date)s and %(to_date)s"]
	for f in ("company", "customer", "status", "currency", "tip"):
		if filters.get(f):
			cond.append(f"{alias}.{f} = %({f})s")
	if filters.get("mashina_raqami"):
		cond.append(f"{alias}.mashina_raqami like %(mashina_like)s")
		filters.mashina_like = f"%{filters.mashina_raqami}%"
	if filters.get("item_code"):
		cond.append(
			f"""exists(select 1 from `tabSotuv Tovar` t where t.parent = {alias}.name and t.item_code = %(item_code)s)"""
		)
	return " and ".join(cond)


def get_data(filters):
	"""Har bir tovar va xizmat qatori alohida ("Продажа карьер" varag'idagi kabi).
	To'langan / qarz hujjat bo'yicha - faqat hujjatning birinchi qatorida ko'rsatiladi."""
	rows = frappe.db.sql(
		f"""select ks.name, ks.posting_date, ks.posting_time, ks.tip, ks.customer, ks.customer_name, ks.mashina_raqami,
			ks.currency, ks.conversion_rate, ks.total_paid, ks.outstanding_amount, ks.status,
			t.item_code, t.item_name, t.qty, t.uom, t.stock_qty, t.rate, t.amount, t.warehouse, t.idx, 0 as is_service
		from `tabSotuv` ks join `tabSotuv Tovar` t on t.parent = ks.name
		where {conditions(filters)}
		union all
		select ks.name, ks.posting_date, ks.posting_time, ks.tip, ks.customer, ks.customer_name, ks.mashina_raqami,
			ks.currency, ks.conversion_rate, ks.total_paid, ks.outstanding_amount, ks.status,
			x.xizmat, x.xizmat, x.qty, '', 0, x.rate, x.amount, '', 100 + x.idx, 1
		from `tabSotuv` ks join `tabSotuv Xizmat` x on x.parent = ks.name
		where {conditions(filters)} and %(show_services)s = 1
		order by posting_date, posting_time, name, idx""",
		dict(filters, show_services=0 if filters.get("item_code") else 1),
		as_dict=True,
	)
	seen = set()
	for r in rows:
		r.base_amount = flt(r.amount) * flt(r.conversion_rate or 1)
		if r.name in seen:
			r.total_paid = r.outstanding_amount = 0
			r.status = ""
		seen.add(r.name)
	return rows


def get_columns():
	return [
		{"fieldname": "posting_date", "label": _("Дата"), "fieldtype": "Date", "width": 95},
		{"fieldname": "name", "label": _("Hujjat"), "fieldtype": "Link", "options": "Sotuv", "width": 130},
		{"fieldname": "tip", "label": _("Тип"), "fieldtype": "Data", "width": 70},
		{"fieldname": "item_code", "label": _("Наименование"), "fieldtype": "Link", "options": "Item", "width": 120},
		{"fieldname": "qty", "label": _("Кол-во"), "fieldtype": "Float", "width": 80},
		{"fieldname": "uom", "label": _("Ед.изм"), "fieldtype": "Data", "width": 70},
		{"fieldname": "rate", "label": _("Цена"), "fieldtype": "Currency", "options": "currency", "width": 100},
		{"fieldname": "currency", "label": _("Валюта"), "fieldtype": "Link", "options": "Currency", "width": 65},
		{"fieldname": "amount", "label": _("Сумма"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "customer", "label": _("Клиент"), "fieldtype": "Link", "options": "Customer", "width": 150},
		{"fieldname": "mashina_raqami", "label": _("Номер машины"), "fieldtype": "Data", "width": 110},
		{"fieldname": "conversion_rate", "label": _("Курс"), "fieldtype": "Float", "precision": 2, "width": 80},
		{"fieldname": "base_amount", "label": _("Сумма (сўм)"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "total_paid", "label": _("Оплачено"), "fieldtype": "Currency", "options": "currency", "width": 110},
		{"fieldname": "outstanding_amount", "label": _("Долг"), "fieldtype": "Currency", "options": "currency", "width": 110},
		{"fieldname": "status", "label": _("Holat"), "fieldtype": "Data", "width": 100},
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
		g.count += 0 if r.name in g.setdefault("docs", set()) else 1
		g.docs.add(r.name)
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
		from `tabSotuv` ks where {conditions(filters)} group by currency""",
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
		f"""select posting_date, sum(base_amount) total from `tabSotuv` ks
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
