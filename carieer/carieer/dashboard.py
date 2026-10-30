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


def kassa_harakati(company) -> tuple[float, float]:
	"""Bugun kassalarga tushgan va ulardan chiqqan pul (so'mda): Kassa, Sotuv to'lovi, Payment Entry - hammasi
	kassa hisoblaridagi buxgalteriya yozuvidan. Kassalar orasidagi o'tkazma (ikkala tomoni kassa) kirmaydi."""
	accounts = frappe.db.sql_list(
		"""select distinct a.default_account from `tabMode of Payment Account` a
		join `tabMode of Payment` m on m.name = a.parent
		where a.company = %s and m.enabled = 1 and ifnull(a.default_account, '') != ''""",
		company,
	)
	if not accounts:
		return 0.0, 0.0
	kirim, chiqim = frappe.db.sql(
		"""select sum(debit), sum(credit) from `tabGL Entry`
		where company = %(company)s and is_cancelled = 0 and posting_date = %(today)s and account in %(accounts)s
			and voucher_no not in (
				select voucher_no from `tabGL Entry`
				where company = %(company)s and is_cancelled = 0 and posting_date = %(today)s
					and account in %(accounts)s
				group by voucher_no having sum(debit) > 0 and sum(credit) > 0
			)""",
		{"company": company, "today": nowdate(), "accounts": accounts},
	)[0]
	return kirim or 0.0, chiqim or 0.0


@frappe.whitelist()
def bugungi_kirim(filters=None) -> dict:
	frappe.has_permission("Kassa", "read", throw=True)
	company = get_company(filters)
	return money(kassa_harakati(company)[0], company)


@frappe.whitelist()
def bugungi_chiqim(filters=None) -> dict:
	frappe.has_permission("Kassa", "read", throw=True)
	company = get_company(filters)
	return money(kassa_harakati(company)[1], company)
