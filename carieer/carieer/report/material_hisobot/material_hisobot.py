# Material Hisobot ("Материальный отчет" / «Мат отчет»): davr uchun har bir tovar bo'yicha jadvaldagi ustunlar:
#   Нач. остаток | Закуп | Производство | Расход производство | Продажа | Инвентаризация | Прочее | Кон. остаток
#   Кон. = Нач. + Закуп + Производство - Расход пр-во - Продажа + Инвентаризация + Прочее
# Закуп - xarid (Purchase Invoice / Receipt), Производство / Расход пр-во - «Производство» (Stock Entry Manufacture)
# kirimi / xomashyo sarfi, Продажа - Sales Invoice / Delivery Note, Инвентаризация - sanoq farqi (+ ortiqcha, - kamomad),
# Прочее - ko'chirish (Material Transfer: omborlar bo'yicha alohida bo'lmasa 0), Material Receipt / Issue va boshqalar.
# «Ko'rinish»: Кол-во (ombor birligida) yoki Сумма (so'mda).
# Manba: Stock Ledger Entry. Karer tovari tan narxi 0 (yerdan qazib olinadi): uning summasi 0, miqdori esa to'liq ko'rinadi.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import prepare
from carieer.carieer.report.ombor import PURCHASE_TYPES, SALES_TYPES, get_sles, with_movement

# (kalit, sarlavha, ishora): ishora - harakat qaysi tomonga yoziladi (-1: chiqim musbat ko'rinadi)
USTUNLAR = (
	("nach", "Нач. остаток", 1),
	("zakup", "Закуп", 1),
	("proizv", "Производство", 1),
	("rasxod_pr", "Расход производство", -1),
	("prodaja", "Продажа", -1),
	("inventar", "Инвентаризация", 1),
	("prochee", "Прочее", 1),
	("kon", "Кон. остаток", 1),
)
KEYS = tuple(k for k, _l, _s in USTUNLAR)
SIGN = {k: s for k, _l, s in USTUNLAR}


def execute(filters=None):
	filters = prepare(filters, period="month")
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	summa = filters.get("korinish") == "Сумма"
	data = get_data(filters)
	return get_columns(filters, currency, summa), data, None, None, get_summary(data, currency)


def get_columns(filters, currency, summa):
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
	for key, label, _sign in USTUNLAR:
		if summa:
			cols.append(
				{
					"label": _(label),
					"fieldname": f"{key}_val",
					"fieldtype": "Currency",
					"options": currency,
					"width": 135,
				}
			)
		else:
			cols.append(
				{
					"label": _(label),
					"fieldname": f"{key}_qty",
					"fieldtype": "Float",
					"precision": "3",
					"width": 120,
				}
			)
	return cols


def turi(e) -> str:
	"""Harakat -> jadvaldagi ustun."""
	if e.voucher_type in PURCHASE_TYPES:
		return "zakup"
	if e.voucher_type in SALES_TYPES:
		return "prodaja"
	if e.voucher_type == "Stock Reconciliation":
		return "inventar"
	if e.voucher_type == "Stock Entry" and e.purpose == "Manufacture":
		# miqdorsiz qayta baholash (qty 0, summa bor): musbat - kirimga, manfiy - chiqimga
		return "proizv" if e.qty > 0 or (e.qty == 0 and e.val > 0) else "rasxod_pr"
	return "prochee"


def get_data(filters):
	by_warehouse = filters.get("by_warehouse")
	fields = [f"{k}_{t}" for k in KEYS for t in ("qty", "val")]
	rows = {}
	for e in with_movement(get_sles(filters)):
		key = (e.item_code, e.warehouse if by_warehouse else "")
		r = rows.setdefault(
			key,
			frappe._dict(
				item_code=e.item_code,
				item_group=e.item_group,
				uom=e.uom,
				warehouse=key[1],
				**dict.fromkeys(fields, 0.0),
			),
		)
		r.kon_qty += e.qty
		r.kon_val += e.val
		col = "nach" if e.posting_date < filters.from_date else turi(e)
		r[f"{col}_qty"] += SIGN[col] * e.qty
		r[f"{col}_val"] += SIGN[col] * e.val

	data = []
	for r in sorted(rows.values(), key=lambda r: (r.item_group or "", r.item_code, r.warehouse)):
		if not any(abs(flt(r[f])) >= 0.0005 for f in fields):
			continue
		for f in fields:
			r[f] = flt(r[f], 3 if f.endswith("_qty") else 2) or None
		data.append(r)
	return data


def get_summary(data, currency):
	def total(f):
		return sum(flt(r.get(f)) for r in data)

	cards = []
	for key, label, indicator in (
		("nach", "Нач. остаток", "Gray"),
		("zakup", "Закуп", "Green"),
		("rasxod_pr", "Расход производство", "Orange"),
		("prodaja", "Продажа", "Red"),
		("kon", "Кон. остаток", "Blue"),
	):
		value = total(f"{key}_val")
		cards.append(
			{
				"label": _(label),
				"value": value,
				"datatype": "Currency",
				"currency": currency,
				"indicator": indicator if abs(value) >= 0.005 else "Gray",
			}
		)
	return cards
