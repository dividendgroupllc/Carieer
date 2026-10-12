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

# Bosh sahifa (dashboard) workspace nomlari: har bir zavodning o'zi. Funksional bo'limlar (Kassa, Sotuv, Ta'minot, Ombor,
# Ishlab chiqarish, Texnika, Hisobotlar) alohida modul / ikonka (desktop_icon/*.json, <modul>/sidebar, <modul>/workspace).
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


def set_module_profile(doc, method=None):
	"""hooks.py: User -> validate. Karer / Beton rollari bo'yicha modul profili: Beton xodimiga Karer paneli (va ERPNext'ning
	Selling, Stock ... bo'limlari) ko'rinmaydi, Karer xodimiga - Beton paneli. Katta (ERPNext) rollari bor foydalanuvchiga tegilmaydi."""
	roles = {r.role for r in doc.roles}
	if doc.name in ("Administrator", "Guest") or roles & POWER_ROLES or not roles & set(ALL_ROLES):
		return
	karer, beton = bool(roles & set(KARER_ROLES)), bool(roles & set(BETON_ROLES))
	profile = "Karer va Beton xodim" if karer and beton else "Karer xodim" if karer else "Beton xodim"
	if not frappe.db.exists("Module Profile", profile):
		return
	doc.module_profile = profile
	doc.set("block_modules", [{"module": d.module} for d in frappe.get_doc("Module Profile", profile).block_modules])


def sync_all_users():
	"""Mavjud xodimlar uchun bir marta: bench --site SITE execute carieer.permissions.sync_all_users"""
	for name in frappe.get_all("User", filters={"user_type": "System User", "enabled": 1}, pluck="name"):
		user = frappe.get_doc("User", name)
		if {r.role for r in user.roles} & set(ALL_ROLES):
			user.save(ignore_permissions=True)  # validate: modul profili, on_update: firma ruxsati
		else:
			sync_user_companies(user)
	frappe.db.commit()


def get_allowed_zavodlar(user: str | None = None) -> list[str]:
	"""Xodim bog'langan zavodlar (User Permission -> Zavod). Bo'sh ro'yxat = cheklov yo'q."""
	from frappe.core.doctype.user_permission.user_permission import get_permitted_documents

	if user and user != frappe.session.user:
		return [
			d.for_value
			for d in frappe.get_all("User Permission", filters={"user": user, "allow": "Zavod"}, fields=["for_value"])
		]
	return get_permitted_documents("Zavod")


def boot_session(bootinfo):
	"""Xodim bitta zavodga bog'langan bo'lsa - yangi hujjatlarda firma / zavod / xarid ombori o'zi qo'yiladi
	(public/js/carieer.js). Menyu esa Desktop Icon / Sidebar rollari bilan boshqariladi (hooks: extend_bootinfo)."""
	bootinfo.carieer_form_defaults = user_form_defaults()


def hide_foreign_icons(bootinfo):
	"""hooks.py: extend_bootinfo. Karer / Beton xodimi (ERPNext'ning boshqa rollari bo'lmasa) desktop'da faqat Carieer
	ikonkalarini ko'radi: Karer yoki Beton Zavod, Kassa, Sotuv, Ta'minot, Ombor, Ishlab chiqarish, Texnika, Hisobotlar.
	ERPNext'ning Accounting, Stock, Selling ... papkalari ularga ko'rinmaydi. System Manager hammasini ko'radi."""
	roles = set(frappe.get_roles())
	if roles & POWER_ROLES or not roles & set(ALL_ROLES):
		return
	icons = bootinfo.get("desktop_icons")
	if icons:
		bootinfo.desktop_icons = [i for i in icons if i.get("app") == "carieer"]


def user_form_defaults() -> dict:
	"""{"Purchase Receipt": {"company": "Eko Beton", "set_warehouse": "..."}, "Sotuv": {"tip": "Beton", ...}}
	Faqat bitta zavodga bog'langan xodim uchun (ikkala zavodga ruxsati bor xodim / Administrator - o'zi tanlaydi)."""
	from carieer.utils import find_zavod  # noqa: F401

	zavodlar = get_allowed_zavodlar()
	if len(zavodlar) != 1:
		return {}
	zavod = zavodlar[0]
	z = frappe.db.get_value("Zavod", zavod, ["company", "xomashyo_ombori", "asosiy_ombor"], as_dict=True)
	if not z or not z.company:
		return {}
	out = {}
	for doctype in frappe.get_all("DocType", filters={"module": "Carieer", "istable": 0, "issingle": 0}, pluck="name"):
		options = {}
		for df in frappe.get_meta(doctype).get("fields", {"fieldtype": "Link"}):
			if df.options == "Company" and df.fieldname == "company":
				options["company"] = z.company
			elif df.options == "Zavod":
				options[df.fieldname] = zavod
		if options:
			out[doctype] = options
	# xarid: tovar o'z zavodi omboriga (Beton - xomashyo ombori)
	warehouse = z.xomashyo_ombori or z.asosiy_ombor
	for doctype in ("Purchase Receipt", "Purchase Invoice"):
		out[doctype] = {"company": z.company, **({"set_warehouse": warehouse} if warehouse else {})}
	return out
