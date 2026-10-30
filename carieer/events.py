"""ERPNext hujjatlari uchun kichik server hodisalari (hooks.py -> doc_events)."""

import frappe
from frappe.utils import flt


def stock_reconciliation_before_validate(doc, method=None):
	"""Инвентаризация: karerda qazib olingan tovar tan narxi 0. Karer zavodining asosiy omboridagi qatorda narx
	ko'rsatilmasa «Allow Zero Valuation Rate» o'zi belgilanadi (aks holda ERPNext narx talab qiladi)."""
	from carieer.utils import find_zavod

	zavod = find_zavod("Karer")  # Zavod boshqacha nomlangan bo'lsa ham topiladi
	karer_omborlari = {frappe.db.get_value("Zavod", zavod, "asosiy_ombor")} if zavod else set()
	for row in doc.items:
		if row.warehouse in karer_omborlari and not flt(row.valuation_rate):
			row.allow_zero_valuation_rate = 1


def customer_validate(doc, method=None):
	"""INN / JShShIR: faqat raqam, 9 (korxona) yoki 14 (jismoniy shaxs / yakka tadbirkor) xona."""
	from frappe import _

	inn = (doc.tax_id or "").replace(" ", "")
	if inn and (not inn.isdigit() or len(inn) not in (9, 14)):
		frappe.throw(
			_(
				"INN 9 raqamdan (korxona) yoki JShShIR 14 raqamdan (yakka tadbirkor) iborat bo'ladi: {0}"
			).format(doc.tax_id),
			title=_("INN noto'g'ri"),
		)
	doc.tax_id = inn or None
