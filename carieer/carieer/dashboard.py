"""Bo'limlar (Karer, Beton Zavod, Sotuv operator) dashboardidagi raqamli kartochkalar (Number Card, type=Custom).

Kartochka filtri: {"tip": "Karer"} yoki {"tip": "Beton"} -> firma Karer Sozlamalari'dan olinadi (Sotuv'dagi kabi).
Kassa qoldig'i va qarzlar GL Entry'dan hisoblanadi, shuning uchun faqat GL Entry'ni o'qiy oladigan rollar
(kassir, menejer) ko'radi; operatorga kartochka ko'rinmaydi (Number Card.document_type = GL Entry).
"""

import frappe
from frappe import _
from frappe.utils import flt, today

from carieer.carieer.doctype.sotuv.sotuv import company_for_tip
from carieer.carieer.report.kassa_va_qarzlar.kassa_va_qarzlar import qarzlar
from carieer.utils import get_allowed_companies, get_company_currency


def _company(filters) -> str:
	filters = frappe.parse_json(filters) or {}
	tip = filters.get("tip") if isinstance(filters, dict) else None
	company = company_for_tip(tip or "Karer")
	allowed = get_allowed_companies()
	if allowed and company not in allowed:
		frappe.throw(_("{0} firmasi ma'lumotlarini ko'rishga ruxsatingiz yo'q").format(company), frappe.PermissionError)
	return company


def _check_gl():
	if not frappe.has_permission("GL Entry", "read"):
		frappe.throw(_("Kassa va qarzlarni ko'rishga ruxsatingiz yo'q"), frappe.PermissionError)


def _card(value, company):
	return {
		"value": flt(value, 2),
		"fieldtype": "Currency",
		"route": ["query-report", "Kassa va Qarzlar"],
		"route_options": {"company": company},
	}


@frappe.whitelist()
def kassa_qoldigi(filters=None):
	"""Barcha kassa va bank hisoblaridagi pul (firma valyutasida)."""
	_check_gl()
	company = _company(filters)
	value = frappe.db.sql(
		"""select sum(gl.debit) - sum(gl.credit)
		from `tabGL Entry` gl
		join `tabAccount` a on a.name = gl.account
		where gl.company = %s and gl.is_cancelled = 0 and a.account_type in ('Cash', 'Bank')""",
		company,
	)[0][0]
	return _card(value, company)


@frappe.whitelist()
def mijozlar_qarzi(filters=None):
	"""Mijozlar bizdan qancha qarz (debitorlar, o'zimizning ikkinchi firmamizsiz)."""
	_check_gl()
	company = _company(filters)
	debitorlar, _kreditorlar = qarzlar(frappe._dict(company=company, to_date=today()), get_company_currency(company))
	return _card(sum(flt(r["somda"]) for r in debitorlar if r["link_doctype"] == "Customer"), company)
