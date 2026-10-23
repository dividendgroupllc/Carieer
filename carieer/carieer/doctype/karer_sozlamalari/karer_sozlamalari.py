import frappe
from frappe.model.document import Document


class KarerSozlamalari(Document):
	def on_update(self):
		frappe.cache.delete_value("karer_eskiz_token")
