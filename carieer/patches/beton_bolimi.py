import frappe

from carieer.install import make_report_roles, make_standard_permissions
from carieer.permissions import ALL_ROLES

# Lavozim bo'yicha eski workspace'lar -> «Operator Karer», «Kassa Karer» ... va «Operator Beton», «Kassa Beton» ...
ESKI_WORKSPACELAR = ("Operator", "Kassir", "Omborchi", "Menejer")


def execute():
	"""Beton bo'limi: eski (firma nomisiz) workspace / sidebar / desktop ikonkalari o'chiriladi, Beton rollariga
	ERPNext hujjatlari va hisobotlari uchun ruxsatlar, beton zavodida sotuvda ishlab chiqarish yoqiladi."""
	for name in ESKI_WORKSPACELAR:
		for doctype in ("Desktop Icon", "Workspace Sidebar"):
			if (
				frappe.db.exists("DocType", doctype)
				and frappe.db.get_value(doctype, name, "app") == "carieer"
			):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		if frappe.db.get_value("Workspace", name, "module") == "Carieer":
			frappe.delete_doc("Workspace", name, ignore_permissions=True, force=True)

	make_standard_permissions(roles=ALL_ROLES)  # Karer rollari ham yangi ruxsatlarni oladi
	make_report_roles()

	for zavod in frappe.get_all("Zavod", filters={"name": ["like", "%beton%"]}, pluck="name"):
		frappe.db.set_value("Zavod", zavod, "ishlab_chiqarish", 1)

	frappe.cache.delete_value("desktop_icons")
	frappe.cache.delete_value("bootinfo")
