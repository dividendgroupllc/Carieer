# Material Hisobot ("Материальный отчет"): davr uchun har bir tovar bo'yicha, jadvaldagi «Мат отчет» kabi
#   Нач. остаток | Приход (закуп) | Производство | Расход производство | Продажа | Инвентаризация |
#   Кон. остаток (miqdor ombor birligida; boshi va oxiri summada ham).
# Производство - Karer'da «Qazib olish», Beton'da retsept bo'yicha chiqarilgan beton.
# Kartalarda (summary) davrdagi kirim / chiqim so'mda.
# Manba: Stock Ledger Entry (Sotuv, Приход, Инвентаризация, Stock Entry - ombor harakati bo'lgan barcha hujjatlar).
# Karer tovari tan narxi 0 (yerdan qazib olinadi): uning summasi 0, miqdori esa to'liq ko'rinadi.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import prepare

# harakat ustunlari; «Кон. остаток» = Нач + закуп + производство - расход - продажа ± инвентаризация
MOVES = (
	("zakup", _("Приход (закуп)")),
	("proizv", _("Производство (қазиб олинди)")),
	("rasxod", _("Расход производство")),
	("sotuv", _("Продажа")),
	("inv", _("Инвентаризация ±")),
)
QTY = ("nach_qty", *(f"{key}_qty" for key, _label in MOVES), "kon_qty")
VAL = ("nach_val", "kon_val")
# faqat kartalar uchun: davrdagi kirim / chiqim so'mda
SUMMARY_VAL = ("prixod_val", "rasxod_val")
SOTUV_VOUCHERS = ("Sales Invoice", "Delivery Note", "POS Invoice")
XARID_VOUCHERS = ("Purchase Invoice", "Purchase Receipt")


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
	def qty_col(key, label):
		return {"label": label, "fieldname": f"{key}_qty", "fieldtype": "Float", "width": 120}

	def val_col(key, label):
		return {
			"label": label,
			"fieldname": f"{key}_val",
			"fieldtype": "Currency",
			"options": currency,
			"width": 130,
		}

	cols += [
		qty_col("nach", _("Нач. остаток: кол-во")),
		val_col("nach", _("Нач. остаток: сумма")),
		*(qty_col(key, label) for key, label in MOVES),
		qty_col("kon", _("Кон. остаток: кол-во")),
		val_col("kon", _("Кон. остаток: сумма")),
	]
	return cols


def harakat_turi(e, qty, by_warehouse):
	"""Ombor harakati -> jadval ustuni. None - ustunga yozilmaydi (firma ichida bir ombordan ikkinchisiga)."""
	if e.voucher_type == "Stock Reconciliation":
		return "inv"
	if e.voucher_type in SOTUV_VOUCHERS:
		return "sotuv"
	if e.voucher_type in XARID_VOUCHERS:
		return "zakup"
	if e.qazib_olish or (e.purpose == "Manufacture" and qty > 0):
		return "proizv"
	if e.purpose == "Material Transfer" and not by_warehouse:
		return None
	return "zakup" if qty > 0 else "rasxod"


def get_data(filters):
	cond = ["sle.company = %(company)s", "sle.is_cancelled = 0", "sle.posting_date <= %(to_date)s"]
	if filters.get("warehouse"):
		cond.append("sle.warehouse = %(warehouse)s")
	if filters.get("item_group"):
		cond.append("item.item_group = %(item_group)s")
	sles = frappe.db.sql(
		f"""select sle.item_code, sle.warehouse, sle.posting_date, sle.qty_after_transaction,
			sle.stock_value_difference, sle.voucher_type, se.purpose, qo.name qazib_olish,
			item.item_group, item.stock_uom uom
		from `tabStock Ledger Entry` sle join `tabItem` item on item.name = sle.item_code
			left join `tabStock Entry` se on sle.voucher_type = 'Stock Entry' and se.name = sle.voucher_no
			left join `tabQazib Olish` qo
				on sle.voucher_type = 'Stock Entry' and qo.stock_entry = sle.voucher_no and qo.docstatus = 1
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
				**dict.fromkeys(QTY + VAL + SUMMARY_VAL, 0.0),
			),
		)
		r.kon_qty += qty
		r.kon_val += val
		if e.posting_date < filters.from_date:
			r.nach_qty += qty
			r.nach_val += val
			continue
		turi = harakat_turi(e, qty, by_warehouse)
		if not turi:
			continue
		# chiqim ustunlari (расход, продажа) musbat son: sotilgan 5 куб = 5
		r[f"{turi}_qty"] += -qty if turi in ("rasxod", "sotuv") else qty
		# miqdorsiz qayta baholash (qty 0, summa bor): musbat - kirimga, manfiy - chiqimga
		incoming = qty > 0 or (qty == 0 and val > 0)
		if incoming:
			r.prixod_val += val
		else:
			r.rasxod_val -= val

	data = []
	for r in sorted(rows.values(), key=lambda r: (r.item_group or "", r.item_code, r.warehouse)):
		if not any(abs(flt(r[f])) >= 0.0005 for f in QTY + VAL + SUMMARY_VAL):
			continue
		for f in QTY + VAL + SUMMARY_VAL:
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
