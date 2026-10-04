# Zavod: ikki zavod (Karer, Beton) -> firma, omborlar, standart kassa.
# Sotuv'dagi «Тип» shu yerdan tanlanadi va firma o'zi qo'yiladi. Xodimga User Permission (Zavod) berilsa,
# Sotuv formasida Тип avtomatik uning zavodi bo'ladi.

import frappe
from frappe import _
from frappe.model.document import Document

from carieer.utils import validate_warehouse_company


class Zavod(Document):
	def validate(self):
		for field in ("asosiy_ombor", "xomashyo_ombori", "yoqilgi_ombori"):
			validate_warehouse_company(self.get(field), self.company, self.meta.get_label(field))
		if self.kassa and not frappe.db.exists(
			"Mode of Payment Account", {"parent": self.kassa, "company": self.company}
		):
			frappe.throw(
				_("{0} kassasida {1} firmasi uchun hisob ko'rsatilmagan").format(self.kassa, self.company)
			)
