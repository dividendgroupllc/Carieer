"""Bo'lim (Karer / Beton Zavod) bosh sahifasidagi raqamli kartochkalar (Number Card, type = Custom).

Kartochka filtri: {"tip": "Karer"} yoki {"tip": "Beton"} -> firma Zavod'dan olinadi.
Kassa va qarzlar GL Entry'dan hisoblanadi, shuning uchun faqat GL Entry'ni o'qiy oladigan rollar
(kassir, menejer) ko'radi (Number Card.document_type = GL Entry).
"""

import frappe
from frappe import _
from frappe.utils import flt

from carieer.permissions import check_company


def _company(filters) -> str | None:
	"""Zavod hali sozlanmagan bo'lsa (setup_karer ishlatilmagan) - None: kartochka 0 ko'rsatadi, xato chiqarmaydi."""
	filters = frappe.parse_json(filters) or {}
	tip = filters.get("tip") if isinstance(filters, dict) else "Karer"
	company = frappe.db.get_value("Zavod", tip, "company") if tip else None
	if not company or not check_company(company, throw=False):
		return None
	return company


def _empty():
	return {"value": 0, "fieldtype": "Currency"}


def _check_gl():
	if not frappe.has_permission("GL Entry", "read"):
		frappe.throw(_("Kassa va qarzlarni ko'rishga ruxsatingiz yo'q"), frappe.PermissionError)


@frappe.whitelist()
def kassa_qoldigi(filters=None):
	"""Barcha kassa va bank hisoblaridagi pul (firma valyutasida)."""
	_check_gl()
	company = _company(filters)
	if not company:
		return _empty()
	value = frappe.db.sql(
		"""select sum(gl.debit) - sum(gl.credit)
		from `tabGL Entry` gl join `tabAccount` a on a.name = gl.account
		where gl.company = %s and gl.is_cancelled = 0 and a.account_type in ('Cash', 'Bank')""",
		company,
	)[0][0]
	return {
		"value": flt(value, 2),
		"fieldtype": "Currency",
		"route": ["query-report", "DDS"],
		"route_options": {"company": company},
	}


@frappe.whitelist()
def mijozlar_qarzi(filters=None):
	"""Mijozlar bizdan qancha qarz (faqat musbat qoldiqlar, o'zimizning ikkinchi firmamizsiz)."""
	_check_gl()
	company = _company(filters)
	if not company:
		return _empty()
	value = frappe.db.sql(
		"""select sum(t.qoldiq) from (
			select sum(gl.debit) - sum(gl.credit) as qoldiq
			from `tabGL Entry` gl join `tabCustomer` c on c.name = gl.party
			where gl.company = %s and gl.is_cancelled = 0 and gl.party_type = 'Customer'
				and ifnull(c.is_internal_customer, 0) = 0
			group by gl.party having sum(gl.debit) - sum(gl.credit) > 0
		) t""",
		company,
	)[0][0]
	return {
		"value": flt(value, 2),
		"fieldtype": "Currency",
		"route": ["query-report", "Qarzdorlik"],
		"route_options": {"company": company},
	}
