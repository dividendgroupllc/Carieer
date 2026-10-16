# Pr Srav ("ПР Срав." / "ПР Срав. Общ"): mahsulot bo'yicha oyma-oy sotuv, tannarx va marja - jadvaldagi ikki varaq:
#   «ПР Срав.»     - Тип категории (tovar guruhi) bo'yicha: Гуруҳлаш = Категория
#   «ПР Срав. Общ» - Наименование (tovar) bo'yicha:          Гуруҳлаш = Наименование
# Har bir guruh uchun: Продажа, СС, Маржа, Рент. %, Доля в продажах %, Кол-во, Сред. цена, Сред. СС.
# Manba: tasdiqlangan Sotuv'ning «Товары» jadvali (korrektirovka va xizmatlar kirmaydi - jadvaldagi kabi
# «Наименование» bo'sh qatorlar hisobga olinmaydi). Summalar firma valyutasida (so'm), СС - ombordan ayrilgan tan narx (Stock Ledger Entry).
# Karer tovarining tan narxi 0 (yerdan qazib olinadi), shuning uchun karer mahsulotida Маржа = Продажа.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import prepare
from carieer.carieer.report.moliya import (
	drop_empty_months,
	finalize,
	get_months,
	line,
	month_columns,
	percent_line,
)


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	data, totals = get_data(filters, months)
	data = finalize(data)
	columns, _shown = drop_empty_months(month_columns(months, _("Наименование")), data, months)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	return columns, data, None, None, get_summary(totals, currency)


def get_data(filters, months):
	by_item = filters.get("guruhlash") == "Наименование"
	group_expr = (
		"ifnull(nullif(i.item_name, ''), i.item_code)" if by_item else "ifnull(nullif(i.item_group, ''), '—')"
	)
	# СС ombordagi haqiqiy tan narxdan (Stock Ledger Entry): ombor qayta hisoblansa ham P&L bilan mos qoladi.
	# Sotuv tovar qatorlari Sales Invoice'ning birinchi qatorlari bilan bir tartibda (Sotuv.make_sales_invoice).
	rows = frappe.db.sql(
		f"""select {group_expr} grp, date_format(s.posting_date, '%%Y-%%m') ym,
			sum(i.amount * ifnull(nullif(s.conversion_rate, 0), 1)) sales,
			sum(ifnull(sle.cost, 0)) cost,
			sum(i.stock_qty) qty
		from `tabSotuv Tovar` i
		join `tabSotuv` s on s.name = i.parent and i.parenttype = 'Sotuv'
		left join `tabSales Invoice Item` sii on sii.parent = s.sales_invoice and sii.idx = i.idx
		left join (
			select voucher_detail_no, -sum(stock_value_difference) cost
			from `tabStock Ledger Entry`
			where voucher_type = 'Sales Invoice' and is_cancelled = 0
			group by voucher_detail_no
		) sle on sle.voucher_detail_no = sii.name
		where s.docstatus = 1 and s.company = %(company)s and ifnull(s.korrektirovka, 0) = 0
			and s.posting_date between %(from_date)s and %(to_date)s
		group by grp, ym""",
		filters,
		as_dict=True,
	)
	keys = [m.key for m in months]
	n = len(keys)
	groups = {}
	for r in rows:
		g = groups.setdefault(r.grp, {"sales": [0.0] * n, "cost": [0.0] * n, "qty": [0.0] * n})
		i = keys.index(r.ym)
		g["sales"][i] += flt(r.sales)
		g["cost"][i] += flt(r.cost)
		g["qty"][i] += flt(r.qty)

	total = {f: [sum(g[f][i] for g in groups.values()) for i in range(n)] for f in ("sales", "cost", "qty")}
	data = block(_("Итого"), total, total, months)
	for name in sorted(groups, key=lambda k: -sum(groups[k]["sales"])):
		data += block(name, groups[name], total, months)
	return data, {f: sum(v) for f, v in total.items()}


def block(name, g, total, months):
	"""Bitta guruh: sarlavha qatori = Продажа, ostida СС, Маржа va ko'rsatkichlar (jadvaldagi qatorlar tartibida)."""
	margin = [s - c for s, c in zip(g["sales"], g["cost"], strict=False)]
	sales_row = line(name, months, g["sales"], bold=1)
	margin_row = line(_("Маржа"), months, margin, indent=1)
	total_row = line("", months, total["sales"])
	qty_row = line(_("Кол-во"), months, g["qty"], indent=1)
	return [
		sales_row,
		line(_("СС"), months, g["cost"], indent=1),
		margin_row,
		percent_line(_("Рент., %"), months, margin_row, sales_row),
		percent_line(_("Доля в продажах, %"), months, sales_row, total_row),
		qty_row,
		ratio_line(_("Сред. цена"), months, sales_row, qty_row),
		ratio_line(_("Сред. СС"), months, line("", months, g["cost"]), qty_row),
	]


def ratio_line(label, months, numerator, denominator):
	"""O'rtacha narx: summa / miqdor (miqdor 0 bo'lsa bo'sh)."""
	row = {"label": label, "indent": 1}
	for f in [m.fieldname for m in months] + ["total"]:
		d = flt(denominator.get(f))
		row[f] = flt(flt(numerator.get(f)) / d, 2) if d else None
	return row


def get_summary(t, currency):
	margin = t["sales"] - t["cost"]
	pct = f" ({flt(margin / t['sales'] * 100, 1)}%)" if t["sales"] else ""
	return [
		{
			"label": _("Продажа"),
			"value": t["sales"],
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue",
		},
		{
			"label": _("СС"),
			"value": t["cost"],
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Orange",
		},
		{
			"label": _("Маржа") + pct,
			"value": margin,
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green" if margin >= 0 else "Red",
		},
		{"label": _("Кол-во"), "value": t["qty"], "datatype": "Float", "indicator": "Gray"},
	]
