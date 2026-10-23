# Beton Tannarxi ("АВ РАС РЕЦ сум" / «ГП СС»): oyma-oy har bir beton markasi qancha ishlab chiqarilgan, xomashyoning har
# biriga qancha pul ketgan va 1 куб tannarxi (СС). Narx - xomashyoning ombordagi o'rtacha tan narxi (Приход narxi).
#   Месяц | Марка | Кол-во (куб) | <xomashyo 1> | <xomashyo 2> ... | Итого СС | СС 1 куб
# Manba: tasdiqlangan «Производство» (Stock Entry Manufacture). Sotuv va marja - «ПР Срав.» hisobotida.

import frappe
from frappe import _
from frappe.utils import flt, getdate

from carieer.carieer.report.common import bold, prepare

OYLAR = (
	"Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
	"Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)  # fmt: skip


def execute(filters=None):
	filters = prepare(filters, period="year")
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	rows = get_rows(filters)
	xomashyolar = list(dict.fromkeys(r.item_code for r in rows if not r.is_finished_item))
	data = get_data(rows, xomashyolar, currency)
	return get_columns(xomashyolar), data, None, None, get_summary(data, currency)


def get_columns(xomashyolar):
	cur = {"fieldtype": "Currency", "options": "currency"}
	cols = [
		{"label": _("Месяц"), "fieldname": "oy", "fieldtype": "Data", "width": 120},
		{"label": _("Марка"), "fieldname": "marka", "fieldtype": "Link", "options": "Item", "width": 140},
		{
			"label": _("Кол-во (куб)"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"precision": "2",
			"width": 100,
		},
	]
	cols += [
		{"label": item, "fieldname": f"x_{i}", **cur, "width": 125} for i, item in enumerate(xomashyolar)
	]
	cols += [
		{"label": _("Итого СС"), "fieldname": "jami", **cur, "width": 140},
		{"label": _("СС 1 куб"), "fieldname": "ss", **cur, "width": 120},
		{"label": "", "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]
	return cols


def get_rows(filters):
	return frappe.db.sql(
		"""select se.name, se.posting_date, bom.item marka, se.fg_completed_qty, d.item_code, d.amount,
			ifnull(d.is_finished_item, 0) is_finished_item, ifnull(d.s_warehouse, '') s_warehouse
		from `tabStock Entry` se join `tabBOM` bom on bom.name = se.bom_no
			join `tabStock Entry Detail` d on d.parent = se.name
		where se.docstatus = 1 and se.purpose = 'Manufacture' and se.company = %(company)s
			and se.posting_date between %(from_date)s and %(to_date)s
		order by se.posting_date, bom.item, d.idx""",
		dict(filters),
		as_dict=True,
	)


def get_data(rows, xomashyolar, currency):
	col = {item: f"x_{i}" for i, item in enumerate(xomashyolar)}
	groups, seen = {}, set()
	for r in rows:
		sana = getdate(r.posting_date)
		key = (sana.year, sana.month, r.marka)
		g = groups.setdefault(
			key,
			{
				"oy": f"{OYLAR[sana.month - 1]} {sana.year}",
				"marka": r.marka,
				"qty": 0,
				"jami": 0,
				"currency": currency,
			},
		)
		if r.name not in seen:
			seen.add(r.name)
			g["qty"] += flt(r.fg_completed_qty)
		if r.is_finished_item or not r.s_warehouse:
			continue
		g[col[r.item_code]] = g.get(col[r.item_code], 0) + flt(r.amount)
		g["jami"] += flt(r.amount)
	out = []
	for key in sorted(groups):
		g = groups[key]
		g["ss"] = g["jami"] / g["qty"] if g["qty"] else None
		out.append(g)
	if out:
		total = {"oy": bold(_("ЖАМИ")), "currency": currency}
		for f in ["qty", "jami", *col.values()]:
			total[f] = sum(flt(g.get(f)) for g in out)
		total["ss"] = total["jami"] / total["qty"] if total["qty"] else None
		out.append(total)
	return out


def get_summary(data, currency):
	if not data:
		return []
	total = data[-1]
	return [
		{
			"label": _("Ishlab chiqarildi (куб)"),
			"value": total["qty"],
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"label": _("Xomashyo sarfi (СС)"),
			"value": total["jami"],
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Orange",
		},
		{
			"label": _("1 куб o'rtacha СС"),
			"value": total["ss"] or 0,
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green",
		},
	]
