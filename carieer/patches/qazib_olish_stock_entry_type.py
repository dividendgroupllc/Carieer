import frappe

from carieer.carieer.doctype.qazib_olish.qazib_olish import QAZIB_TURI


def execute():
	"""Qazib olish yaratadigan ombor kirimi uchun o'z turi (purpose = Material Receipt): Stock Entry
	ro'yxatida va ombor hisobotlarida «Qazib olish» deb ajraladi. Mavjud qazib olish kirimlari ham."""
	if not frappe.db.exists("Stock Entry Type", QAZIB_TURI):
		frappe.get_doc(
			{"doctype": "Stock Entry Type", "name": QAZIB_TURI, "purpose": "Material Receipt"}
		).insert(ignore_permissions=True)
	for se in frappe.get_all("Qazib Olish", filters={"stock_entry": ["is", "set"]}, pluck="stock_entry"):
		frappe.db.set_value("Stock Entry", se, "stock_entry_type", QAZIB_TURI, update_modified=False)
