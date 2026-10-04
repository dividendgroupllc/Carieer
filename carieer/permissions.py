"""Rollar, firma bo'yicha ruxsat va menyu (desktop / sidebar) tozaligi.

Rollar ikki o'q bo'yicha: zavod (Karer / Beton) x lavozim (Operator / Kassir / Menejer).
Ma'lumot ajratilishi ERPNext'ning o'z mexanizmi bilan: User Permission -> Company (har kim faqat o'z firmasini
ko'radi). Menyu: Karer xodimi faqat "Karer", beton xodimi faqat "Beton Zavod" bo'limini ko'radi.
"""

import frappe
from frappe import _

KARER_ROLES = ("Karer Operator", "Karer Kassir", "Karer Menejer")
BETON_ROLES = ("Beton Operator", "Beton Kassir", "Beton Menejer")
ALL_ROLES = KARER_ROLES + BETON_ROLES

OPERATOR_ROLES = ("Karer Operator", "Beton Operator")
KASSIR_ROLES = ("Karer Kassir", "Beton Kassir")
MENEJER_ROLES = ("Karer Menejer", "Beton Menejer")

# Bo'lim (Workspace / Workspace Sidebar / Desktop Icon) nomlari
KARER_SECTION = "Karer"
BETON_SECTION = "Beton Zavod"

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


def user_sections(roles=None) -> set[str]:
	roles = set(roles if roles is not None else frappe.get_roles())
	sections = set()
	if roles & set(KARER_ROLES):
		sections.add(KARER_SECTION)
	if roles & set(BETON_ROLES):
		sections.add(BETON_SECTION)
	return sections


def boot_session(bootinfo):
	"""Menyuni tozalash (JS siz, server tomonda):
	- Frappe avtomatik yaratadigan "Carieer" modul sidebar'i hech kimga kerak emas (bo'limlar: Karer, Beton Zavod).
	- Karer / Beton xodimi (ERPNext'ning boshqa rollari bo'lmasa) desktop'da faqat o'z bo'limini ko'radi."""
	sidebars = bootinfo.get("workspace_sidebar_item") or {}
	sidebars.pop("carieer", None)

	roles = set(frappe.get_roles())
	if roles & POWER_ROLES or not roles & set(ALL_ROLES):
		return

	keep = user_sections(roles)
	keep_keys = {s.lower() for s in keep} | {"my workspaces"}
	bootinfo.workspace_sidebar_item = {k: v for k, v in sidebars.items() if k in keep_keys}
	bootinfo.desktop_icons = [i for i in (bootinfo.get("desktop_icons") or []) if i.get("label") in keep]
