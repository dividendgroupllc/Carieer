import frappe

from carieer.carieer.doctype.qazib_olish.qazib_olish import items_title


def execute():
	"""Qazib Olish qayta yozildi: eski yozuvlarda sarlavha (ro'yxatdagi «Шебень 120 Куб, ...») bo'sh."""
	for name in frappe.get_all("Qazib Olish", filters={"title": ["is", "not set"]}, pluck="name"):
		rows = frappe.get_all(
			"Qazib Olish Tovar",
			filters={"parent": name},
			fields=["item_code", "item_name", "qty", "uom"],
			order_by="idx",
		)
		frappe.db.set_value("Qazib Olish", name, "title", items_title(rows), update_modified=False)
