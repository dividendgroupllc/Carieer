"""Bo'lim (Karer / Beton Zavod) bosh sahifasidagi raqamli kartochkalar (Number Card, type = Custom).

Kartochka filtri: {"tip": "Karer"} yoki {"tip": "Beton"} -> firma Zavod'dan olinadi (utils.company_for_bolim:
Zavod «Beton Zavod» deb nomlangan bo'lsa ham topiladi). Hamma kartochka FIRMA bo'yicha hisoblanadi - shuning uchun
bir firmaning hujjati ikkinchi bo'lim kartochkasiga tushmaydi.
Kassa va qarzlar GL Entry'dan hisoblanadi, shuning uchun faqat GL Entry'ni o'qiy oladigan rollar
(kassir, menejer) ko'radi (Number Card.document_type = GL Entry).
"""

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, get_last_day, nowdate

from carieer.permissions import check_company
from carieer.utils import company_for_bolim


def _company(filters) -> str | None:
	"""Zavod hali sozlanmagan bo'lsa - None: kartochka 0 ko'rsatadi, xato chiqarmaydi."""
	filters = frappe.parse_json(filters) or {}
	tip = filters.get("tip") if isinstance(filters, dict) else None
	company = company_for_bolim(tip or "Karer")
	if not company or not check_company(company, throw=False):
		return None
	return company


def _empty(fieldtype="Currency"):
	return {"value": 0, "fieldtype": fieldtype}


def _check(doctype):
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("{0} ni ko'rishga ruxsatingiz yo'q").format(_(doctype)), frappe.PermissionError)


def _sotuv_summa(company, from_date, to_date):
	"""Tasdiqlangan sotuvlar summasi firma valyutasida (base_amount)."""
	return flt(
		frappe.db.sql(
			"""select sum(base_amount) from `tabSotuv`
			where company = %s and docstatus = 1 and posting_date between %s and %s""",
			(company, from_date, to_date),
		)[0][0],
		2,
	)


# ------------------------------------------------------------------ sotuv
@frappe.whitelist()
def bugungi_sotuv(filters=None):
	_check("Sotuv")
	company = _company(filters)
	if not company:
		return _empty()
	today = nowdate()
	return {
		"value": _sotuv_summa(company, today, today),
		"fieldtype": "Currency",
		"route": ["List", "Sotuv"],
		"route_options": {"company": company, "posting_date": today, "docstatus": 1},
	}


@frappe.whitelist()
def oylik_sotuv(filters=None):
	_check("Sotuv")
	company = _company(filters)
	if not company:
		return _empty()
	today = nowdate()
	return {
		"value": _sotuv_summa(company, get_first_day(today), get_last_day(today)),
		"fieldtype": "Currency",
		"route": ["List", "Sotuv"],
		"route_options": {"company": company, "docstatus": 1},
	}


@frappe.whitelist()
def qarzga_sotuvlar(filters=None):
	"""Tasdiqlangan sotuvlardagi to'lanmagan qoldiq. Sotuv dollarda bo'lsa ham firma valyutasiga o'tkaziladi."""
	_check("Sotuv")
	company = _company(filters)
	if not company:
		return _empty()
	value = frappe.db.sql(
		"""select sum(outstanding_amount * ifnull(nullif(conversion_rate, 0), 1)) from `tabSotuv`
		where company = %s and docstatus = 1 and outstanding_amount > 0""",
		company,
	)[0][0]
	return {
		"value": flt(value, 2),
		"fieldtype": "Currency",
		"route": ["List", "Sotuv"],
		"route_options": {"company": company, "docstatus": 1, "outstanding_amount": [">", 0]},
	}


@frappe.whitelist()
def tasdiqlanmagan_sotuv(filters=None):
	"""Saqlangan, lekin tasdiqlanmagan (Draft) sotuvlar: ular sotuv, qarz va ombor hisobiga KIRMAYDI.
	Operator «Submit» bosishni unutgan bo'lsa shu yerda ko'rinadi."""
	_check("Sotuv")
	company = _company(filters)
	if not company:
		return _empty()
	value = frappe.db.sql(
		"""select sum(base_amount) from `tabSotuv` where company = %s and docstatus = 0""", company
	)[0][0]
	return {
		"value": flt(value, 2),
		"fieldtype": "Currency",
		"route": ["List", "Sotuv"],
		"route_options": {"company": company, "docstatus": 0},
	}


