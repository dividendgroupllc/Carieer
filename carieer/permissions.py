"""Rollar (Karer Operator / Kassir / Menejer), firma bo'yicha ruxsat va menyu (desktop / sidebar) tozaligi.

Ma'lumot cheklovi ERPNext'ning o'z mexanizmi bilan: User Permission -> Company.
Menyu: Karer xodimi faqat Carieer bo'limlarini ko'radi.
"""

import frappe
from frappe import _

KARER_ROLES = ("Karer Operator", "Karer Kassir", "Karer Menejer")
ALL_ROLES = KARER_ROLES

OPERATOR_ROLES = ("Karer Operator",)
KASSIR_ROLES = ("Karer Kassir",)
MENEJER_ROLES = ("Karer Menejer",)

# Bu rollardan biri bo'lsa foydalanuvchi ERPNext'ning boshqa bo'limlarini ham ko'radi (menyu qisqartirilmaydi)
POWER_ROLES = {
	"System Manager",
	"Administrator",
	"Accounts Manager",
	"Accounts User",
	"Stock Manager",
	"Sales Manager",
	"Purchase Manager",
	"Manufacturing Manager",
	"HR Manager",
}


def get_allowed_companies(user: str | None = None) -> list[str]:
	"""Xodim ko'ra oladigan firmalar (User Permission -> Company). Bo'sh ro'yxat = cheklov yo'q."""
	from frappe.core.doctype.user_permission.user_permission import get_permitted_documents

	if user and user != frappe.session.user:
		return [
			d.for_value
			for d in frappe.get_all(
				"User Permission", filters={"user": user, "allow": "Company"}, fields=["for_value"]
			)
		]
	return get_permitted_documents("Company")


def check_company(company: str | None, throw: bool = True) -> bool:
	allowed = get_allowed_companies()
	if not allowed or not company or company in allowed:
		return True
	if throw:
		frappe.throw(
			_("{0} firmasi ma'lumotlarini ko'rishga ruxsatingiz yo'q").format(company), frappe.PermissionError
		)
	return False


def check_report_company(filters: frappe._dict):
	"""SQL bilan yozilgan hisobotlarda ruxsat avtomatik qo'llanmaydi: firma bo'sh bo'lsa - o'z firmasi
	(yoki standart firma) qo'yiladi, boshqa firma tanlansa - xato."""
	allowed = get_allowed_companies()
	if not filters.get("company"):
		filters.company = (
			(allowed[0] if allowed else None)
			or frappe.defaults.get_user_default("Company")
			or frappe.db.get_single_value("Global Defaults", "default_company")
			or frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		)
	if not filters.company:
		frappe.throw(_("Firma topilmadi. Avval Company yarating"))
	check_company(filters.company)


def hide_foreign_icons(bootinfo):
	"""hooks.py: extend_bootinfo. Karer xodimi (ERPNext'ning boshqa rollari bo'lmasa) desktop'da faqat Carieer
	ikonkalarini ko'radi (jadvaldagi varaqlar). ERPNext'ning Accounting, Stock, Selling ... papkalari ularga
	ko'rinmaydi. System Manager hammasini ko'radi."""
	roles = set(frappe.get_roles())
	if roles & POWER_ROLES or not roles & set(ALL_ROLES):
		return
	icons = bootinfo.get("desktop_icons")
	if icons:
		bootinfo.desktop_icons = [i for i in icons if i.get("app") == "carieer"]
