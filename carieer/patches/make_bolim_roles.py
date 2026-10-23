import frappe

from carieer.permissions import ALL_ROLES


def execute():
	"""Karer / Beton rollari (8 ta) workspace / hisobot JSON'lari sinxronlanishidan oldin bo'lishi kerak."""
	for role in ALL_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)
