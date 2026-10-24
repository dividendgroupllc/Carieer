# «Panel Karer» / «Panel Beton» raqamli kartalari (Number Card, turi Custom).
# Karta filtri: {"zavod": "Karer"}. Summalar firma valyutasida (so'm): USD sotuv va kassalar kurs bilan.

import frappe
from frappe import _
from frappe.utils import get_first_day, nowdate

from carieer.permissions import check_company
from carieer.utils import get_company_currency, kassalar_jami


def get_company(filters) -> str:
	zavod = frappe.parse_json(filters or "{}").get("zavod")
	company = frappe.db.get_value("Zavod", zavod, "company") if zavod else None
	if not company:
		frappe.throw(_("Zavod topilmadi: {0}").format(zavod))
	check_company(company)
	return company


def money(value, company) -> dict:
	return {"value": value or 0, "fieldtype": "Currency", "currency": get_company_currency(company)}


def sotuv_summa(company, from_date) -> float:
	return frappe.db.sql(
		"""select sum(base_amount) from `tabSotuv`
		where company = %s and docstatus = 1 and posting_date between %s and %s""",
		(company, from_date, nowdate()),
	)[0][0]


@frappe.whitelist()
def bugungi_sotuv(filters=None) -> dict:
	frappe.has_permission("Sotuv", "read", throw=True)
	company = get_company(filters)
	return money(sotuv_summa(company, nowdate()), company)


@frappe.whitelist()
def oylik_sotuv(filters=None) -> dict:
	frappe.has_permission("Sotuv", "read", throw=True)
	company = get_company(filters)
	return money(sotuv_summa(company, get_first_day(nowdate())), company)


@frappe.whitelist()
def debitor_qarz(filters=None) -> dict:
	"""Mijozlarning bizga qarzi (Кардорликлар jami): mijoz hisoblaridagi debet - kredit."""
	frappe.has_permission("Sotuv", "read", throw=True)
	company = get_company(filters)
	value = frappe.db.sql(
		"""select sum(debit - credit) from `tabGL Entry`
		where company = %s and party_type = 'Customer' and is_cancelled = 0""",
		company,
	)[0][0]
	return money(value, company)


@frappe.whitelist()
def kassa_qoldigi(filters=None) -> dict:
	frappe.has_permission("Kassa", "read", throw=True)
	company = get_company(filters)
	return money(kassalar_jami(company), company)
