# Ishchi Oyligi ("Ишчи ойлиги"): xodim okladi (oyiga) yoki soatbay stavkasi (Сдельный), shu sanadan boshlab.
# Расчёт ЗП har oy uchun oy oxirigacha bo'lgan eng oxirgi yozuvni oladi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class IshchiOyligi(Document):
	def validate(self):
		if flt(self.oklad) < 0 or flt(self.sdelniy) < 0:
			frappe.throw(_("Oklad va stavka manfiy bo'lmaydi"))
		if not flt(self.oklad) and not flt(self.sdelniy):
			frappe.throw(_("Оклад yoki Сдельный stavkadan birini kiriting"))
