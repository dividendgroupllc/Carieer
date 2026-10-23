import frappe
from frappe import _
from frappe.model.document import Document

from carieer.didox.client import token_key


class DidoxSozlamalari(Document):
	def validate(self):
		companies = set()
		for row in self.firmalar:
			row.inn = (row.inn or "").strip()
			if not row.inn.isdigit() or len(row.inn) not in (9, 14):
				frappe.throw(
					_("Qator {0}: INN 9 yoki 14 raqamdan iborat bo'ladi").format(row.idx), title=_("Didox")
				)
			if row.company in companies:
				frappe.throw(_("{0} firmasi ikki marta kiritilgan").format(row.company), title=_("Didox"))
			companies.add(row.company)

	def on_update(self):
		# rejim, token yoki parol o'zgargan bo'lishi mumkin: eski firma tokenlari tashlanadi
		for row in self.firmalar:
			frappe.cache.delete_value(token_key(row.company))
