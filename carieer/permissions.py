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


def sync_user_companies(doc, method=None):
	"""hooks.py: User -> on_update. Karer / Beton rollari bo'yicha firma va zavod cheklovi (User Permission)
	o'zi qo'yiladi: Beton xodimi Karer kassasi, sotuvi, qarzlarini ko'rmaydi (va aksincha).
	Ikkala bo'lim roli bo'lsa - ikkala firma. Katta (ERPNext) rollari bor foydalanuvchiga tegilmaydi."""
	roles = {r.role for r in doc.roles}
	if doc.name in ("Administrator", "Guest") or roles & POWER_ROLES or not roles & set(ALL_ROLES):
		return
	from carieer.install import set_user_permissions
	from carieer.utils import find_zavod

	bolimlar = [b for b, rs in (("Karer", KARER_ROLES), ("Beton", BETON_ROLES)) if roles & set(rs)]
	zavodlar = [z for z in (find_zavod(b) for b in bolimlar) if z]
	companies = list(dict.fromkeys(c for c in (frappe.db.get_value("Zavod", z, "company") for z in zavodlar) if c))
	if not companies:
		return
	set_user_permissions(doc.name, "Company", companies)
	set_user_permissions(doc.name, "Zavod", zavodlar)


def sync_all_users():
	"""Mavjud xodimlar uchun bir marta: bench --site SITE execute carieer.permissions.sync_all_users"""
	for name in frappe.get_all("User", filters={"user_type": "System User", "enabled": 1}, pluck="name"):
		sync_user_companies(frappe.get_doc("User", name))
	frappe.db.commit()


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

	# bo'lim -> firma (public/js/carieer.js: Beton Zavod menyusidan ochilgan hisobot Eko Beton bilan ochiladi)
	from carieer.utils import company_for_bolim

	bootinfo.carieer_bolim = {
		KARER_SECTION.lower(): company_for_bolim("Karer"),
		BETON_SECTION.lower(): company_for_bolim("Beton"),
	}
	bootinfo.carieer_route_options, bootinfo.carieer_form_defaults = section_route_options()

	roles = set(frappe.get_roles())
	if roles & POWER_ROLES or not roles & set(ALL_ROLES):
		return

	keep = user_sections(roles)
	keep_keys = {s.lower() for s in keep} | {"my workspaces"}
	bootinfo.workspace_sidebar_item = {k: v for k, v in sidebars.items() if k in keep_keys}
	bootinfo.desktop_icons = [i for i in (bootinfo.get("desktop_icons") or []) if i.get("label") in keep]


def section_route_options() -> tuple[dict, dict]:
	"""Bo'lim (Karer / Beton Zavod) ichida ochilgan hujjat shu bo'lim firmasida bo'lsin (public/js/carieer.js).
	Aks holda ikkala firmaga ruxsati bor foydalanuvchida (Administrator, menejer) standart firma - masalan Eko Karer -
	qo'yiladi: Beton Zavod -> Qabul -> tovar Karer omboriga tushib qoladi.
	Qaytaradi:
	  ro'yxat filtri / yangi forma qiymatlari: {"Purchase Receipt": {"beton zavod": {"company": "Eko Beton"}},
	                                            "Sotuv": {"karer": {"tip": "Karer", "company": "Eko Karer"}}}
	  faqat yangi forma uchun (ro'yxat filtri emas): {"Purchase Receipt": {"beton zavod": {"set_warehouse": ...}}}"""
	from carieer.utils import find_zavod

	options_out, defaults_out = {}, {}
	for section, bolim in ((KARER_SECTION, "Karer"), (BETON_SECTION, "Beton")):
		zavod = find_zavod(bolim)
		z = zavod and frappe.db.get_value(
			"Zavod", zavod, ["company", "xomashyo_ombori", "asosiy_ombor"], as_dict=True
		)
		if not z or not z.company:
			continue
		doctypes = frappe.get_all(
			"Workspace Sidebar Item", filters={"parent": section, "link_type": "DocType"}, pluck="link_to"
		)
		for doctype in set(doctypes):
			if not frappe.db.exists("DocType", doctype):
				continue
			meta = frappe.get_meta(doctype)
			options = {}
			for df in meta.get("fields", {"fieldtype": "Link"}):
				if df.options == "Company" and df.fieldname == "company":
					options["company"] = z.company
				elif df.options == "Zavod":
					options[df.fieldname] = zavod
			if options:
				options_out.setdefault(doctype, {})[section.lower()] = options
			# xarid: tovar shu bo'lim omboriga (Beton - xomashyo ombori)
			warehouse = z.xomashyo_ombori or z.asosiy_ombor
			if warehouse and doctype in ("Purchase Receipt", "Purchase Invoice") and meta.has_field("set_warehouse"):
				defaults_out.setdefault(doctype, {})[section.lower()] = {"set_warehouse": warehouse}
	return options_out, defaults_out
