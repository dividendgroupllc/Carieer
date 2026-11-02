# Zarplata ("Зарплата"): har bir xodim bo'yicha davr ichida hisoblangan va to'langan ish haqi:
#   Сотрудник | Ф.И.О | Начислено | Выплачено | Остаток (к выплате) [| har oy to'langani]
# Начислено - «Расчёт ЗП» hisobi (Оклад / Рабочие часы × ishlagan soat).
# Выплачено - (1) xodimga to'lov: GL Entry'da party_type = Employee debeti (Kassa «Сотрудник» -> Payment Entry, yoki
#             Journal Entry); (2) Kassa chiqimi xarajat sifatida, kategoriya «Зарплата ...» - xodim «Kontragent nomi»
#             bo'yicha topiladi (topilmasa - nomi bilan alohida qator).

import frappe
from frappe import _
from frappe.utils import cint, flt

from carieer.carieer.report.common import bold, prepare
from carieer.carieer.report.moliya import get_months
from carieer.carieer.report.raschet_zp.raschet_zp import hisobla


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	oylar = cint(filters.get("oylar"))
	data = get_data(filters, months, oylar)
	return get_columns(months, oylar, currency), data, None, None, get_summary(data, currency)


def get_columns(months, oylar, currency):
	cur = {"fieldtype": "Currency", "options": currency}
	cols = [
		{
			"label": _("Сотрудник"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{"label": _("Ф.И.О"), "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
		{"label": _("Начислено"), "fieldname": "nachisleno", **cur, "width": 140},
		{"label": _("Выплачено"), "fieldname": "vyplacheno", **cur, "width": 140},
		{"label": _("Остаток (к выплате)"), "fieldname": "ostatok", **cur, "width": 150},
	]
	if oylar:
		cols += [
			{"label": _("Выплачено") + f": {m.label}", "fieldname": m.fieldname, **cur, "width": 130}
			for m in months
		]
	return cols


def get_data(filters, months, oylar):
	employee = filters.get("employee")
	values = {**filters, "employee": employee}
	key_to_field = {m.key: m.fieldname for m in months}
	rows = {}

	def row(key, employee_code=None, name=None):
		return rows.setdefault(
			key, frappe._dict(employee=employee_code, employee_name=name, nachisleno=0.0, vyplacheno=0.0)
		)

	for code, e in hisobla(filters.company, months, employee).items():
		row(code, code, e.employee_name).nachisleno += sum(flt(v) for v in e.summa.values())

	def paid(r, ym, amount):
		r.vyplacheno += flt(amount)
		f = key_to_field.get(ym)
		if f:
			r[f] = flt(r.get(f)) + flt(amount)

	emp_cond = " and party = %(employee)s" if employee else ""
	for g in frappe.db.sql(
		f"""select party, date_format(posting_date, '%%Y-%%m') ym, sum(debit) amount
		from `tabGL Entry`
		where company = %(company)s and is_cancelled = 0 and party_type = 'Employee'
			and posting_date between %(from_date)s and %(to_date)s and debit > 0 {emp_cond}
		group by party, ym""",
		values,
		as_dict=True,
	):
		paid(row(g.party, g.party), g.ym, g.amount)

	# xodimni nomi bo'yicha topish (Kassa «Kontragent nomi» - erkin matn)
	xodimlar = frappe.get_all("Employee", filters={"company": filters.company}, fields=["name", "employee_name"])
	by_name = {(e.employee_name or "").strip().lower(): e.name for e in xodimlar}
	by_name.update({e.name.lower(): e.name for e in xodimlar})
	for k in frappe.db.sql(
		"""select party_name, date_format(sana, '%%Y-%%m') ym, sum(summa_sum) amount
		from `tabKassa`
		where company = %(company)s and docstatus = 1 and turi = 'Расход'
			and ifnull(party_type, '') != 'Сотрудник' and kategoriya like 'Зарплата%%'
			and sana between %(from_date)s and %(to_date)s
		group by party_name, ym""",
		values,
		as_dict=True,
	):
		name = (k.party_name or "").strip()
		code = by_name.get(name.lower())
		if employee and code != employee:
			continue
		paid(row(code or f"name:{name}", code, name or _("(nomi ko'rsatilmagan)")), k.ym, k.amount)

	data, total = [], frappe._dict(employee_name=bold(_("Итого")))
	numeric = ["nachisleno", "vyplacheno", "ostatok"] + ([m.fieldname for m in months] if oylar else [])
	for r in sorted(rows.values(), key=lambda r: (r.employee_name or r.employee or "")):
		if not r.employee_name and r.employee:
			r.employee_name = frappe.db.get_value("Employee", r.employee, "employee_name")
		r.ostatok = r.nachisleno - r.vyplacheno
		for f in numeric:
			total[f] = flt(total.get(f)) + flt(r.get(f))
			r[f] = flt(r.get(f), 2) or None
		data.append(r)
	if data:
		data.append(total)
	return data


def get_summary(data, currency):
	if not data:
		return []
	t = data[-1]
	return [
		{"label": _("Начислено"), "value": flt(t.nachisleno), "datatype": "Currency", "currency": currency, "indicator": "Blue"},
		{"label": _("Выплачено"), "value": flt(t.vyplacheno), "datatype": "Currency", "currency": currency, "indicator": "Green"},
		{
			"label": _("Остаток (к выплате)"),
			"value": flt(t.ostatok),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Red" if flt(t.ostatok) > 0.005 else "Gray",
		},
	]
