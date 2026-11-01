# Posesheniye ("Посещение"): bir kun - bitta hujjat, har bir xodimning kelish / ketish vaqti.
# Часы работы jadvaldagidek: ketish - kelish; kechasi ishlaganda (ketish < kelish) + 24 soat.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, to_timedelta


class Posesheniye(Document):
	def validate(self):
		self.validate_duplicate()
		seen = set()
		for row in self.xodimlar:
			if row.employee in seen:
				frappe.throw(_("{0}-qator: {1} ikki marta yozilgan").format(row.idx, row.employee_name or row.employee))
			seen.add(row.employee)
			row.soat = ish_soati(row.kelish, row.ketish)
		self.jami_soat = flt(sum(flt(r.soat) for r in self.xodimlar), 2)

	def validate_duplicate(self):
		other = frappe.db.get_value(
			"Posesheniye",
			{"company": self.company, "sana": self.sana, "name": ["!=", self.name]},
			"name",
		)
		if other:
			frappe.throw(_("{0} sanasi uchun Посещение allaqachon bor: {1}").format(self.sana, other))


def ish_soati(kelish, ketish) -> float:
	if not kelish or not ketish:
		return 0
	secs = (to_timedelta(ketish) - to_timedelta(kelish)).total_seconds()
	if secs < 0:
		secs += 24 * 3600
	return flt(secs / 3600, 2)


@frappe.whitelist()
def get_active_employees(company: str) -> list[dict]:
	"""Firmaning faol xodimlari - «Xodimlarni qo'shish» tugmasi uchun."""
	frappe.has_permission("Posesheniye", "write", throw=True)
	return frappe.get_all(
		"Employee",
		filters={"company": company, "status": "Active"},
		fields=["name as employee", "employee_name", "department as bolim"],
		order_by="employee_name",
	)
