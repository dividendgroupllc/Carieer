# Qarzdorlik ("Қарздорликлар"): mijozlarning to'lanmagan sotuvlari muddat bo'yicha.
# Google Sheets'dagi "Карздорликлар" varag'i: mijoz, jami qarz, 7 kun ichida, 7 kundan ko'p, 14 kundan ko'p.
# Manba: submit qilingan, qoldig'i bor Sales Invoice'lar (Sotuv shularni yaratadi). Muddat = hisobot sanasi - sotuv sanasi.
# Summalar mijoz (debitor) hisobi valyutasida.

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate

from carieer.utils import check_report_company

BUCKETS = ("d0_7", "d8_14", "d15")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	check_report_company(filters)
	filters.to_date = getdate(filters.get("to_date") or nowdate())
	return get_columns(), get_data(filters)


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency", "width": 150}
	return [
		{"label": _("Мижоз"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 220},
		{"label": _("Номи"), "fieldname": "customer_name", "fieldtype": "Data", "width": 180},
		{"label": _("Валюта"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 70},
		{"label": _("Жами қарз"), "fieldname": "total", **cur},
		{"label": _("7 кун ичи"), "fieldname": "d0_7", **cur},
		{"label": _("7 кундан кўп"), "fieldname": "d8_14", **cur},
		{"label": _("14 кундан кўп"), "fieldname": "d15", **cur},
		{"label": _("Энг эски қарз (кун)"), "fieldname": "max_days", "fieldtype": "Int", "width": 130},
		{"label": _("Ҳужжатлар сони"), "fieldname": "count", "fieldtype": "Int", "width": 110},
	]


def get_data(filters):
	cond = ["docstatus = 1", "outstanding_amount > 0.005", "posting_date <= %(to_date)s"]
	if filters.get("company"):
		cond.append("company = %(company)s")
	if filters.get("customer"):
		cond.append("customer = %(customer)s")
	invoices = frappe.db.sql(
		f"""select customer, customer_name, party_account_currency as currency, posting_date, outstanding_amount
		from `tabSales Invoice` where {" and ".join(cond)}""",
		filters,
		as_dict=True,
	)
	out, totals = {}, {}
	for inv in invoices:
		days = max(date_diff(filters.to_date, inv.posting_date), 0)
		bucket = "d0_7" if days <= 7 else "d8_14" if days <= 14 else "d15"
		row = out.setdefault(
			(inv.customer, inv.currency),
			frappe._dict(customer=inv.customer, customer_name=inv.customer_name, currency=inv.currency,
						 total=0, d0_7=0, d8_14=0, d15=0, max_days=0, count=0),
		)
		amount = flt(inv.outstanding_amount)
		row.total += amount
		row[bucket] += amount
		row.max_days = max(row.max_days, days)
		row.count += 1
		t = totals.setdefault(inv.currency, frappe._dict(total=0, d0_7=0, d8_14=0, d15=0, count=0))
		t.total += amount
		t[bucket] += amount
		t.count += 1

	data = sorted(out.values(), key=lambda r: (r.currency or "", -r.total))
	# Jami - har bir valyuta uchun alohida (so'm va dollarni qo'shib bo'lmaydi)
	for currency, t in totals.items():
		data.append({"customer_name": _("ЖАМИ"), "currency": currency, "is_total_row": 1, **t})
	return data
