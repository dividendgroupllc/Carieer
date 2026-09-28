import frappe
from frappe import _
from frappe.model.document import Document


class KarerSozlamalari(Document):
	def validate(self):
		seen = set()
		for row in self.firmalar:
			if row.company in seen:
				frappe.throw(_("{0} firmasi jadvalda ikki marta kiritilgan").format(row.company))
			seen.add(row.company)
			for field in ("sotuv_ombori", "qazish_ombori", "beton_xomashyo_ombori", "beton_ombori", "yoqilgi_ombori"):
				wh = row.get(field)
				if wh and frappe.db.get_value("Warehouse", wh, "company") != row.company:
					frappe.throw(_("{0}-qator: {1} ombori {2} firmasiga tegishli emas").format(row.idx, wh, row.company))

	def on_update(self):
		frappe.cache.delete_value("karer_eskiz_token")
