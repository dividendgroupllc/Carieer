# Ostatok Obsh ("ОСТАТОК ОБЩ"): har bir tovarning har oy oxiridagi qoldig'i (miqdorda) - oyma-oy ustunlar, jadvaldagi
# varaq kabi: Тип | Наименование | Ед.изм. | <oy 1> | <oy 2> ... Qoldiq kumulyativ (oy oxiriga), firmaning barcha
# omborlari bo'yicha (yoki tanlangan ombor). Summadagi ko'rinishi - «ОСТАТОК ОБЩ суммовой» (Ostatok Obsh Summovoy).
# Manba: Stock Ledger Entry (Приход, Продажа, Производство, Инвентаризация, Перемещение - barcha ombor harakati).

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import bold, prepare
from carieer.carieer.report.moliya import get_months
from carieer.carieer.report.ombor import get_sles, item_meta, month_end_balances, with_movement


def execute(filters=None):
	return build(filters, summa=False)


def build(filters, summa: bool):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	sles = with_movement(get_sles(filters))
	balances = month_end_balances(sles, months)
	meta = item_meta(sles)
	idx = 1 if summa else 0
	precision = 0 if summa else 3

	data = []
	for item in sorted(balances, key=lambda i: (meta[i].item_group or "", i)):
		vals = {m.fieldname: flt(balances[item][m.key][idx], precision) for m in months}
		if not any(abs(v) >= 0.0005 for v in vals.values()):
			continue
		data.append({"item_group": meta[item].item_group, "item_code": item, "uom": meta[item].uom, **vals})

	if summa and data:
		data = summa_header(filters, months, data) + data
	for r in data:
		for m in months:
			if r.get(m.fieldname) is not None and abs(r[m.fieldname]) < 0.0005:
				r[m.fieldname] = None
	return get_columns(months, summa), data


def get_columns(months, summa):
	cols = [
		{"label": _("Тип"), "fieldname": "item_group", "fieldtype": "Data", "width": 140},
		{
			"label": _("Наименования"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 170,
		},
		{"label": _("Ед.изм."), "fieldname": "uom", "fieldtype": "Data", "width": 70},
	]
	for m in months:
		cols.append(
			{
				"label": m.label,
				"fieldname": m.fieldname,
				"fieldtype": "Float",
				"precision": "0" if summa else "3",
				"width": 130,
			}
		)
	return cols


def summa_header(filters, months, data):
	"""Jadvaldagi tepa qatorlar: Итого (tovarlar summasi) va Баланс bilan tekshiruv (ombor hisoblari qoldig'i)."""
	total = {m.fieldname: sum(flt(r.get(m.fieldname)) for r in data) for m in months}
	rows = [{"item_group": bold(_("Итого")), **total}]
	# ombor yoki tovar guruhi tanlansa Баланс bilan solishtirib bo'lmaydi (u butun firma bo'yicha)
	if filters.get("warehouse") or filters.get("item_group"):
		return rows
	gl = frappe.db.sql(
		"""select date_format(gle.posting_date, '%%Y-%%m') ym, sum(gle.debit) - sum(gle.credit) net
		from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
		where gle.company = %(company)s and gle.is_cancelled = 0 and gle.posting_date <= %(to_date)s
			and acc.account_type = 'Stock'
		group by ym order by ym""",
		filters,
		as_dict=True,
	)
	balans, i, acc = {}, 0, 0.0
	for m in months:
		while i < len(gl) and gl[i].ym <= m.key:
			acc += flt(gl[i].net)
			i += 1
		balans[m.fieldname] = flt(acc, 0)
	farq = {f: flt(total[f] - balans[f], 0) for f in total}
	rows.append({"item_group": _("Баланс (ombor hisobi)"), **balans})
	rows.append({"item_group": bold(_("Разница")), **farq})
	return rows
