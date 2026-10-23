"""Sotuv uchun yordamchilar: manfiy ombor qoldig'i, korrektirovka hisobi, USD kursi, beton ishlab chiqarish."""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import flt

ADJUSTMENT_ACCOUNT = "Корректировка расчётов"


@contextmanager
def allow_negative_stock():
	"""Jadvalda ombor qoldig'i tekshiruvi yo'q: sotuv doim o'tadi. ERPNext Stock Settings'dagi umumiy belgini
	faqat shu amal davomida yoqamiz (Sales Invoice tasdiqlanayotganda), so'ng avvalgi holatiga qaytaramiz."""
	settings = frappe.get_cached_doc("Stock Settings")
	old = settings.allow_negative_stock
	settings.allow_negative_stock = 1
	try:
		yield
	finally:
		settings.allow_negative_stock = old


def get_adjustment_account(company: str) -> str:
	"""Korrektirovka qarshi hisobi: balans hisobi (Liability), foyda-zarar (P&L) ga ta'sir qilmaydi."""
	name = frappe.db.get_value("Account", {"company": company, "account_name": ADJUSTMENT_ACCOUNT, "is_group": 0}, "name")
	if name:
		return name
	parent = frappe.db.get_value(
		"Account", {"company": company, "account_name": "Current Liabilities", "is_group": 1}, "name"
	) or frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "is_group": 1}, "name")
	if not parent:
		frappe.throw(_("{0} firmasida majburiyat (Liability) hisoblari guruhi topilmadi").format(company))
	acc = frappe.new_doc("Account")
	acc.update(
		{
			"account_name": ADJUSTMENT_ACCOUNT,
			"company": company,
			"parent_account": parent,
			"is_group": 0,
			"root_type": "Liability",
			"account_type": "",
		}
	)
	acc.flags.ignore_permissions = True
	acc.insert()
	return acc.name


def get_usd_rate(date, currency: str) -> float:
	"""Shu kungi USD -> so'm kursi; yo'q bo'lsa 0 (xato chiqarmaydi: «Сумма $» ixtiyoriy)."""
	from erpnext.setup.utils import get_exchange_rate

	try:
		return flt(get_exchange_rate("USD", currency, date))
	except Exception:
		frappe.clear_messages()
		return 0.0


# ------------------------------------------------------------------ Beton: retsept bo'yicha ishlab chiqarish
def get_production_bom(item_code: str, company: str) -> str | None:
	"""Firmadagi markaning faol standart retsepti (BOM)."""
	return frappe.db.get_value(
		"BOM",
		{"item": item_code, "company": company, "is_default": 1, "is_active": 1, "docstatus": 1},
		"name",
	)


def bom_raw_qty(bom: str, qty: float) -> dict:
	"""Retsept bo'yicha qty (ombor birligida) mahsulot uchun xomashyo: {tovar: miqdor ombor birligida}."""
	bom_qty = flt(frappe.db.get_value("BOM", bom, "quantity")) or 1
	out = {}
	for row in frappe.get_all("BOM Item", filters={"parent": bom}, fields=["item_code", "stock_qty"]):
		out[row.item_code] = out.get(row.item_code, 0) + flt(row.stock_qty) * flt(qty) / bom_qty
	return out


def make_manufacture_entry(doc, row, zavod) -> str:
	"""Sotuv qatori -> «Производство»: Stock Entry (Manufacture) retsept bo'yicha. Xomashyo xomashyo omboridan
	ayriladi, tayyor beton asosiy omborga kiradi. Tan narx = sarflangan xomashyo qiymati (Цена СС)."""
	se = frappe.new_doc("Stock Entry")
	se.update(
		{
			"purpose": "Manufacture",
			"stock_entry_type": "Manufacture",
			"company": doc.company,
			"posting_date": doc.posting_date,
			"posting_time": doc.posting_time,
			"set_posting_time": 1,
			"from_bom": 1,
			"bom_no": row.bom,
			"use_multi_level_bom": 0,
			"fg_completed_qty": row.stock_qty,
			"from_warehouse": zavod.xomashyo_ombori or zavod.asosiy_ombor,
			"to_warehouse": row.warehouse,
			"remarks": _("Sotuv {0}: {1} {2}").format(doc.name, row.item_code, flt(row.stock_qty)),
		}
	)
	se.get_items()
	for item in se.items:
		# jadvaldagidek: xomashyo qoldig'i / narxi yo'q bo'lsa ham ishlab chiqarish to'xtamaydi (tan narx 0)
		item.allow_zero_valuation_rate = 1
	se.flags.ignore_permissions = True
	se.insert()
	se.submit()
	return se.name
