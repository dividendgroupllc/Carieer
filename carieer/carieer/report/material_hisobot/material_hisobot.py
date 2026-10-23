# Material Hisobot ("Материальный отчет"): davr uchun har bir tovar bo'yicha
#   Нач. остаток -> Приход -> Расход -> Кон. остаток (miqdor ombor birligida va summa so'mda).
# Manba: Stock Ledger Entry (Sotuv, Приход, Инвентаризация, Stock Entry - ombor harakati bo'lgan barcha hujjatlar).
# Karer tovari tan narxi 0 (yerdan qazib olinadi): uning summasi 0, miqdori esa to'liq ko'rinadi.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import prepare

QTY = ("nach_qty", "prixod_qty", "rasxod_qty", "kon_qty")
VAL = ("nach_val", "prixod_val", "rasxod_val", "kon_val")


def execute(filters=None):
	filters = prepare(filters, period="month")
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	data = get_data(filters)
	return get_columns(filters, currency), data, None, None, get_summary(data, currency)


def get_columns(filters, currency):
	cols = [
		{
			"label": _("Тип"),
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 120,
		},
		{
			"label": _("Наименование"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 170,
		},
		{"label": _("Ед.изм."), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 75},
	]
	if filters.get("by_warehouse"):
		cols.append(
			{
				"label": _("Омбор"),
				"fieldname": "warehouse",
				"fieldtype": "Link",
				"options": "Warehouse",
				"width": 150,
			}
		)
	for key, label in (
		("nach", _("Нач. остаток")),
		("prixod", _("Приход")),
		("rasxod", _("Расход")),
		("kon", _("Кон. остаток")),
	):
		cols.append(
			{
				"label": f"{label}: " + _("кол-во"),
				"fieldname": f"{key}_qty",
				"fieldtype": "Float",
				"width": 120,
			}
		)
		cols.append(
			{
				"label": f"{label}: " + _("сумма"),
				"fieldname": f"{key}_val",
				"fieldtype": "Currency",
				"options": currency,
				"width": 130,
			}
		)
	return cols


def get_data(filters):
	cond = ["sle.company = %(company)s", "sle.is_cancelled = 0", "sle.posting_date <= %(to_date)s"]
	if filters.get("warehouse"):
		cond.append("sle.warehouse = %(warehouse)s")
	if filters.get("item_group"):
		cond.append("item.item_group = %(item_group)s")
	sles = frappe.db.sql(
		f"""select sle.item_code, sle.warehouse, sle.posting_date, sle.qty_after_transaction,
			sle.stock_value_difference, item.item_group, item.stock_uom uom
		from `tabStock Ledger Entry` sle join `tabItem` item on item.name = sle.item_code
		where {" and ".join(cond)}
		order by sle.item_code, sle.warehouse, sle.posting_datetime, sle.creation""",
		filters,
		as_dict=True,
	)
	by_warehouse = filters.get("by_warehouse")
	rows, last_qty = {}, {}
	for e in sles:
		# Инвентаризация (Stock Reconciliation) actual_qty'ni 0 yozadi, yangi qoldiqni esa qty_after_transaction'da
		# saqlaydi: shuning uchun harakat har doim oldingi qoldiqdan farq sifatida olinadi
		prev = last_qty.get((e.item_code, e.warehouse), 0.0)
		qty = flt(e.qty_after_transaction) - prev
		last_qty[(e.item_code, e.warehouse)] = flt(e.qty_after_transaction)
		val = flt(e.stock_value_difference)
		key = (e.item_code, e.warehouse if by_warehouse else "")
		r = rows.setdefault(
			key,
			frappe._dict(
				item_code=e.item_code,
				item_group=e.item_group,
				uom=e.uom,
				warehouse=key[1],
				**dict.fromkeys(QTY + VAL, 0.0),
			),
		)
		r.kon_qty += qty
		r.kon_val += val
		if e.posting_date < filters.from_date:
			r.nach_qty += qty
			r.nach_val += val
			continue
		# miqdorsiz qayta baholash (qty 0, summa bor): musbat - kirimga, manfiy - chiqimga
		incoming = qty > 0 or (qty == 0 and val > 0)
		if incoming:
			r.prixod_qty += qty
			r.prixod_val += val
		else:
			r.rasxod_qty -= qty
			r.rasxod_val -= val

	data = []
	for r in sorted(rows.values(), key=lambda r: (r.item_group or "", r.item_code, r.warehouse)):
		if not any(abs(flt(r[f])) >= 0.0005 for f in QTY + VAL):
			continue
		for f in QTY + VAL:
			r[f] = flt(r[f], 3 if f in QTY else 2) or None
		data.append(r)
	return data


def get_summary(data, currency):
	def total(f):
		return sum(flt(r.get(f)) for r in data)

	return [
		{
			"label": _("Нач. остаток"),
			"value": total("nach_val"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Gray",
		},
		{
			"label": _("Приход"),
			"value": total("prixod_val"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green" if abs(total("prixod_val")) >= 0.005 else "Gray",
		},
		{
			"label": _("Расход"),
			"value": total("rasxod_val"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Red" if abs(total("rasxod_val")) >= 0.005 else "Gray",
		},
		{
			"label": _("Кон. остаток"),
			"value": total("kon_val"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue" if abs(total("kon_val")) >= 0.005 else "Gray",
		},
	]
