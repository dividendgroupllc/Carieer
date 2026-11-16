import frappe
from frappe.model.document import Document


class DidoxHujjat(Document):
	def on_update(self):
		# Sotuv tasdiqlangan hujjat: holat fetch_from bilan yangilanmaydi, shu yerdan yoziladi.
		# Sotuvga TTN ham bog'lanadi - holat faqat Sotuv'ning o'z fakturasidan yoziladi.
		if (
			self.sotuv
			and self.has_value_changed("holat")
			and frappe.db.get_value("Sotuv", self.sotuv, "didox_hujjat") == self.name
		):
			frappe.db.set_value("Sotuv", self.sotuv, "didox_holati", self.holat, update_modified=False)
