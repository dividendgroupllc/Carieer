"""ERPNext hujjatlari uchun kichik server hodisalari (hooks.py -> doc_events)."""

import frappe
from frappe.utils import flt


def stock_reconciliation_before_validate(doc, method=None):
	"""Инвентаризация: karerda qazib olingan tovar tan narxi 0. Karer zavodining asosiy omboridagi qatorda narx
	ko'rsatilmasa «Allow Zero Valuation Rate» o'zi belgilanadi (aks holda ERPNext narx talab qiladi)."""
	karer_omborlari = set(frappe.get_all("Zavod", filters={"zavod": "Karer"}, pluck="asosiy_ombor"))
	for row in doc.items:
		if row.warehouse in karer_omborlari and not flt(row.valuation_rate):
			row.allow_zero_valuation_rate = 1
