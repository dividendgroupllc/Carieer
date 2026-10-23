# BD Kontragent ("БД контрагент"): kontragentlar ro'yxati - Клиенты | Тип клиент | Остаток | Подпись.
# Остаток = Кредит - Дебет (firma valyutasida): musbat - biz kontragentga qarzdormiz, manfiy - u bizga qarzdor.
# Tur jadvaldagi kabi: Клиент, Поставщик, Прочие лица, Налог, Сотрудник. «Подпись» - akt imzosi uchun bo'sh ustun.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import (
	kontragent_turi,
	normalize_turi,
	party_types_for_turi,
	prepare,
	turi_ok,
)


def execute(filters=None):
	filters = prepare(filters, need_company=True)
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"label": _("Клиенты"),
			"fieldname": "party",
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 300,
		},
		{"label": "", "fieldname": "party_type", "fieldtype": "Data", "hidden": 1},
		{"label": _("Тип клиент"), "fieldname": "turi", "fieldtype": "Data", "width": 120},
		{"label": _("Остаток"), "fieldname": "balance", "fieldtype": "Currency", "options": "currency", "width": 160},
		{"label": _("Подпись"), "fieldname": "podpis", "fieldtype": "Data", "width": 220},
		{"label": "", "fieldname": "currency", "fieldtype": "Data", "hidden": 1},
	]


def get_data(filters):
	turi = normalize_turi(filters.get("turi"))
	party_types = party_types_for_turi(turi)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	balances = {
		(r.party_type, r.party): flt(r.net)
		for r in frappe.db.sql(
			"""select party_type, party, sum(credit) - sum(debit) net from `tabGL Entry`
			where company = %(company)s and is_cancelled = 0 and posting_date <= %(to_date)s
				and party_type in %(party_types)s and ifnull(party, '') != ''
			group by party_type, party""",
			{**filters, "party_types": party_types},
			as_dict=True,
		)
	}
	# bo'sh qoldiqli kontragentlar ham ro'yxatda turadi (jadvaldagidek): barcha mijoz va ta'minotchilar
	names = {}
	for pt in party_types:
		if pt == "Employee":
			continue
		for n in frappe.get_all(pt, filters={"disabled": 0}, pluck="name"):
			names[(pt, n)] = None
	keys = {*names, *balances}
	data = []
	for party_type, party in keys:
		if not turi_ok(turi, party_type, party):
			continue
		balance = flt(balances.get((party_type, party), 0), 2)
		if not balance and filters.get("only_balance"):
			continue
		data.append(
			{
				"party_type": party_type,
				"party": party,
				"turi": kontragent_turi(party_type, party),
				"balance": balance,
				"currency": currency,
			}
		)
	data.sort(key=lambda r: (r["turi"], r["party"]))
	return data
