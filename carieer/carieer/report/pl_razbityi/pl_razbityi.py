# Pl Razbityi ("P&L Разбитый"): oyma-oy foyda va zarar, xarajatlar kategoriyalar daraxti bilan - jadvaldagi
# «P&L Разбитый» varag'i:
#   Выручка (продукции / услуг) -> Прочие доходы -> Себестоимость -> Маржинальная прибыль (+ рentabelnost)
#   -> Прибыль/убыток от инвентаризации склада -> Расходы: «Категория верхнего уровня» (Административный,
#   Операционный, Производственный, Инвестиционные, Финансовые) -> «Категория 2 типа» -> «Категория 1 типа» (statya)
#   -> Чистая прибыль (+ рентабельность)
# Daraxt hisoblar rejasidan olinadi (install.make_moddalar jadvaldagi Лист55 jadvalini yaratadi). Jadvaldagi varaq
# yarim tayyor edi (qat'iy diapazon, xarajatlar deyarli hisoblanmagan) - bu yerda davrdagi barcha yozuvlar hisobga olinadi.

import frappe
from frappe import _

from carieer.carieer.report.common import prepare
from carieer.carieer.report.foyda_zarar.foyda_zarar import classify, get_message, get_summary
from carieer.carieer.report.moliya import (
	COGS_TYPES,
	INVENTAR_TYPES,
	TAQSIM_OS,
	category_info,
	drop_empty_months,
	finalize,
	get_accounts,
	get_monthly_gl,
	get_months,
	line,
	month_columns,
	percent_line,
	tree_rows,
	vsum,
)


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	data, totals = get_data(filters, months)
	data = finalize(data)
	columns, shown = drop_empty_months(month_columns(months, _("Модда")), data, months)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	return columns, data, get_message(totals, shown, currency), None, get_summary(totals, currency)


def get_data(filters, months):
	company = filters.company
	n = len(months)
	zero = [0.0] * n
	accounts = get_accounts(company, ("Income", "Expense"))
	by_name = {a.name: a for a in accounts}
	values = get_monthly_gl(
		company, ("Income", "Expense"), filters.to_date, from_date=months[0].start, skip_closing=True
	)
	c = classify(accounts, by_name, values, months, company)
	expense = [a for a in accounts if a.root_type == "Expense"]
	special = {
		a.name for a in expense if not a.is_group and a.account_type in (*COGS_TYPES, *INVENTAR_TYPES)
	}
	other_rows, other_total = tree_rows(expense, values, months, skip=special)

	revenue = vsum(c["product"], c["service"], n=n)
	margin = [r - k for r, k in zip(revenue, c["cogs"])]
	other_income = vsum(*c["other_income"].values(), zero, n=n)
	spend = [other_total.get(m.fieldname, 0) for m in months]
	# «На ОС»: kapital qo'yilma - Баланс'dagi Оборудование'ga o'tadi, foydadan ayrilmaydi (P&L bilan bir xil qoida)
	os_names = {k for k, v in category_info(company).items() if v.taqsimot == TAQSIM_OS}
	capex = [
		sum(values.get(a.name, {}).get(m.key, 0) for a in expense if not a.is_group and a.account_name in os_names)
		for m in months
	]
	net = [m - i + o - (s - x) for m, i, o, s, x in zip(margin, c["inv"], other_income, spend, capex)]

	rev_row = line(_("Выручка"), months, revenue, bold=1)
	margin_row = line(_("Маржинальная прибыль"), months, margin, bold=1, total_row=1)
	net_row = line(_("Чистая прибыль"), months, net, bold=1, total_row=1)

	# ildiz guruh ("Expenses") va ERPNext'ning «Прямые / Косвенные» pog'onasi o'rniga "Расходы" qatori,
	# ostida jadvaldagi 1-tur -> 2-tur -> modda daraxti
	expense_rows = []
	for r in other_rows:
		if r["indent"] == 0 or (r["indent"] == 1 and r.get("is_group")):
			continue
		indent = max(r["indent"] - 1, 1)
		expense_rows.append({**r, "indent": indent, "bold": 1 if r.get("is_group") and indent == 1 else 0})

	data = [
		rev_row,
		line(_("Выручка от реализации продукции"), months, c["product"], indent=1),
		line(_("Выручка от реализации услуг"), months, c["service"], indent=1),
		line(_("Прочие доходы"), months, other_income, indent=1),
		line(_("Себестоимость"), months, c["cogs"], bold=1),
		line(_("Сырьевая себестоимость реализованной продукции"), months, c["cogs"], indent=1),
		margin_row,
		percent_line(_("Рентабельность по маржинальному доходу, %"), months, margin_row, rev_row),
		line(_("Прибыль/убыток от инвентаризации склада"), months, c["inv"], bold=1),
		line(_("Расходы"), months, other_total, bold=1),
		*expense_rows,
		net_row,
		percent_line(_("Рентабельность по чистой прибыли, %"), months, net_row, rev_row),
	]
	if any(abs(v) >= 0.005 for v in capex):
		data.append(line(_("в т.ч. капитальные вложения (На ОС): в Баланс, прибыль не уменьшают"), months, capex, indent=1))
	expense_items = {
		r["label"]: r.get("total") or 0 for r in other_rows if not r.get("is_group") and (r.get("total") or 0) > 0
	}
	return data, {
		"income": sum(revenue),
		"cogs": sum(c["cogs"]),
		"margin": sum(margin),
		"other_income": sum(other_income),
		"expenses": sum(spend) - sum(capex) + sum(c["inv"]),
		"net": sum(net),
		"expense_items": expense_items,
	}
