import frappe


def execute():
	"""«Karer Omborchi» roli workspace / hisobot JSON'lari sinxronlanishidan oldin bo'lishi kerak."""
	if not frappe.db.exists("Role", "Karer Omborchi"):
		frappe.get_doc({"doctype": "Role", "role_name": "Karer Omborchi", "desk_access": 1}).insert(
			ignore_permissions=True
		)
