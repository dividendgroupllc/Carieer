# Balans Bpr ("Баланс бпр"): Баланс (qatorlari bir xil) + pastida «Оборудование» (asosiy vositalar) o'zgarishini tekshirish
# bloki - jadvaldagi T:X ustunlari kabi:
#   Фарқ                 - oy ichida Оборудование qoldig'i o'zgarishi
#   Ошди / Камайди       - o'sdi (+1) yoki kamaydi (-1)
#   Приход ОС            - oy ichida ОС hisoblariga kirim (Приход ОС / xarid)
#   Касса (На ОС)        - kassadan «На ОС» kategoriyalari bo'yicha to'langan summa
#   Сверка               - Приход ОС + Касса (На ОС) - Фарқ: 0 bo'lsa o'zgarish to'liq tushuntirilgan
# Eslatma: kassadan «На ОС» kategoriyasi bilan to'langan summa ERPNext'da xarajat hisobiga yoziladi, lekin Баланс'da
# Оборудование qatoriga qo'shiladi va P&L foydasidan ayrilmaydi (balans.py), shuning uchun «Фарқ» ikkalasini ham o'z ichiga oladi.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.balans.balans import OS_GURUH, get_data as balans_data, get_message, get_summary
from carieer.carieer.report.common import prepare
from carieer.carieer.report.moliya import (
	TAQSIM_OS,
	category_info,
	drop_empty_months,
	finalize,
	get_months,
	line,
	month_columns,
)


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	data, totals = balans_data(filters, months)
	data += os_check_rows(filters, months)
	data = finalize(data)
	columns, shown = drop_empty_months(month_columns(months, _("Статья"), total=False, width=150), data, months)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	return columns, data, get_message(totals, shown, currency), None, get_summary(totals, currency)


def monthly(accounts, months, filters, column: str) -> list[float]:
	"""Hisoblar bo'yicha oy ichidagi debet / kredit / (debet - kredit) yig'indisi."""
	if not accounts:
		return [0.0] * len(months)
	expr = {"debit": "sum(debit)", "net": "sum(debit) - sum(credit)"}[column]
	rows = dict(
		frappe.db.sql(
			f"""select date_format(posting_date, '%%Y-%%m'), {expr} from `tabGL Entry`
			where company = %(company)s and is_cancelled = 0 and account in %(accounts)s
				and posting_date between %(from_date)s and %(to_date)s
			group by date_format(posting_date, '%%Y-%%m')""",
			{
				"company": filters.company,
				"accounts": list(accounts),
				"from_date": months[0].start,
				"to_date": filters.to_date,
			},
		)
	)
	return [flt(rows.get(m.key)) for m in months]


def os_check_rows(filters, months) -> list[dict]:
	os_accounts = frappe.get_all(
		"Account",
		filters={"company": filters.company, "is_group": 0, "account_name": ["in", [k for k, v in OS_GURUH.items() if v == "Оборудование"]]},
		pluck="name",
	)
	os_names = [n for n in (k for k, v in category_info().items() if v.taqsimot == TAQSIM_OS)]
	cash_os_accounts = frappe.get_all(
		"Account",
		filters={"company": filters.company, "is_group": 0, "root_type": "Expense", "account_name": ["in", os_names or [""]]},
		pluck="name",
	)
	prixod_os = monthly(os_accounts, months, filters, "debit")
	kassa_os = monthly(cash_os_accounts, months, filters, "net")
	change = [flt(a + b, 2) for a, b in zip(monthly(os_accounts, months, filters, "net"), kassa_os)]
	diff = [flt(p + k - c, 2) for p, k, c in zip(prixod_os, kassa_os, change)]

	rows = [
		{"label": _("Проверка: Оборудование (основные средства)"), "is_header": 1, "bold": 1},
		line(_("Фарқ (изменение за месяц)"), months, change, total=False, indent=1),
		{
			**line(_("Ошди (+1) / Камайди (-1)"), months, [1 if c > 0.005 else -1 if c < -0.005 else 0 for c in change], total=False, indent=1),
			"is_check": 1,
		},
		line(_("Приход ОС"), months, prixod_os, total=False, indent=1),
		line(_("Касса (На ОС)"), months, kassa_os, total=False, indent=1),
		{**line(_("Сверка (Приход ОС + Касса На ОС - Фарқ, 0 = всё объяснено)"), months, diff, total=False, indent=1), "is_check": 1},
	]
	return rows
