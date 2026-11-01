# Ss Obsh ("СС ОБЩ"): barcha tovarlarning har oydagi tan narxi (1 birlik) bitta jadvalda - jadvaldagi varaq kabi:
#   Тип сс | Наименования | Ед.изм. | <oy 1> | <oy 2> ...
#   Готовый продукт (beton markalari) - «ГП СС»: oy ichida ishlab chiqarilganining 1 куб tan narxi (Beton Tannarxi kabi:
#     «Производство» xomashyo sarfi / ishlab chiqarilgan куб); shu oyda ishlab chiqarilmagan bo'lsa - o'tgan oy СС.
#   Xomashyo (Полуфабрикат, Сырьё ...) - «Сырьё СС»: oylik o'rtacha tan narx (Syrye SS hisoboti formulasi).

import frappe
from frappe import _
from frappe.utils import flt, getdate

from carieer.carieer.report.beton_tannarxi.beton_tannarxi import get_rows
from carieer.carieer.report.common import prepare
from carieer.carieer.report.moliya import get_months
from carieer.carieer.report.ombor import FINISHED_GROUP
from carieer.carieer.report.syrye_ss.syrye_ss import compute_ss


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	data = finished_rows(filters, months) + raw_rows(filters, months)
	return get_columns(months), data


def get_columns(months):
	cols = [
		{"label": _("Тип сс"), "fieldname": "tip", "fieldtype": "Data", "width": 130},
		{
			"label": _("Наименования"),
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


def finished_rows(filters, months):
	"""Beton markalari: oy -> [куб, xomashyo summasi] -> СС 1 куб (oyda ishlab chiqarilmasa - o'tgan oy qiymati)."""
	per_month, seen = {}, set()
	for r in get_rows(filters):
		ym = getdate(r.posting_date).strftime("%Y-%m")
		g = per_month.setdefault(r.marka, {}).setdefault(ym, [0.0, 0.0])
		if r.name not in seen:
			seen.add(r.name)
			g[0] += flt(r.fg_completed_qty)
		if not r.is_finished_item and r.s_warehouse:
			g[1] += flt(r.amount)
	out = []
	for marka in sorted(per_month):
		row = {
			"tip": FINISHED_GROUP,
			"item_code": marka,
			"uom": frappe.get_cached_value("Item", marka, "stock_uom"),
		}
		prev = None
		for m in months:
			qty, summa = per_month[marka].get(m.key, (0.0, 0.0))
			prev = summa / qty if qty else prev
			row[m.fieldname] = flt(prev, 2) if prev else None
		out.append(row)
	return out


def raw_rows(filters, months):
	ss, meta = compute_ss(filters, months)
	out = []
	for item in sorted(ss, key=lambda i: (meta[i].item_group or "", i)):
		vals = {m.fieldname: flt(ss[item][m.key], 2) if ss[item][m.key] else None for m in months}
		if any(vals.values()):
			out.append({"tip": meta[item].item_group, "item_code": item, "uom": meta[item].uom, **vals})
	return out
