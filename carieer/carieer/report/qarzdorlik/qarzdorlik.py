# Qarzdorlik ("Қарздорликлар"): kim qancha qarz va qarz qancha vaqtdan beri turibdi.
# Jadvaldagi «Карздорликлар» varag'i: Клиент | Сумма долга (sof qoldiq, manfiy = biz qarzmiz) |
#   7 кун ичи | 7 кундан кўп | 14 кундан кўп | 21 кундан кўп | энг эски қарз (кун).
# Manba - GL (buxgalteriya daftari): sotuv, nachislenie, boshlang'ich qoldiq, to'lovlar hammasi hisobga olinadi.
# Muddat FIFO bo'yicha: to'lovlar eng eski qarzni yopadi, qolgan qarz o'z sanasi bo'yicha muddatga ajratiladi.

import frappe
from frappe import _
from frappe.utils import date_diff, flt

from carieer.carieer.report.common import blank_zeros, bold, prepare

BUCKETS = ("d0_7", "d8_14", "d15_21", "d21")
NAME_FIELD = {"Customer": "customer_name", "Supplier": "supplier_name", "Employee": "employee_name"}
TURI = {"Mijozlar": "Customer", "Ta'minotchilar": "Supplier", "Xodimlar": "Employee"}


def execute(filters=None):
	filters = prepare(filters)
	filters.party_type = TURI.get(filters.get("turi") or "Mijozlar", "Customer")
	return get_columns(filters), blank_zeros(
		get_data(filters), ("d0_7", "d8_14", "d15_21", "d21", "max_days")
	)


def get_columns(filters):
	cur = {"fieldtype": "Currency", "options": "currency", "width": 140}
	return [
		{"label": "", "fieldname": "party_type", "fieldtype": "Data", "hidden": 1},
		{
			"label": _("Контрагент"),
			"fieldname": "party",
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 200,
		},
		{"label": _("Номи"), "fieldname": "party_name", "fieldtype": "Data", "width": 180},
		{
			"label": _("Валюта"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"width": 70,
		},
		{"label": _("Сумма долга (соф)"), "fieldname": "qoldiq", **cur},
		{"label": _("7 кун ичи"), "fieldname": "d0_7", **cur},
		{"label": _("7 кундан кўп"), "fieldname": "d8_14", **cur},
		{"label": _("14 кундан кўп"), "fieldname": "d15_21", **cur},
		{"label": _("21 кундан кўп"), "fieldname": "d21", **cur},
		{"label": _("Энг эски қарз (кун)"), "fieldname": "max_days", "fieldtype": "Int", "width": 120},
	]


def get_data(filters):
	cond = [
		"company = %(company)s",
		"party_type = %(party_type)s",
		"is_cancelled = 0",
		"posting_date <= %(to_date)s",
	]
	if filters.get("party"):
		cond.append("party = %(party)s")
	if not filters.get("ichki_firma"):
		# o'zimizning ikkinchi firmamiz - «Firmalararo qarzlar» hisobotida
		table = {"Customer": "Customer", "Supplier": "Supplier"}.get(filters.party_type)
		if table:
			flag = "is_internal_customer" if table == "Customer" else "is_internal_supplier"
			cond.append(f"party not in (select name from `tab{table}` where {flag} = 1)")
	entries = frappe.db.sql(
		f"""select party, account_currency currency, posting_date,
			sum(debit_in_account_currency) debit, sum(credit_in_account_currency) credit
		from `tabGL Entry` where {" and ".join(cond)}
		group by party, account_currency, posting_date
		order by party, account_currency, posting_date""",
		filters,
		as_dict=True,
	)
	sign = 1 if filters.party_type == "Customer" else -1  # ta'minotchi: biz qarz bo'lsak musbat
	by_party = {}
	for e in entries:
		by_party.setdefault((e.party, e.currency), []).append(e)

	data, totals = [], {}
	for (party, currency), rows in by_party.items():
		qoldiq = sign * sum(flt(r.debit) - flt(r.credit) for r in rows)
		if abs(qoldiq) < 0.5 and not filters.get("show_zero"):
			continue
		row = frappe._dict(
			party_type=filters.party_type,
			party=party,
			party_name=frappe.db.get_value(filters.party_type, party, NAME_FIELD[filters.party_type])
			or party,
			currency=currency,
			qoldiq=flt(qoldiq, 2),
			max_days=0,
			**{b: 0 for b in BUCKETS},
		)
		if qoldiq > 0:
			age_buckets(row, rows, sign, filters.to_date)
		data.append(row)
		t = totals.setdefault(currency, {"qoldiq": 0, **{b: 0 for b in BUCKETS}})
		for f in ("qoldiq", *BUCKETS):
			t[f] += flt(row[f])

	data.sort(key=lambda r: (r.currency or "", -r.qoldiq))
	for currency, t in totals.items():
		data.append({"party_name": bold(_("ЖАМИ")), "currency": currency, **t})
	return data


def age_buckets(row, rows, sign, to_date):
	"""FIFO: barcha to'lovlar (kamaytiruvchi yozuvlar) eng eski qarzlarni yopadi."""
	increases = []  # [(sana, summa)]
	decrease = 0.0
	for r in rows:
		net = sign * (flt(r.debit) - flt(r.credit))
		if net > 0:
			increases.append([r.posting_date, net])
		else:
			decrease += -net
	for item in increases:
		if decrease <= 0:
			break
		used = min(item[1], decrease)
		item[1] -= used
		decrease -= used
	for date, amount in increases:
		if amount < 0.005:
			continue
		days = max(date_diff(to_date, date), 0)
		bucket = "d0_7" if days <= 7 else "d8_14" if days <= 14 else "d15_21" if days <= 21 else "d21"
		row[bucket] = flt(row[bucket] + amount, 2)
		row.max_days = max(row.max_days, days)
