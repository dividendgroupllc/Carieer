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
	"""Tasdiqlangan sotuvlar summasi firma valyutasida (base_amount). Firmalararo sotuv - xaridor qabul qilgandan keyin."""
	return flt(
		frappe.db.sql(
			"""select sum(base_amount) from `tabSotuv`
			where company = %s and docstatus = 1 and posting_date between %s and %s
				and ifnull(qabul_holati, '') != 'Kutilmoqda'""",
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
	"""Hali sotuv bo'lmagan hujjatlar: saqlangan, lekin tasdiqlanmagan (Draft) va ikkinchi firmamiz qabul qilishini
	kutayotgan firmalararo sotuvlar. Ular sotuv, qarz va ombor hisobiga KIRMAYDI."""
	_check("Sotuv")
	company = _company(filters)
	if not company:
		return _empty()
	value = frappe.db.sql(
		"""select sum(base_amount) from `tabSotuv` where company = %s
		and (docstatus = 0 or (docstatus = 1 and qabul_holati = 'Kutilmoqda'))""",
		company,
	)[0][0]
	return {
		"value": flt(value, 2),
		"fieldtype": "Currency",
		"route": ["List", "Sotuv"],
		"route_options": {"company": company, "status": ["in", ["Draft", "Tasdiq kutilmoqda"]]},
	}


@frappe.whitelist()
def kutilayotgan_xarid(filters=None):
	"""Ikkinchi firmamiz bizga yuborgan, biz hali qabul qilmagan tovar (qabul qilish / rad etish kerak)."""
	_check("Sotuv")
	company = _company(filters)
	if not company:
		return _empty()
	value = frappe.db.sql(
		"""select sum(base_amount) from `tabSotuv`
		where ichki_firma = %s and docstatus = 1 and qabul_holati = 'Kutilmoqda'""",
		company,
	)[0][0]
	return {
		"value": flt(value, 2),
		"fieldtype": "Currency",
		"route": ["List", "Sotuv"],
		"route_options": {"ichki_firma": company, "qabul_holati": "Kutilmoqda"},
	}


@frappe.whitelist()
def qarzlarimiz(filters=None):
	"""Bizning qarzimiz: ta'minotchilarga (o'zimizning ikkinchi firmamiz ham), xodimlarga va kassa qarzi
	(minusga kirgan kassalar). Bosilsa - «Qarzlarimiz»: kimga, nima uchun, qachondan."""
	_check("GL Entry")
	company = _company(filters)
	if not company:
		return _empty()
	from carieer.utils import kassa_qarzlari

	kassa = sum(k.qarz for k in kassa_qarzlari(company))
	value = kassa + flt(frappe.db.sql(
		"""select sum(t.qoldiq) from (
			select sum(gl.credit) - sum(gl.debit) as qoldiq
			from `tabGL Entry` gl
			where gl.company = %s and gl.is_cancelled = 0 and gl.party_type in ('Supplier', 'Employee')
			group by gl.party_type, gl.party having sum(gl.credit) - sum(gl.debit) > 0
		) t""",
		company,
	)[0][0])
	return {
		"value": flt(value, 2),
		"fieldtype": "Currency",
		"route": ["query-report", "Qarzlarimiz"],
		"route_options": {"company": company},
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
	return _text_card(_miqdor_text(rows), ["List", doctype], {"company": company, "docstatus": 1})


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
	if flt(value) < -0.005:
		# kassa minusda: pul o'rniga kassa qarzi ko'rsatiladi (Number Card matnni o'zgartirmasdan chiqaradi)
		currency = frappe.get_cached_value("Company", company, "default_currency")
		return _text_card(
			_("Kassa qarzi: {0}").format(frappe.utils.fmt_money(-flt(value), 0, currency)),
			["query-report", "Kassa Daftari"],
			{"company": company},
		)
	return {
		"value": flt(value, 2),
		"fieldtype": "Currency",
		"route": ["query-report", "DDS"],
		"route_options": {"company": company},
	}


def _text_card(text: str, route=None, route_options=None) -> dict:
	"""Matnli kartochka (raqam emas), bosilganda hisobot ochiladi. Number Card qiymatni HTML sifatida chiqaradi."""
	out = {"value": f"<span>{frappe.utils.escape_html(text)}</span>", "fieldtype": "Data"}
	if route:
		out.update({"route": route, "route_options": route_options or {}})
	return out


@frappe.whitelist()
def firmalararo_qarz(filters=None):
	"""Ikkinchi firmamiz bilan hisob: kim kimga qancha qarzdor (bosilsa - «Firmalararo qarzlar» hisoboti)."""
	_check("GL Entry")
	company = _company(filters)
	if not company:
		return _empty()
	from carieer.carieer.report.firmalararo_qarzlar.firmalararo_qarzlar import balance, other_companies

	currency = frappe.get_cached_value("Company", company, "default_currency")
	today = nowdate()
	parts = []
	for other in other_companies(company):
		bal = flt(balance(company, other, today), 2)
		if bal > 0.005:
			line = _("{0} bizga qarz: {1}").format(other, frappe.utils.fmt_money(bal, 0, currency))
		elif bal < -0.005:
			line = _("{0}ga qarzimiz: {1}").format(other, frappe.utils.fmt_money(-bal, 0, currency))
		else:
			line = _("{0} bilan qarz yo'q").format(other)
		if abs(bal + flt(balance(other, company, today))) >= 0.01:
			line += " ⚠"  # ikki firma hisobi farq qiladi - batafsil hisobotda
		parts.append(line)
	return _text_card(
		" · ".join(parts) or _("Ichki firma yo'q"), ["query-report", "Firmalararo Qarzlar"], {"company": company}
	)


@frappe.whitelist()
def mijozlar_qarzi(filters=None):
	"""Bizga qarzdorlar: mijozlar va o'zimizning ikkinchi firmamiz (faqat musbat qoldiqlar).
	Bosilsa - «Qarzdorlik» hisoboti: kim, qancha, nima olgan, qachondan beri."""
	_check("GL Entry")
	company = _company(filters)
	if not company:
		return _empty()
	value = frappe.db.sql(
		"""select sum(t.qoldiq) from (
			select sum(gl.debit) - sum(gl.credit) as qoldiq
			from `tabGL Entry` gl
			where gl.company = %s and gl.is_cancelled = 0 and gl.party_type = 'Customer'
			group by gl.party having sum(gl.debit) - sum(gl.credit) > 0
		) t""",
		company,
	)[0][0]
	return {
		"value": flt(value, 2),
		"fieldtype": "Currency",
		"route": ["query-report", "Qarzdorlik"],
		"route_options": {"company": company, "turi": "Mijozlar", "ichki_firma": 1},
	}