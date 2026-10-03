# Balans ("Баланс"): har oy oxiridagi holat, oyma-oy ustunlar.
# Google Sheets'dagi "Баланс" varag'i tartibida: Активы -> Итого -> Пассивы (majburiyatlar, kapital,
# накопленная прибыль/убыток: прошлых периодов va текущего периода) -> Итого -> Разница.
# Manba: GL Entry, hisoblar daraxti hisoblar rejasidan. Summalar firma valyutasida.
# Yil yopilmagan bo'lsa ham to'g'ri chiqadi: foyda daromad/xarajat hisoblari qoldig'idan hisoblanadi
# (yil yopish provodkasi qilingan bo'lsa u Retained Earnings hisobida ko'rinadi, ikki marta sanalmaydi).

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.moliya import get_accounts, get_monthly_gl, get_months, line, month_columns, tree_rows
from carieer.utils import check_report_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	check_report_company(filters)
	months = get_months(filters.from_date, filters.to_date)
	return month_columns(months, _("Модда"), total=False, width=150), get_data(filters, months)


def get_data(filters, months):
	company = filters.company
	keys = [m.key for m in months]
	fields = [m.fieldname for m in months]

	balance_accounts = get_accounts(company, ("Asset", "Liability", "Equity"))
	balance_values = get_monthly_gl(company, ("Asset", "Liability", "Equity"), filters.to_date)
	asset = [a for a in balance_accounts if a.root_type == "Asset"]
	liability = [a for a in balance_accounts if a.root_type == "Liability"]
	equity = [a for a in balance_accounts if a.root_type == "Equity"]

	asset_rows, asset_total = tree_rows(asset, balance_values, months, cumulative=True)
	liability_rows, liability_total = tree_rows(liability, balance_values, months, sign=-1, cumulative=True)
	equity_rows, equity_total = tree_rows(equity, balance_values, months, sign=-1, cumulative=True)

	# Foyda: daromad - xarajat (kredit - debet). Oy ichidagi va shu oygacha to'plangan.
	pl = {}
	for per_month in get_monthly_gl(company, ("Income", "Expense"), filters.to_date).values():
		for ym, net in per_month.items():
			pl[ym] = pl.get(ym, 0) - flt(net)
	current = [flt(pl.get(k)) for k in keys]
	cumulative = [sum(v for ym, v in pl.items() if ym <= k) for k in keys]
	previous = [c - cur for c, cur in zip(cumulative, current)]

	passive_total = [
		flt(liability_total.get(f)) + flt(equity_total.get(f)) + c for f, c in zip(fields, cumulative)
	]
	diff = [flt(asset_total.get(f)) - p for f, p in zip(fields, passive_total)]

	def header(label):
		return {"label": label, "bold": 1, "is_header": 1}

	def total(label, vals, **extra):
		return line(label, months, vals, total=False, bold=1, **extra)

	return [
		header(_("Активы ↓")),
		*shift(asset_rows),
		total(_("Итого активы"), asset_total, total_row=1),
		header(_("Пассивы ↓")),
		total(_("Обязательства"), liability_total),
		*shift(liability_rows),
		total(_("Капитал"), equity_total),
		*shift(equity_rows),
		total(_("Накопленная прибыль / убыток"), cumulative),
		line(_("— прошлых периодов"), months, previous, total=False, indent=1),
		line(_("— текущего периода (месяц)"), months, current, total=False, indent=1),
		total(_("Итого пассивы"), passive_total, total_row=1),
		total(_("Разница (должна быть 0)"), [flt(d, 2) for d in diff]),
	]


def shift(rows):
	"""Ildiz guruh qatori ("Assets" ...) tashlanadi - uning o'rniga o'zimizning sarlavha/jami qatorlar bor."""
	return [{**r, "bold": 1 if r["is_group"] and r["indent"] == 1 else 0} for r in rows if r["indent"] > 0]