@frappe.whitelist()
def oylik_tushum(filters=None):
	"""Shu oy mijozlardan olingan pul (Sotuv to'lovi, Kassa kirimi). Ichki firmadan kelgan pul kirmaydi."""
	_check("GL Entry")
	company = _company(filters)
	if not company:
		return _empty()
	today = nowdate()
	value = frappe.db.sql(
		"""select sum(gl.credit) - sum(gl.debit)
		from `tabGL Entry` gl join `tabCustomer` c on c.name = gl.party
		where gl.company = %s and gl.is_cancelled = 0 and gl.party_type = 'Customer'
			and gl.voucher_type = 'Payment Entry' and ifnull(c.is_internal_customer, 0) = 0
			and gl.posting_date between %s and %s""",
		(company, get_first_day(today), get_last_day(today)),
	)[0][0]
	return {
		"value": flt(value, 2),
		"fieldtype": "Currency",
		"route": ["query-report", "DDS"],
		"route_options": {"company": company},
	}


@frappe.whitelist()
def oylik_xarajat(filters=None):
	"""Shu oy xarajatlar (P&L dagi «Расходы»: ish haqi, yoqilg'i, ijara, xizmatlar). Sotilgan tovar tannarxi kirmaydi."""
	_check("GL Entry")
	company = _company(filters)
	if not company:
		return _empty()
	today = nowdate()
	value = frappe.db.sql(
		"""select sum(gl.debit) - sum(gl.credit)
		from `tabGL Entry` gl join `tabAccount` a on a.name = gl.account
		where gl.company = %s and gl.is_cancelled = 0 and a.root_type = 'Expense'
			and ifnull(a.account_type, '') not in ('Cost of Goods Sold', 'Stock Adjustment')
			and gl.voucher_type != 'Period Closing Voucher'
			and gl.posting_date between %s and %s""",
		(company, get_first_day(today), get_last_day(today)),
	)[0][0]
	return {
		"value": flt(value, 2),
		"fieldtype": "Currency",
		"route": ["query-report", "Foyda Zarar"],
		"route_options": {"company": company},
	}


# ------------------------------------------------------------------ ishlab chiqarish
# o'lchov birligi qisqa ko'rinishda: 176 111 t, 4 444 kg, 20 m³
QISQA_BIRLIK = {
	"tonne": "t",
	"tonna": "t",
	"тонна": "t",
	"kg": "kg",
	"кг": "kg",
	"kilogram": "kg",
	"куб": "m³",
	"cubic meter": "m³",
	"m3": "m³",
	"литр": "l",
	"litre": "l",
	"шт": "dona",
	"nos": "dona",
	"unit": "dona",
}


def _miqdor_text(rows) -> str:
	"""[(birlik, miqdor)] -> "176 111 t · 4 444 kg". Har xil birliklar qo'shilmaydi (tonna + kg = ma'nosiz)."""
	parts = []
	for uom, qty in rows:
		if not flt(qty):
			continue
		text = f"{flt(qty):,.3f}".rstrip("0").rstrip(".").replace(",", " ")
		parts.append(f"{text} {QISQA_BIRLIK.get((uom or '').lower(), uom or '')}".strip())
	return " · ".join(parts) or "0"


def _oylik_miqdor(doctype, sql, filters):
	"""Raqam emas, matn qaytariladi (birlik bilan): Number Card uni o'zgartirmasdan ko'rsatadi."""
	_check(doctype)
	company = _company(filters)
	if not company:
		return "0"
	today = nowdate()
	rows = frappe.db.sql(sql, (company, get_first_day(today), get_last_day(today)))
	return _miqdor_text(rows)


@frappe.whitelist()
def qazib_olingan(filters=None):
	"""Shu oy qazib olingan tovar miqdori birligi bilan (faqat shu bo'lim firmasi)."""
	return _oylik_miqdor(
		"Qazib Olish",
		"""select t.uom, sum(t.qty) from `tabQazib Olish` q join `tabQazib Olish Tovar` t on t.parent = q.name
		where q.company = %s and q.docstatus = 1 and q.posting_date between %s and %s
		group by t.uom order by sum(t.qty) desc""",
		filters,
	)


@frappe.whitelist()
def ishlab_chiqarilgan(filters=None):
	"""Shu oy ishlab chiqarilgan beton miqdori birligi bilan (faqat shu bo'lim firmasi)."""
	return _oylik_miqdor(
		"Beton Ishlab Chiqarish",
		"""select uom, sum(qty) from `tabBeton Ishlab Chiqarish`
		where company = %s and docstatus = 1 and posting_date between %s and %s
		group by uom order by sum(qty) desc""",
		filters,
	)


# ------------------------------------------------------------------ kassa va qarzlar
@frappe.whitelist()
def kassa_qoldigi(filters=None):
	"""Barcha kassa va bank hisoblaridagi pul (firma valyutasida)."""
	_check("GL Entry")
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
	_check("GL Entry")
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
