# Raschet ZP ("Расчёт ЗП"): har bir xodimning oyma-oy hisoblangan ish haqi - jadvaldagi varaq kabi:
#   Ф.И.О | <oy 1> | <oy 2> ... | Жами
# Oylik = Оклад / Рабочие часы (oy) × ishlagan soat (Посещение). Оклад - «Ишчи ойлиги»dagi oy oxirigacha bo'lgan eng
# oxirgi yozuv; oklad 0 bo'lsa - Сдельный (1 soat stavkasi) × ishlagan soat. «Рабочие дни» kiritilmagan oy uchun -
# dushanba-shanba kunlari × 8 soat.
# «Соатларни кўрсатиш» belgilansa - summa o'rniga ishlagan soatlar chiqadi.

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from carieer.carieer.doctype.ish_kunlari.ish_kunlari import SOAT_KUNIGA, ish_kunlari_soni
from carieer.carieer.report.common import bold, prepare
from carieer.carieer.report.moliya import get_months


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	hisob = hisobla(filters.company, months, filters.get("employee"))
	soat = cint(filters.get("soatlar"))
	data = get_data(hisob, months, soat)
	return get_columns(months, soat), data, None, None, get_summary(hisob, currency)


def get_columns(months, soat):
	cols = [
		{
			"label": _("Сотрудник"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{"label": _("Ф.И.О"), "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
	]
	num = {"fieldtype": "Float", "precision": "2" if soat else "0"}
	cols += [{"label": m.label, "fieldname": m.fieldname, **num, "width": 120} for m in months]
	cols.append({"label": _("Жами"), "fieldname": "total", **num, "width": 130})
	return cols


def hisobla(company: str, months, employee: str | None = None) -> dict:
	"""{employee: {employee_name, soat: {fieldname: h}, summa: {fieldname: so'm}}} - Зарплата hisobotida ham ishlatiladi."""
	if not months:
		return {}
	start, end = months[0].start, months[-1].end
	emp_cond = " and q.employee = %(employee)s" if employee else ""
	values = {"company": company, "start": start, "end": end, "employee": employee}

	soatlar = frappe.db.sql(
		f"""select q.employee, max(q.employee_name) employee_name, date_format(p.sana, '%%Y-%%m') ym,
			sum(q.soat) soat
		from `tabPosesheniye` p join `tabPosesheniye Qator` q on q.parent = p.name
			and q.parenttype = 'Posesheniye'
		where p.company = %(company)s and p.sana between %(start)s and %(end)s {emp_cond}
		group by q.employee, ym""",
		values,
		as_dict=True,
	)
	stavkalar = frappe.db.sql(
		f"""select employee, employee_name, sana, oklad, sdelniy from `tabIshchi Oyligi` q
		where company = %(company)s and sana <= %(end)s {emp_cond}
		order by employee, sana, creation""",
		values,
		as_dict=True,
	)
	ish_soatlari = {
		getdate(r.oy_boshi).strftime("%Y-%m"): flt(r.ish_soatlari)
		for r in frappe.get_all(
			"Ish Kunlari",
			filters={"company": company, "oy_boshi": ["between", [months[0].start, end]]},
			fields=["oy_boshi", "ish_soatlari"],
		)
	}

	out = {}

	def emp(code, name):
		return out.setdefault(code, frappe._dict(employee_name=name, soat={}, summa={}))

	key_to_field = {m.key: m.fieldname for m in months}
	for r in soatlar:
		e = emp(r.employee, r.employee_name)
		e.soat[key_to_field[r.ym]] = flt(r.soat, 2)
	by_emp = {}
	for r in stavkalar:
		by_emp.setdefault(r.employee, []).append(r)
		emp(r.employee, r.employee_name)

	for code, e in out.items():
		for m in months:
			stavka = None
			for r in by_emp.get(code, []):
				if getdate(r.sana) <= m.end:
					stavka = r
			h = flt(e.soat.get(m.fieldname))
			if not stavka or not h:
				continue
			if flt(stavka.oklad):
				norma = ish_soatlari.get(m.key) or ish_kunlari_soni(m.start) * SOAT_KUNIGA
				e.summa[m.fieldname] = flt(flt(stavka.oklad) / norma * h, 2) if norma else 0
			else:
				e.summa[m.fieldname] = flt(flt(stavka.sdelniy) * h, 2)
		if not e.employee_name:
			e.employee_name = frappe.db.get_value("Employee", code, "employee_name")
	return out


def get_data(hisob, months, soat):
	field = "soat" if soat else "summa"
	data, total = [], {"employee_name": bold(_("Итого"))}
	for code, e in sorted(hisob.items(), key=lambda x: x[1].employee_name or x[0]):
		row = {"employee": code, "employee_name": e.employee_name}
		for m in months:
			row[m.fieldname] = e[field].get(m.fieldname) or None
			total[m.fieldname] = flt(total.get(m.fieldname)) + flt(row[m.fieldname])
		row["total"] = sum(flt(v) for v in e[field].values()) or None
		total["total"] = flt(total.get("total")) + flt(row["total"])
		data.append(row)
	if data:
		data.append(total)
	return data


def get_summary(hisob, currency):
	if not hisob:
		return []
	summa = sum(flt(v) for e in hisob.values() for v in e.summa.values())
	soat = sum(flt(v) for e in hisob.values() for v in e.soat.values())
	return [
		{"label": _("Начислено ЗП"), "value": summa, "datatype": "Currency", "currency": currency, "indicator": "Blue"},
		{"label": _("Ishlangan soat"), "value": soat, "datatype": "Float", "indicator": "Gray"},
		{"label": _("Xodimlar"), "value": len(hisob), "datatype": "Int", "indicator": "Gray"},
	]
