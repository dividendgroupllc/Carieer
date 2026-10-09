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
	card,
	drop_empty_months,
	finalize,
	get_accounts,
	get_monthly_gl,
	get_months,
	line,
	money,
	month_columns,
	note_box,
	percent_line,
	tree_rows,
)

COGS_TYPES = ("Cost of Goods Sold",)
INVENTAR_TYPES = ("Stock Adjustment",)


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	data, totals, expense_rows = get_data(filters, months, with_totals=True)
	data = finalize(data)
	columns, shown = drop_empty_months(month_columns(months, _("Модда")), data, months)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	return columns, data, get_message(totals, expense_rows, shown, currency), None, get_summary(totals, currency)


def get_summary(t, currency):
	"""Tepadagi kartochkalar: daromad -> tannarx -> yalpi foyda -> xarajatlar -> sof foyda."""
	income, net = t["income"], t["net"]
	margin_pct = f" ({flt(t['margin'] / income * 100, 1)}%)" if income else ""
	net_pct = f" ({flt(net / income * 100, 1)}%)" if income else ""
	return [
		card(_("Daromad (Выручка)"), income, "Blue", currency),
		card(_("Tannarx (Себестоимость)"), t["cogs"], "Orange", currency),
		card(_("Yalpi foyda") + margin_pct, t["margin"], "Green" if t["margin"] >= 0 else "Red", currency),
		card(_("Xarajatlar (Расходы)"), t["other"] + t["inv"], "Orange", currency),
		card(_("Sof foyda") + net_pct if net >= 0 else _("Zarar") + net_pct, net, "Green" if net >= 0 else "Red", currency),
	]


def get_message(t, expense_rows, months, currency):
	"""Oddiy tilda: davr natijasi va eng katta xarajatlar."""
	period = months[0].label if len(months) == 1 else f"{months[0].label} – {months[-1].label}"
	net = t["net"]
	if not (t["income"] or t["cogs"] or t["other"] or t["inv"]):
		return note_box(_("{0}: daromad ham, xarajat ham yo'q").format(period), [])
	headline = (
		_("{0}: sof foyda {1}").format(period, money(net, currency))
		if net >= 0
		else _("{0}: zarar {1}").format(period, money(-net, currency))
	)
	lines = [
		_("Sotuvdan tushum: <b>{0}</b>, sotilgan tovar tannarxi: <b>{1}</b> → yalpi foyda <b>{2}</b>").format(
			money(t["income"], currency), money(t["cogs"], currency), money(t["margin"], currency)
		),
		_("Boshqa xarajatlar (ish haqi, yoqilg'i, ijara ...): <b>{0}</b>").format(money(t["other"], currency)),
	]
	if t["inv"]:
		lines.append(_("Inventarizatsiya natijasi: <b>{0}</b>").format(money(-t["inv"], currency)))
	top = sorted(
		(r for r in expense_rows if not r.get("is_group") and flt(r.get("total")) > 0),
		key=lambda r: -flt(r["total"]),
	)[:3]
	if top:
		lines.append(
			_("Eng katta xarajatlar: {0}").format(
				", ".join(f"{frappe.utils.escape_html(r['label'])} — {money(r['total'], currency)}" for r in top)
			)
		)
	if t["income"] and not t["cogs"]:
		lines.append(
			_("Diqqat: tannarx 0 - sotilgan tovarning kirim narxi (tan narxi) kiritilmagan, foyda haqiqiydan katta ko'rinadi.")
		)
	color = "var(--green-600, #2f9e44)" if net >= 0 else "var(--red-600, #e03636)"
	return note_box(frappe.utils.escape_html(headline), lines, color)


def get_data(filters, months, with_totals=False):
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
	# jadvaldagi kabi doim ko'rinadi (nol bo'lsa ham)
	data.append(line(_("Убыток (прибыль) от инвентаризации склада"), months, inv_total, bold=1))
	# ildiz guruh ("Expenses") va ERPNext'ning «Прямые / Косвенные расходы» pog'onasi o'rniga "Расходы" qatori,
	# ostida jadvaldagi 1-tur (Административный, Производственный ...) -> 2-tur -> modda daraxti
	expense_rows = []
	for r in other_rows:
		if r["indent"] == 0 or (r["indent"] == 1 and r.get("is_group")):
			continue
		indent = max(r["indent"] - 1, 1)
		expense_rows.append({**r, "indent": indent, "bold": 1 if r.get("is_group") and indent == 1 else 0})
	data += [line(_("Расходы"), months, other_total, bold=1), *expense_rows]
	data += [
		line(_("Чистая прибыль"), months, net, bold=1, total_row=1),
		percent_line(_("Рентабельность по чистой прибыли, %"), months, net, income_total),
	]
	if not with_totals:
		return data
	totals = {
		"income": flt(income_total.get("total")),
		"cogs": flt(cogs_total.get("total")),
		"margin": flt(margin.get("total")),
		"inv": flt(inv_total.get("total")),
		"other": flt(other_total.get("total")),
		"net": flt(net.get("total")),
	}
	return data, totals, [dict(r) for r in other_rows]


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
