import frappe


def execute():
	"""«Эко Карьер» bosh sahifasi «Eko Carier» ga, «Carieer» ilova ikonkasi «Carier» ga o'zgardi -
	eski (kirillcha) yozuvlar bazadan o'chiriladi, yangilari JSON fayllardan sinxronlanadi."""
	for doctype, name in (
		("Desktop Icon", "Эко Карьер"),
		("Desktop Icon", "Carieer"),
		("Workspace Sidebar", "Эко Карьер"),
		("Workspace", "Эко Карьер"),
	):
		if frappe.db.exists(doctype, name):
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)

	frappe.cache.delete_value("desktop_icons")
	frappe.cache.delete_value("bootinfo")
