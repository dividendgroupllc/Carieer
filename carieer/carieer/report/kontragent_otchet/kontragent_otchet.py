# Kontragent Otchet ("Оборотка контрагентов") - Armada andozasi asosida.
# Har bir kontragent bo'yicha: boshlang'ich qoldiq, davr oboroti (kredit/debet), yakuniy qoldiq.
# Kredit qoldiq = biz qarzdormiz (masalan oldindan to'lov olingan), Debet qoldiq = kontragent bizdan qarzdor.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.utils import check_report_company

PARTY_NAME_FIELD = {"Customer": "customer_name", "Supplier": "supplier_name", "Employee": "employee_name", "Shareholder": "title"}
AMOUNT_FIELDS = (
	"opening_credit", "opening_debit", "period_credit", "period_debit", "final_credit", "final_debit",
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	check_report_company(filters)
	return get_columns(), get_data(filters)


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency", "width": 135}
	return [
		{"label": _("Контрагент тури"), "fieldname": "party_type", "fieldtype": "Data", "width": 110},
		{"label": _("Контрагент"), "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 200},
		{"label": _("Валюта"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 70},
		{"label": _("Акт сверка"), "fieldname": "akt_sverka", "fieldtype": "Data", "width": 110},
		{"label": _("Кредит (нач.)"), "fieldname": "opening_credit", **cur},
		{"label": _("Дебет (нач.)"), "fieldname": "opening_debit", **cur},
		{"label": _("Кредит (оборот)"), "fieldname": "period_credit", **cur},
		{"label": _("Дебет (оборот)"), "fieldname": "period_debit", **cur},
		{"label": _("Кредит (кон.)"), "fieldname": "final_credit", **cur},
		{"label": _("Дебет (кон.)"), "fieldname": "final_debit", **cur},
	]


def get_data(filters):
	cond = ["company = %(company)s", "ifnull(party, '') != ''", "ifnull(party_type, '') != ''", "is_cancelled = 0"]
	if filters.get("party_type"):
		cond.append("party_type = %(party_type)s")
	if filters.get("party"):
		cond.append("party = %(party)s")
	rows = frappe.db.sql(
		f"""select party_type, party, account_currency as currency,
			sum(if(posting_date < %(from_date)s, credit_in_account_currency, 0)) opening_credit,
			sum(if(posting_date < %(from_date)s, debit_in_account_currency, 0)) opening_debit,
			sum(if(posting_date >= %(from_date)s, credit_in_account_currency, 0)) period_credit,
			sum(if(posting_date >= %(from_date)s, debit_in_account_currency, 0)) period_debit
		from `tabGL Entry`
		where {" and ".join(cond)} and posting_date <= %(to_date)s
		group by party_type, party, account_currency
		order by party_type, party""",
		filters,
		as_dict=True,
	)
	data, totals = [], {}
	for r in rows:
		opening = flt(r.opening_credit) - flt(r.opening_debit)
		final = opening + flt(r.period_credit) - flt(r.period_debit)
		if not filters.get("show_zero") and not any((opening, r.period_credit, r.period_debit)):
			continue
		row = {
			"party_type": r.party_type,
			"party": r.party,
			"party_name": (PARTY_NAME_FIELD.get(r.party_type) and frappe.db.get_value(r.party_type, r.party, PARTY_NAME_FIELD[r.party_type])) or r.party,
			"currency": r.currency,
			"akt_sverka": _("Акт сверка"),
			"opening_credit": max(opening, 0),
			"opening_debit": abs(min(opening, 0)),
			"period_credit": flt(r.period_credit),
			"period_debit": flt(r.period_debit),
			"final_credit": max(final, 0),
			"final_debit": abs(min(final, 0)),
		}
		data.append(row)
		t = totals.setdefault(r.currency, {f: 0 for f in AMOUNT_FIELDS})
		for f in AMOUNT_FIELDS:
			t[f] += row[f]
	# Jami - har bir valyuta uchun alohida (so'm va dollarni qo'shib bo'lmaydi)
	for currency, t in totals.items():
		data.append({"party": _("ЖАМИ"), "currency": currency, "is_total_row": 1, **t})
	return data
