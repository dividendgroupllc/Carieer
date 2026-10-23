# Postav Klient Fakt ("Постав Клиент Факт"): kontragent qoldig'i DOLLAR ekvivalentida, har oy oxiriga, o'sha oy kursi bilan.
# Yuqorida «Курс» qatori (oyning oxirgi kuniga USD kursi), pastda har kontragent. Qoldiq = Кредит - Дебет
# (musbat - biz qarzdormiz, manfiy - kontragent bizga qarzdor), kumulyativ. So'm hisobidagilar oy kursiga bo'linadi,
# dollar hisobidagilar o'z holicha qo'shiladi.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import (
	bold,
	kontragent_turi,
	normalize_turi,
	party_types_for_turi,
	prepare,
	turi_ok,
	usd_rate,
)
from carieer.carieer.report.moliya import get_months


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	return get_columns(months), get_data(filters, months)


def get_columns(months):
	cols = [
		{"label": _("Тип контрагента"), "fieldname": "turi", "fieldtype": "Data", "width": 110},
		{"label": "", "fieldname": "party_type", "fieldtype": "Data", "hidden": 1},
		{
			"label": _("Контрагент"),
			"fieldname": "party",
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 220,
		},
	]
	for m in months:
		cols.append(
			{"label": m.label, "fieldname": m.fieldname, "fieldtype": "Float", "precision": "2", "width": 120}
		)
	return cols


def get_data(filters, months):
	turi = normalize_turi(filters.get("turi"))
	filters.party_types = party_types_for_turi(turi)
	company_currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	rows = frappe.db.sql(
		"""select party_type, party, date_format(posting_date, '%%Y-%%m') ym, account_currency currency,
			sum(credit_in_account_currency) - sum(debit_in_account_currency) net
		from `tabGL Entry`
		where company = %(company)s and is_cancelled = 0 and posting_date <= %(to_date)s
			and party_type in %(party_types)s and ifnull(party, '') != ''
		group by party_type, party, ym, account_currency""",
		filters,
		as_dict=True,
	)
	per_party = {}
	for r in rows:
		if turi_ok(turi, r.party_type, r.party):
			per_party.setdefault((r.party_type, r.party), []).append(r)

	cache = {}
	rates = {m.key: usd_rate(filters.company, m.end, cache) for m in months}
	data = []
	for (party_type, party), entries in per_party.items():
		row = {"party_type": party_type, "party": party, "turi": kontragent_turi(party_type, party)}
		for m in months:
			total = 0.0
			for e in entries:
				if e.ym > m.key:
					continue
				if e.currency == company_currency:
					total += flt(e.net) / rates[m.key] if rates[m.key] else 0.0
				elif e.currency == "USD":
					total += flt(e.net)
			row[m.fieldname] = flt(total, 2)
		if filters.get("show_zero") or any(abs(row[m.fieldname]) >= 0.005 for m in months):
			data.append(row)
	data.sort(key=lambda r: (r["turi"], r["party"]))
	if not data:
		return []

	def total(label, pick):
		return {"turi": bold(label), **{m.fieldname: sum(pick(flt(r[m.fieldname])) for r in data) for m in months}}

	head = [
		{"turi": bold(_("Курс")), **{m.fieldname: rates[m.key] or None for m in months}},
		total(_("Бизнинг қарз (кредитор, +)"), lambda v: max(v, 0)),
		total(_("Бизга қарз (дебитор, −)"), lambda v: min(v, 0)),
		total(_("Жами"), lambda v: v),
	]
	for r in data:
		for m in months:
			if abs(flt(r.get(m.fieldname))) < 0.005:
				r[m.fieldname] = None
	return [*head, *data]
