# Firmalararo Qarzlar: Karer <-> Beton (va boshqa zavod firmalari) bir-biriga qancha qarz. Har bir firma o'z
# hisobida boshqa firmani ichki mijoz (Customer) va ichki ta'minotchi (Supplier) sifatida yuritadi (setup_firmalararo).
#   Фирма | Контрагент фирма | Debitor (bizga qarz) | Kreditor (biz qarzmiz) | Saldo | Uning hisobida | Farq
# Saldo musbat - kontragent firma bizga qarz. To'g'ri yuritilganda «Uning hisobida» = -Saldo, ya'ni «Farq» = 0.
# Farq bo'lsa - bir tomonda hujjat (to'lov, Приход) kiritilmagan.

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from carieer.permissions import get_allowed_companies


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.to_date = getdate(filters.get("to_date") or today())
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency"}
	return [
		{
			"label": _("Фирма"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 150,
		},
		# Data (Link emas): Frappe hisobot qatorlarini Link ustunlar bo'yicha User Permission bilan filtrlaydi - boshqa
		# firma Link bo'lsa xodim o'z qatorini ham ko'rmay qoladi
		{"label": _("Контрагент фирма"), "fieldname": "other", "fieldtype": "Data", "width": 150},
		{"label": _("Дебитор (бизга қарз)"), "fieldname": "debitor", **cur, "width": 160},
		{"label": _("Кредитор (биз қарзмиз)"), "fieldname": "kreditor", **cur, "width": 160},
		{"label": _("Сальдо"), "fieldname": "saldo", **cur, "width": 150},
		{"label": _("Унинг ҳисобида"), "fieldname": "mirror", **cur, "width": 150},
		{"label": _("Фарқ"), "fieldname": "farq", **cur, "width": 130},
		{"label": "", "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def party_balance(company, party_type, party, to_date) -> float:
	"""Kontragent saldosi firma valyutasida (debet - kredit)."""
	if not party:
		return 0
	return flt(
		frappe.db.sql(
			"""select sum(debit) - sum(credit) from `tabGL Entry`
			where company = %s and party_type = %s and party = %s and is_cancelled = 0 and posting_date <= %s""",
			(company, party_type, party, to_date),
		)[0][0]
	)


def internal_party(doctype: str, represents: str, company: str) -> str | None:
	"""Firmaning boshqa firmani ifodalovchi ichki mijozi / ta'minotchisi (shu firma bilan ishlashga ruxsat berilgan)."""
	flag = "is_internal_customer" if doctype == "Customer" else "is_internal_supplier"
	names = frappe.get_all(doctype, filters={flag: 1, "represents_company": represents}, pluck="name")
	for name in names:
		if frappe.db.exists(
			"Allowed To Transact With", {"parent": name, "parenttype": doctype, "company": company}
		):
			return name
	return names[0] if names else None


def balance(company, other, to_date) -> tuple[float, float]:
	"""company hisobida other firma: (debitor - bizga qarz, kreditor - biz qarzmiz)."""
	debitor = kreditor = 0
	for party_type in ("Customer", "Supplier"):
		value = party_balance(company, party_type, internal_party(party_type, other, company), to_date)
		debitor += max(value, 0)
		kreditor += max(-value, 0)
	return debitor, kreditor


def get_data(filters):
	companies = sorted(set(frappe.get_all("Zavod", pluck="company")))
	allowed = get_allowed_companies()
	out = []
	for company in companies:
		if allowed and company not in allowed:
			continue
		currency = frappe.get_cached_value("Company", company, "default_currency")
		for other in companies:
			if other == company:
				continue
			debitor, kreditor = balance(company, other, filters.to_date)
			their_debitor, their_kreditor = balance(other, company, filters.to_date)
			saldo = debitor - kreditor
			mirror = their_debitor - their_kreditor
			out.append(
				{
					"company": company,
					"other": other,
					"debitor": debitor,
					"kreditor": kreditor,
					"saldo": saldo,
					"mirror": mirror,
					"farq": flt(saldo + mirror, 2),
					"currency": currency,
				}
			)
	return out


def get_summary(data):
	if not data:
		return []
	currency = data[0]["currency"]
	farq = sum(abs(flt(r["farq"])) for r in data)
	return [
		{
			"label": _("Kontragent firmalar bizga qarz"),
			"value": sum(flt(r["debitor"]) for r in data),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green",
		},
		{
			"label": _("Biz qarzmiz"),
			"value": sum(flt(r["kreditor"]) for r in data),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Red",
		},
		{
			"label": _("Ikki tomon farqi"),
			"value": farq,
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green" if farq < 0.01 else "Orange",
		},
	]
