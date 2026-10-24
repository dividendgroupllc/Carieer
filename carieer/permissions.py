"""Rollar (Karer / Beton: Operator, Kassir, Omborchi, Menejer), firma bo'yicha ruxsat va menyu (desktop / sidebar) tozaligi.

Ma'lumot cheklovi ERPNext'ning o'z mexanizmi bilan: User Permission -> Company.
Menyu: Karer / Beton xodimi faqat Carieer bo'limlarini (o'z workspace'larini) ko'radi.
"""

import frappe
from frappe import _

# Bo'lim = firma (Zavod): rol nomi «<Bo'lim> <Lavozim>», masalan «Beton Kassir»
BOLIMLAR = ("Karer", "Beton")
LAVOZIMLAR = ("Operator", "Kassir", "Omborchi", "Menejer")

KARER_ROLES = tuple(f"Karer {lavozim}" for lavozim in LAVOZIMLAR)
BETON_ROLES = tuple(f"Beton {lavozim}" for lavozim in LAVOZIMLAR)
ALL_ROLES = KARER_ROLES + BETON_ROLES


def lavozim_roles(lavozim: str) -> tuple[str, ...]:
	"""Lavozim -> ikkala bo'limdagi rollari: «Kassir» -> («Karer Kassir», «Beton Kassir»)."""
	return tuple(f"{bolim} {lavozim}" for bolim in BOLIMLAR)


OPERATOR_ROLES = lavozim_roles("Operator")
KASSIR_ROLES = lavozim_roles("Kassir")
OMBORCHI_ROLES = lavozim_roles("Omborchi")
MENEJER_ROLES = lavozim_roles("Menejer")

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


def has_app_permission() -> bool:
	"""hooks.py: add_to_apps_screen. "Carier" ilovasi -> desktop (har bir lavozim o'z workspace'ini ko'radi:
	Operator Karer, Kassa Karer ... / Operator Beton, Kassa Beton ...)."""
	return bool(set(frappe.get_roles()) & (set(ALL_ROLES) | {"System Manager"}))


def hide_foreign_icons(bootinfo):
	"""hooks.py: extend_bootinfo. Karer / Beton xodimi (ERPNext'ning boshqa rollari bo'lmasa) desktop'da faqat Carieer
	ikonkalarini ko'radi (jadvaldagi varaqlar). ERPNext'ning Accounting, Stock, Selling ... papkalari ularga
	ko'rinmaydi. System Manager hammasini ko'radi."""
	roles = set(frappe.get_roles())
	if roles & POWER_ROLES or not roles & set(ALL_ROLES):
		return
	icons = bootinfo.get("desktop_icons")
	if icons:
		bootinfo.desktop_icons = [i for i in icons if i.get("app") == "carieer"]


def boot_firma(bootinfo):
	"""hooks.py: extend_bootinfo. Ro'yxat / hisobotlarda firma filtri (public/js/carieer.bundle.js): bo'lim -> firma
	(faqat xodimga ruxsat berilganlari) va standart firma. Karer / Beton rollari bo'lmasa - filtr qo'yilmaydi."""
	from carieer.utils import company_for_bolim

	if not set(frappe.get_roles()) & set(ALL_ROLES):
		return
	allowed = get_allowed_companies()
	bolimlar = {}
	for bolim in BOLIMLAR:
		company = company_for_bolim(bolim)
		if company and (not allowed or company in allowed):
			bolimlar[bolim] = company
	default = frappe.defaults.get_user_default("Company")
	if allowed and default not in allowed:
		default = allowed[0]
	bootinfo.carieer_firma = {"bolimlar": bolimlar, "default": default}
