# Retsept Sarfi ("Расход сырья по рецепту за период" / «Произ.расход»): davrda ishlab chiqarilgan har bir beton markasi
# uchun xomashyo sarfi - retsept me'yori (1 куб), me'yor bo'yicha kerak bo'lgani, haqiqatda ayrilgani va summasi.
#   Производимая продукция | Кол-во ПП | Расходная продукция | Ед.изм | Норма | По норме | Факт | Отклонение | Сумма
# Manba: tasdiqlangan «Производство» (Stock Entry Manufacture) - Sotuv tasdiqlanganda o'zi yaratiladi.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import bold, prepare


def execute(filters=None):
	filters = prepare(filters, period="month")
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	data, produced = get_data(filters)
	return get_columns(currency), data, None, None, get_summary(data, produced, currency)


def get_columns(currency):
	cur = {"fieldtype": "Currency", "options": "currency"}
	return [
		{
			"label": _("Производимая продукция"),
			"fieldname": "marka",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{
			"label": _("Кол-во ПП (куб)"),
			"fieldname": "produced",
			"fieldtype": "Float",
			"precision": "2",
			"width": 110,
		},
		{
			"label": _("Расходная продукция"),
			"fieldname": "xomashyo",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{"label": _("Ед.изм"), "fieldname": "uom", "fieldtype": "Data", "width": 70},
		{
			"label": _("Норма (1 куб)"),
			"fieldname": "norma",
			"fieldtype": "Float",
			"precision": "3",
			"width": 100,
		},
		{"label": _("По норме"), "fieldname": "kerak", "fieldtype": "Float", "precision": "3", "width": 110},
		{
			"label": _("Расход (факт)"),
			"fieldname": "fakt",
			"fieldtype": "Float",
			"precision": "3",
			"width": 110,
		},
		{"label": _("Отклонение"), "fieldname": "farq", "fieldtype": "Float", "precision": "3", "width": 100},
		{"label": _("Сумма"), "fieldname": "amount", **cur, "width": 140},
		{"label": _("Цена СС"), "fieldname": "rate", **cur, "width": 110},
		{"label": "", "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_data(filters):
	values = dict(filters)
	item_cond = " and bom.item = %(item_code)s" if filters.get("item_code") else ""
	ses = frappe.db.sql(
		f"""select se.name, se.bom_no, se.fg_completed_qty, bom.item marka
		from `tabStock Entry` se join `tabBOM` bom on bom.name = se.bom_no
		where se.docstatus = 1 and se.purpose = 'Manufacture' and se.company = %(company)s
			and se.posting_date between %(from_date)s and %(to_date)s{item_cond}""",
		values,
		as_dict=True,
	)
	if not ses:
		return [], 0
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	produced = {}
	for se in ses:
		produced[se.marka] = produced.get(se.marka, 0) + flt(se.fg_completed_qty)

	# haqiqiy sarf: Stock Entry'ning xomashyo qatorlari (ombordan ayrilgan)
	fakt = {}
	for r in frappe.db.sql(
		"""select se.bom_no, bom.item marka, d.item_code, d.stock_uom, sum(d.transfer_qty) qty, sum(d.amount) amount
		from `tabStock Entry Detail` d join `tabStock Entry` se on se.name = d.parent
			join `tabBOM` bom on bom.name = se.bom_no
		where se.name in %(names)s and ifnull(d.s_warehouse, '') != '' and ifnull(d.is_finished_item, 0) = 0
		group by bom.item, d.item_code, d.stock_uom""",
		{"names": [se.name for se in ses]},
		as_dict=True,
	):
		fakt[(r.marka, r.item_code)] = r

	# me'yor bo'yicha: har bir hujjat o'z retsepti bilan (retsept o'zgargan bo'lsa ham to'g'ri)
	kerak, norma = {}, {}
	bom_items = {}
	for se in ses:
		if se.bom_no not in bom_items:
			bom_qty = flt(frappe.db.get_value("BOM", se.bom_no, "quantity")) or 1
			bom_items[se.bom_no] = [
				(r.item_code, r.stock_uom, flt(r.stock_qty) / bom_qty)
				for r in frappe.get_all(
					"BOM Item",
					filters={"parent": se.bom_no},
					fields=["item_code", "stock_uom", "stock_qty"],
					order_by="idx",
				)
			]
		for item_code, uom, per_unit in bom_items[se.bom_no]:
			key = (se.marka, item_code)
			kerak[key] = kerak.get(key, 0) + per_unit * flt(se.fg_completed_qty)
			norma.setdefault(key, (per_unit, uom))

	out = []
	for marka in sorted(produced):
		keys = [k for k in dict.fromkeys(list(norma) + list(fakt)) if k[0] == marka]
		jami = 0
		for i, key in enumerate(keys):
			f = fakt.get(key) or frappe._dict(qty=0, amount=0, stock_uom=None)
			per_unit, uom = norma.get(key, (None, f.stock_uom))
			need = kerak.get(key, 0)
			jami += flt(f.amount)
			out.append(
				{
					"marka": marka if i == 0 else None,
					"produced": produced[marka] if i == 0 else None,
					"xomashyo": key[1],
					"uom": uom or f.stock_uom,
					"norma": per_unit,
					"kerak": need,
					"fakt": flt(f.qty),
					"farq": flt(f.qty) - need,
					"amount": flt(f.amount),
					"rate": flt(f.amount) / flt(f.qty) if flt(f.qty) else None,
					"currency": currency,
				}
			)
		out.append(
			{
				"marka": None,
				"xomashyo": bold(_("ЖАМИ {0}").format(marka)),
				"amount": jami,
				"rate": None,
				"norma": None,
				"currency": currency,
				"bold": 1,
			}
		)
	return out, sum(produced.values())


def get_summary(data, produced, currency):
	jami = sum(flt(r.get("amount")) for r in data if not r.get("bold"))
	return [
		{"label": _("Ishlab chiqarildi (куб)"), "value": produced, "datatype": "Float", "indicator": "Blue"},
		{
			"label": _("Xomashyo sarfi"),
			"value": jami,
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Orange",
		},
		{
			"label": _("1 куб o'rtacha tannarxi"),
			"value": jami / produced if produced else 0,
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green",
		},
	]
