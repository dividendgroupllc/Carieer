"""Sotuv uchun yordamchilar: manfiy ombor qoldig'i, korrektirovka hisobi, USD kursi."""

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
