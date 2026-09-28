# Texnika Xarajatlari: har bir mashina/texnika bo'yicha yoqilg'i va moy sarfi, summa, yurgan km, o'rtacha sarf.

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	cond = ["y.docstatus = 1", "y.posting_date between %(from_date)s and %(to_date)s"]
	if filters.get("company"):
		cond.append("y.company = %(company)s")
	if filters.get("vehicle"):
		cond.append("y.vehicle = %(vehicle)s")
	rows = frappe.db.sql(
		f"""select y.vehicle, v.texnika_turi, v.model, y.turi, sum(y.qty) qty, sum(y.amount) amount,
			sum(y.yurgan_km) km, max(y.moto_soat) - min(nullif(y.moto_soat, 0)) moto
		from `tabYoqilgi Hisobi` y left join `tabVehicle` v on v.name = y.vehicle
		where {" and ".join(cond)}
		group by y.vehicle, v.texnika_turi, v.model, y.turi
		order by y.vehicle, y.turi""",
		filters,
		as_dict=True,
	)
	for r in rows:
		r.sarf_100 = flt(flt(r.qty) * 100 / r.km, 2) if flt(r.km) and r.turi in ("Dizel", "Benzin", "Gaz (metan/propan)") else None
		r.sarf_soat = flt(flt(r.qty) / r.moto, 2) if flt(r.moto) else None
	columns = [
		{"fieldname": "vehicle", "label": _("Texnika"), "fieldtype": "Link", "options": "Vehicle", "width": 130},
		{"fieldname": "texnika_turi", "label": _("Turi"), "fieldtype": "Data", "width": 140},
		{"fieldname": "model", "label": _("Model"), "fieldtype": "Data", "width": 110},
		{"fieldname": "turi", "label": _("Yoqilg'i/moy"), "fieldtype": "Data", "width": 120},
		{"fieldname": "qty", "label": _("Litr"), "fieldtype": "Float", "width": 90},
		{"fieldname": "amount", "label": _("Summa"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "km", "label": _("Yurgan km"), "fieldtype": "Float", "width": 100},
		{"fieldname": "sarf_100", "label": _("L / 100 km"), "fieldtype": "Float", "width": 100},
		{"fieldname": "moto", "label": _("Motor soat"), "fieldtype": "Float", "width": 100},
		{"fieldname": "sarf_soat", "label": _("L / soat"), "fieldtype": "Float", "width": 90},
	]
	return columns, rows
