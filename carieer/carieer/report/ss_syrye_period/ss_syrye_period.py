# Ss Syrye Period ("СС сырьё на период"): tanlangan davr uchun har bir xomashyoning o'rtacha tan narxi va harakati:
#   Ед.изм. | Нач. остаток (кол-во, сумма) | Приход (кол-во, сумма) | Средняя СС | Расход (кол-во, сумма) | Кон. остаток
#   Средняя СС = (Нач. сумма + Приход сумма) / (Нач. кол-во + Приход кол-во)
#   Расход кол-во = Нач. + Приход - Кон. (davrdagi barcha chiqim: ishlab chiqarish, sotuv, inventarizatsiya ...)
#   Расход сумма / Кон. сумма = miqdor × Средняя СС (jadvaldagi kabi o'rtacha narxda)
# Приход - omborga kirim (xarid, Material Receipt ...; ko'chirish va inventarizatsiyadan tashqari).
# Manba: Stock Ledger Entry.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import bold, prepare
from carieer.carieer.report.ombor import get_sles, is_incoming, raw_items, with_movement

QTY = ("nach_qty", "prixod_qty", "rasxod_qty", "kon_qty")
VAL = ("nach_val", "prixod_val", "rasxod_val", "kon_val")


def execute(filters=None):
	filters = prepare(filters, period="month")
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	data = get_data(filters, currency)
	return get_columns(), data, None, None, get_summary(data, currency)


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency", "width": 130}
	qty = {"fieldtype": "Float", "precision": "3", "width": 110}
	return [
		{"label": _("Тип"), "fieldname": "item_group", "fieldtype": "Data", "width": 120},
		{
			"label": _("Наименование"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 170,
		},
		{"label": _("Ед.изм."), "fieldname": "uom", "fieldtype": "Data", "width": 70},
		{"label": _("Нач. остаток: кол-во"), "fieldname": "nach_qty", **qty},
		{"label": _("Нач. остаток: сумма"), "fieldname": "nach_val", **cur},
		{"label": _("Приход: кол-во"), "fieldname": "prixod_qty", **qty},
		{"label": _("Приход: сумма"), "fieldname": "prixod_val", **cur},
		{"label": _("Средняя СС"), "fieldname": "ss", **cur},
		{"label": _("Расход: кол-во"), "fieldname": "rasxod_qty", **qty},
		{"label": _("Расход: сумма"), "fieldname": "rasxod_val", **cur},
		{"label": _("Кон. остаток: кол-во"), "fieldname": "kon_qty", **qty},
		{"label": _("Кон. остаток: сумма"), "fieldname": "kon_val", **cur},
		{"label": "", "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_data(filters, currency):
	rows = {}
	for e in with_movement(get_sles(filters, items=raw_items(filters.company))):
		r = rows.setdefault(
			e.item_code,
			frappe._dict(
				item_code=e.item_code,
				item_group=e.item_group,
				uom=e.uom,
				currency=currency,
				**dict.fromkeys(QTY + VAL, 0.0),
			),
		)
		r.kon_qty += e.qty
		if e.posting_date < filters.from_date:
			r.nach_qty += e.qty
			r.nach_val += e.val
		elif is_incoming(e):
			r.prixod_qty += e.qty
			r.prixod_val += e.val

	data = []
	for r in sorted(rows.values(), key=lambda r: (r.item_group or "", r.item_code)):
		base = r.nach_qty + r.prixod_qty
		r.ss = (r.nach_val + r.prixod_val) / base if base > 0 else None
		r.rasxod_qty = r.nach_qty + r.prixod_qty - r.kon_qty
		r.rasxod_val = r.rasxod_qty * (r.ss or 0)
		r.kon_val = r.kon_qty * (r.ss or 0)
		if not any(abs(flt(r[f])) >= 0.0005 for f in QTY + VAL):
			continue
		for f in QTY + VAL:
			r[f] = flt(r[f], 3 if f in QTY else 2) or None
		data.append(r)
	if data:
		total = {"item_group": bold(_("ЖАМИ")), "currency": currency}
		for f in VAL:
			total[f] = flt(sum(flt(r.get(f)) for r in data), 2)
		data.append(total)
	return data


def get_summary(data, currency):
	if not data:
		return []
	total = data[-1]
	return [
		{"label": _(label), "value": total[f], "datatype": "Currency", "currency": currency, "indicator": ind}
		for f, label, ind in (
			("nach_val", "Нач. остаток", "Gray"),
			("prixod_val", "Приход", "Green"),
			("rasxod_val", "Расход", "Orange"),
			("kon_val", "Кон. остаток", "Blue"),
		)
	]
