# Beton zavod xodimlariga "Karer" nomli sahifalar ko'rinmasligi uchun umumiy hujjat va hisobotlar neytral nomga o'tdi:
#   Karer Sotuv (+ Tovar / Xizmat / Tolov jadvallari) -> Sotuv
#   Karer Balans / Karer Cash Flow / Karer Foyda Zarar -> Balans / Pul Oqimi / Foyda Zarar
#   karer-xarita sahifasi -> texnika-xarita
# DocType'lar rename_doc bilan (jadval, Link maydonlari, parenttype yangilanadi). Hisobot va sahifa yozuvlari
# o'chiriladi - migrate ularni yangi nom bilan fayldan qayta yaratadi.

import frappe

DOCTYPES = [
	("Karer Sotuv Tovar", "Sotuv Tovar"),
	("Karer Sotuv Xizmat", "Sotuv Xizmat"),
	("Karer Sotuv Tolov", "Sotuv Tolov"),
	("Karer Sotuv", "Sotuv"),
]
REPORTS = ("Karer Balans", "Karer Cash Flow", "Karer Foyda Zarar")
PAGES = ("karer-xarita",)


def execute():
	for old, new in DOCTYPES:
		if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
			frappe.rename_doc("DocType", old, new, force=True)
	for name in REPORTS:
		delete_with_roles("Report", name)
	for name in PAGES:
		delete_with_roles("Page", name)


def delete_with_roles(doctype, name):
	if not frappe.db.exists(doctype, name):
		return
	frappe.db.delete("Has Role", {"parenttype": doctype, "parent": name})
	frappe.db.delete(doctype, {"name": name})
