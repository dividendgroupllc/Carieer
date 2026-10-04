# Foyda Zarar (P&L, "Отчет о прибылях и убытках"): oyma-oy.
# Google Sheets'dagi "P&L" / "P&L Разбитый" varaqlari tartibida:
#   Выручка -> Себестоимость -> Маржинальная прибыль (+ рентабельность)
#   -> Прибыль/убыток от инвентаризации склада -> xarajatlar (1-tur -> 2-tur -> modda)
#   -> Чистая прибыль (+ рентабельность)
# Manba: GL Entry (daromad va xarajat hisoblari). Xarajat daraxti hisoblar rejasidan olinadi
# (install.py -> make_moddalar jadvaldagi kategoriyalar daraxtini yaratadi).

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import prepare
from carieer.carieer.report.moliya import (
	finalize,
	get_accounts,
	get_monthly_gl,
	get_months,
	line,
	month_columns,
	percent_line,
	tree_rows,
)

COGS_TYPES = ("Cost of Goods Sold",)
INVENTAR_TYPES = ("Stock Adjustment",)


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	return month_columns(months, _("Модда")), finalize(get_data(filters, months))


def get_data(filters, months):
	accounts = get_accounts(filters.company, ("Income", "Expense"))
	values = get_monthly_gl(
		filters.company, ("Income", "Expense"), filters.to_date, from_date=months[0].start, skip_closing=True
	)
	income = [a for a in accounts if a.root_type == "Income"]
	expense = [a for a in accounts if a.root_type == "Expense"]
	cogs = {a.name for a in expense if not a.is_group and a.account_type in COGS_TYPES}
	inventar = {a.name for a in expense if not a.is_group and a.account_type in INVENTAR_TYPES}
	fields = [m.fieldname for m in months] + ["total"]

	def minus(a, b):
		return {f: flt(a.get(f)) - flt(b.get(f)) for f in fields}

	income_rows, income_total = tree_rows(income, values, months, sign=-1, base_indent=1)
	cogs_rows, cogs_total = tree_rows(
		expense, values, months, skip={a.name for a in expense} - cogs_parents(expense, cogs), base_indent=1
	)
	inv_rows, inv_total = tree_rows(
		expense,
		values,
		months,
		skip={a.name for a in expense} - cogs_parents(expense, inventar),
		base_indent=1,
	)
	other_rows, other_total = tree_rows(expense, values, months, skip=cogs | inventar)

	margin = minus(income_total, cogs_total)
	net = minus(minus(margin, inv_total), other_total)

	data = [line(_("Выручка"), months, income_total, bold=1), *leaves_only(income_rows)]
	data += [
		line(_("Себестоимость реализованной продукции"), months, cogs_total, bold=1),
		*leaves_only(cogs_rows),
	]
	data += [
		line(_("Маржинальная прибыль"), months, margin, bold=1, total_row=1),
		percent_line(_("Рентабельность по маржинальному доходу, %"), months, margin, income_total),
	]
	if any(flt(v) for v in inv_total.values()):
		data.append(line(_("Убыток (прибыль) от инвентаризации склада"), months, inv_total, bold=1))
	# ildiz guruh ("Expenses") o'rniga "Расходы" qatori, ostida 1-tur -> 2-tur -> modda daraxti
	data += [line(_("Расходы"), months, other_total, bold=1), *[r for r in other_rows if r["indent"] > 0]]
	data += [
		line(_("Чистая прибыль"), months, net, bold=1, total_row=1),
		percent_line(_("Рентабельность по чистой прибыли, %"), months, net, income_total),
	]
	return data


def cogs_parents(accounts, leaves: set) -> set:
	"""Tanlangan hisoblar va ularning barcha ota guruhlari (daraxtda faqat shular qolishi uchun)."""
	by_name = {a.name: a for a in accounts}
	keep = set()
	for name in leaves:
		node = by_name.get(name)
		while node:
			keep.add(node.name)
			node = by_name.get(node.parent_account)
	return keep


def leaves_only(rows):
	"""Faqat oxirgi darajadagi hisoblar (guruhlarsiz) - qisqa bo'limlar uchun."""
	return [{**r, "indent": 1, "bold": 0} for r in rows if not r.get("is_group")]
