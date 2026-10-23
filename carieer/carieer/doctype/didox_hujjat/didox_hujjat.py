import frappe
from frappe.model.document import Document


class DidoxHujjat(Document):
	def on_update(self):
		# Sotuv tasdiqlangan hujjat: holat fetch_from bilan yangilanmaydi, shu yerdan yoziladi
		if self.sotuv and self.has_value_changed("holat"):
			frappe.db.set_value("Sotuv", self.sotuv, "didox_holati", self.holat, update_modified=False)
