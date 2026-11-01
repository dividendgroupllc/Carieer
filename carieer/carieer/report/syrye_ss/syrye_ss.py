# Syrye SS ("Сырьё СС"): xomashyoning (tayyor mahsulot va xizmatdan tashqari ombor tovarlari) har oydagi o'rtacha
# tan narxi (1 birlik) - jadvaldagi formula bo'yicha:
#   СС(oy) = (o'tgan oy oxiridagi qoldiq × СС(o'tgan oy) + oy ichidagi Приход summasi)
#            / (o'tgan oy oxiridagi qoldiq + oy ichidagi Приход miqdori)
#   oyda kirim bo'lmasa - o'tgan oy СС; birinchi oy - boshlang'ich qoldiq tan narxi (bo'lsa) va kirim bo'yicha.
# Приход - omborga kirim (xarid, Material Receipt ...; ko'chirish va inventarizatsiyadan tashqari).
# Qoldiq - Stock Ledger Entry bo'yicha (barcha harakatlar).

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import prepare
from carieer.carieer.report.moliya import get_months
from carieer.carieer.report.ombor import (
	get_sles,
	is_incoming,
	item_meta,
	month_end_balances,
	raw_items,
	with_movement,
)


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	ss, meta = compute_ss(filters, months)
	data = []
	for item in sorted(ss, key=lambda i: (meta[i].item_group or "", i)):
		vals = {m.fieldname: flt(ss[item][m.key], 2) if ss[item][m.key] else None for m in months}
		if not any(vals.values()):
			continue
		data.append({"item_group": meta[item].item_group, "item_code": item, "uom": meta[item].uom, **vals})
	return get_columns(months), data


def get_columns(months):
	cols = [
		{"label": _("Тип"), "fieldname": "item_group", "fieldtype": "Data", "width": 120},
		{
			"label": _("Наименование"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 170,
		},
		{"label": _("Ед.изм."), "fieldname": "uom", "fieldtype": "Data", "width": 70},
	]
	cols += [
		{"label": m.label, "fieldname": m.fieldname, "fieldtype": "Float", "precision": "2", "width": 125}
		for m in months
	]
	return cols


def compute_ss(filters, months, items=None) -> tuple[dict, dict]:
	"""{item_code: {month.key: СС yoki None}}, {item_code: meta}. items bo'sh bo'lsa - firmaning xomashyolari."""
	items = raw_items(filters.company) if items is None else items
	sles = with_movement(get_sles(filters, items=items))
	balances = month_end_balances(sles, months)
	meta = item_meta(sles)
	first = months[0].start
	opening, purchases = {}, {}
	for e in sles:
		if e.posting_date < first:
			o = opening.setdefault(e.item_code, [0.0, 0.0])
			o[0] += e.qty
			o[1] += e.val
		elif is_incoming(e):
			p = purchases.setdefault(e.item_code, {}).setdefault(e.posting_date.strftime("%Y-%m"), [0.0, 0.0])
			p[0] += e.qty
			p[1] += e.val

	out = {}
	for item in balances:
		oq, ov = opening.get(item, (0.0, 0.0))
		prev_qty = oq
		prev_ss = ov / oq if oq > 0 and ov > 0 else None
		res = {}
		for m in months:
			pq, pv = purchases.get(item, {}).get(m.key, (0.0, 0.0))
			base_qty = max(prev_qty, 0.0) if prev_ss is not None else 0.0
			if pq > 0 and base_qty + pq > 0:
				ss = (base_qty * (prev_ss or 0) + pv) / (base_qty + pq)
			else:
				ss = prev_ss
			res[m.key] = ss
			prev_ss, prev_qty = ss, balances[item][m.key][0]
		out[item] = res
	return out, meta
