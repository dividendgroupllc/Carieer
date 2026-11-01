# Ish Kunlari ("Рабочие дни"): oydagi ish kunlari va ish soatlari. Bo'sh qoldirilsa - dushanba-shanba kunlari
# va har kuni 8 soat. Расчёт ЗП: oklad / ish soatlari × ishlagan soat.

import calendar

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_first_day, get_last_day, getdate

SOAT_KUNIGA = 8


class IshKunlari(Document):
	def validate(self):
		self.oy_boshi = get_first_day(self.oy_boshi)
		self.oy_oxiri = get_last_day(self.oy_boshi)
		if not cint(self.ish_kunlari):
			self.ish_kunlari = ish_kunlari_soni(self.oy_boshi)
		if not flt(self.ish_soatlari):
			self.ish_soatlari = cint(self.ish_kunlari) * SOAT_KUNIGA
		other = frappe.db.get_value(
			"Ish Kunlari",
			{"company": self.company, "oy_boshi": self.oy_boshi, "name": ["!=", self.name]},
			"name",
		)
		if other:
			frappe.throw(_("Bu oy uchun Рабочие дни allaqachon kiritilgan: {0}").format(other))


def ish_kunlari_soni(oy_boshi) -> int:
	"""Oydagi dushanba-shanba kunlari soni (yakshanba - dam olish)."""
	d = getdate(oy_boshi)
	_first, days = calendar.monthrange(d.year, d.month)
	return sum(1 for day in range(1, days + 1) if calendar.weekday(d.year, d.month, day) != 6)
