# Ombor hisobotlari (Мат отчет, ОСТАТОК ОБЩ, Сырьё СС, СС ОБЩ ...) uchun umumiy yordamchilar.
# Manba - Stock Ledger Entry (ombor harakati bo'lgan barcha tasdiqlangan hujjatlar).
# Harakat miqdori har doim oldingi qoldiqdan farq sifatida olinadi: Инвентаризация (Stock Reconciliation)
# actual_qty'ni 0 yozadi, yangi qoldiqni esa qty_after_transaction'da saqlaydi.

import frappe
from frappe.utils import flt

PURCHASE_TYPES = ("Purchase Invoice", "Purchase Receipt")
SALES_TYPES = ("Sales Invoice", "Delivery Note")
FINISHED_GROUP = "Готовый продукт"


def get_sles(filters, to_date=None, items=None) -> list[frappe._dict]:
	"""Firma bo'yicha SLE'lar (to_date gacha), xronologik tartibda. Stock Entry maqsadi (purpose) ham olinadi."""
	cond = ["sle.company = %(company)s", "sle.is_cancelled = 0", "sle.posting_date <= %(to_date)s"]
	values = {"company": filters.company, "to_date": to_date or filters.to_date}
	if filters.get("warehouse"):
		cond.append("sle.warehouse = %(warehouse)s")
		values["warehouse"] = filters.warehouse
	if filters.get("item_group"):
		cond.append("item.item_group = %(item_group)s")
		values["item_group"] = filters.item_group
	if items is not None:
		if not items:
			return []
		cond.append("sle.item_code in %(items)s")
		values["items"] = list(items)
	return frappe.db.sql(
		f"""select sle.item_code, sle.warehouse, sle.posting_date, sle.qty_after_transaction,
			sle.stock_value_difference, sle.voucher_type, sle.voucher_no,
			ifnull(se.purpose, '') purpose, item.item_group, item.stock_uom uom
		from `tabStock Ledger Entry` sle join `tabItem` item on item.name = sle.item_code
			left join `tabStock Entry` se on sle.voucher_type = 'Stock Entry' and se.name = sle.voucher_no
		where {" and ".join(cond)}
		order by sle.item_code, sle.warehouse, sle.posting_datetime, sle.creation""",
		values,
		as_dict=True,
	)


def with_movement(sles):
	"""Har bir SLE'ga «qty» (qoldiq o'zgarishi) va «val» (summa o'zgarishi) qo'shadi."""
	last_qty = {}
	for e in sles:
		key = (e.item_code, e.warehouse)
		e.qty = flt(e.qty_after_transaction) - last_qty.get(key, 0.0)
		e.val = flt(e.stock_value_difference)
		last_qty[key] = flt(e.qty_after_transaction)
	return sles


def month_end_balances(sles, months) -> dict:
	"""{item_code: {month.key: [qty, value]}} - har oy oxiridagi qoldiq (kumulyativ, barcha omborlar)."""
	deltas = {}
	for e in sles:
		ym = e.posting_date.strftime("%Y-%m")
		d = deltas.setdefault(e.item_code, {}).setdefault(ym, [0.0, 0.0])
		d[0] += e.qty
		d[1] += e.val
	out = {}
	for item, per_ym in deltas.items():
		# birinchi oydan oldingi harakatlar ham (boshlang'ich qoldiq) qo'shiladi
		ordered = sorted(per_ym.items())
		i, qty, val, res = 0, 0.0, 0.0, {}
		for m in months:
			while i < len(ordered) and ordered[i][0] <= m.key:
				qty += ordered[i][1][0]
				val += ordered[i][1][1]
				i += 1
			res[m.key] = [qty, val]
		out[item] = res
	return out


def item_meta(sles) -> dict:
	return {e.item_code: frappe._dict(item_group=e.item_group, uom=e.uom) for e in sles}


def finished_items(company) -> set:
	"""Tayyor mahsulot: firmada retsepti (BOM) bor tovarlar va «Готовый продукт» guruhidagilar."""
	items = set(
		frappe.get_all("BOM", filters={"company": company, "docstatus": 1}, pluck="item", distinct=True)
	)
	items |= set(frappe.get_all("Item", filters={"item_group": FINISHED_GROUP}, pluck="name"))
	return items


def raw_items(company) -> list[str]:
	"""Xomashyo: ombor tovari (is_stock_item), tayyor mahsulot emas."""
	finished = finished_items(company)
	return [
		i
		for i in frappe.get_all(
			"Item", filters={"is_stock_item": 1, "disabled": 0}, pluck="name", order_by="name"
		)
		if i not in finished
	]


def is_incoming(e) -> bool:
	"""Jadvaldagi «Приход»: omborga kirim (xarid, boshlang'ich qoldiq, Material Receipt ...). Omborlar orasidagi
	ko'chirish (Material Transfer) va Инвентаризация farqi kirim hisoblanmaydi."""
	return e.qty > 0 and e.voucher_type != "Stock Reconciliation" and e.purpose != "Material Transfer"
