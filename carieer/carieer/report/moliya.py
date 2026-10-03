# Moliyaviy hisobotlar (Balans, Karer P&L, Pul Oqimi) uchun umumiy yordamchi funksiyalar.
# Google Sheets'dagi "Баланс", "P&L", "Cash Flow" varaqlari kabi: har bir oy alohida ustun.
# Bu hisobotlar Carieer modulida turadi, shuning uchun Karer rollari (Menejer, Kassir) ERPNext'ning
# Accounts bo'limiga o'tmasdan va Accounts rollarisiz ko'ra oladi.

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate

MAX_OY = 36

# ERPNext standart hisoblar rejasi inglizcha: hisobotlarda jadvaldagi kabi ruscha nom ko'rsatiladi
# (hisobning o'zi o'zgartirilmaydi, faqat qator nomi)
ACCOUNT_RU = {
	"Application of Funds (Assets)": "Активы",
	"Current Assets": "Оборотные активы",
	"Accounts Receivable": "Дебиторская задолженность",
	"Debtors": "Дебиторы (клиенты)",
	"Bank Accounts": "Банковские счета",
	"Cash In Hand": "Касса",
	"Cash": "Наличные",
	"Loans and Advances (Assets)": "Займы и авансы выданные",
	"Employee Advances": "Подотчёт сотрудников",
	"Prepaid Expenses": "Расходы будущих периодов",
	"Securities and Deposits": "Залоги и депозиты",
	"Earnest Money": "Залоговые суммы",
	"Short-term Investments": "Краткосрочные вложения",
	"Stock Assets": "Товарно-материальные запасы",
	"Stock In Hand": "Склад",
	"Stock Delivered But Not Billed": "Отгружено, не выставлено",
	"Tax Assets": "Налоговые активы",
	"Fixed Assets": "Основные средства",
	"Accumulated Depreciation": "Накопленная амортизация",
	"Buildings": "Здания",
	"Capital Equipment": "Оборудование",
	"CWIP Account": "Незавершённое строительство",
	"Electronic Equipment": "Электроника",
	"Furniture and Fixtures": "Мебель и инвентарь",
	"Office Equipment": "Офисная техника",
	"Plants and Machineries": "Машины и спецтехника",
	"Software": "Программы",
	"Investments": "Инвестиции",
	"Temporary Accounts": "Временные счета",
	"Temporary Opening": "Ввод остатков",
	"Source of Funds (Liabilities)": "Обязательства",
	"Current Liabilities": "Краткосрочные обязательства",
	"Accounts Payable": "Кредиторская задолженность",
	"Creditors": "Кредиторы (поставщики)",
	"Payroll Payable": "Зарплата к выплате",
	"Accrued Expenses": "Начисленные расходы",
	"Customer Advances": "Авансы полученные от клиентов",
	"Duties and Taxes": "Налоги",
	"VAT": "НДС",
	"Loans (Liabilities)": "Кредиты и займы",
	"Bank Overdraft Account": "Овердрафт",
	"Secured Loans": "Обеспеченные кредиты",
	"Unsecured Loans": "Займы",
	"Short-term Provisions": "Краткосрочные резервы",
	"Stock Liabilities": "Обязательства по складу",
	"Asset Received But Not Billed": "ОС получено, счёт не выставлен",
	"Stock Received But Not Billed": "Товар получен, счёт не выставлен",
	"Non-Current Liabilities": "Долгосрочные обязательства",
	"Employee Benefits Obligation": "Обязательства перед сотрудниками",
	"Long-term Provisions": "Долгосрочные резервы",
	"Equity": "Капитал",
	"Capital Stock": "Уставный капитал",
	"Dividends Paid": "Выплаченные дивиденды",
	"Opening Balance Equity": "Капитал (ввод остатков)",
	"Retained Earnings": "Нераспределённая прибыль",
	"Revaluation Surplus": "Переоценка",
	"Income": "Доходы",
	"Direct Income": "Выручка",
	"Sales": "Выручка от реализации продукции",
	"Service": "Выручка от реализации услуг",
	"Indirect Income": "Прочие доходы",
	"Exchange Gain": "Курсовая разница (доход)",
	"Interest Income": "Процентный доход",
	"Interest on Fixed Deposits": "Проценты по депозитам",
	"Expenses": "Расходы",
	"Direct Expenses": "Прямые расходы",
	"Indirect Expenses": "Косвенные расходы",
	"Cost of Goods Sold": "Себестоимость продукции",
	"Stock Expenses": "Складские расходы",
	"Stock Adjustment": "Инвентаризация склада",
	"Expenses Included In Valuation": "Расходы в себестоимости",
	"Expenses Included In Asset Valuation": "Расходы в стоимости ОС",
	"Administrative Expenses": "Административные расходы",
	"Commission on Sales": "Комиссия с продаж",
	"Depreciation": "Амортизация",
	"Entertainment Expenses": "Представительские расходы",
	"Freight and Forwarding Charges": "Транспортные расходы",
	"Legal Expenses": "Юридические расходы",
	"Marketing Expenses": "Маркетинг",
	"Miscellaneous Expenses": "Прочие расходы",
	"Office Maintenance Expenses": "Содержание офиса",
	"Office Rent": "Аренда офиса",
	"Postal Expenses": "Почтовые расходы",
	"Print and Stationery": "Канцелярия",
	"Round Off": "Округление",
	"Salary": "Зарплата",
	"Sales Expenses": "Коммерческие расходы",
	"Telephone Expenses": "Связь",
	"Travel Expenses": "Командировки",
	"Utility Expenses": "Коммунальные расходы",
	"Write Off": "Списание",
	"Exchange Gain/Loss": "Курсовая разница",
	"Gain/Loss on Asset Disposal": "Результат от выбытия ОС",
	"Impairment": "Обесценение",
	"Tax Expense": "Налог на прибыль",
	"Interest Expense": "Проценты по кредитам",
}


def ru(account_name: str) -> str:
	return ACCOUNT_RU.get(account_name, account_name)


def get_months(from_date, to_date) -> list[frappe._dict]:
	"""Davr ichidagi oylar: key ("2026-09"), fieldname ("m_2026_09"), label ("09.2026"), start, end."""
	start, end = get_first_day(getdate(from_date)), getdate(to_date)
	if start > end:
		frappe.throw(_("Boshlanish sanasi tugash sanasidan katta"))
	months = []
	while start <= end:
		months.append(
			frappe._dict(
				key=start.strftime("%Y-%m"),
				fieldname=start.strftime("m_%Y_%m"),
				label=start.strftime("%m.%Y"),
				start=start,
				end=min(getdate(get_last_day(start)), end),
			)
		)
		start = getdate(add_months(start, 1))
		if len(months) > MAX_OY:
			frappe.throw(_("Davr juda katta: ko'pi bilan {0} oy tanlang").format(MAX_OY))
	return months


def month_columns(months, first_label, total=True, width=140):
	cols = [{"fieldname": "label", "label": first_label, "fieldtype": "Data", "width": 320}]
	for m in months:
		cols.append({"fieldname": m.fieldname, "label": m.label, "fieldtype": "Currency", "width": width})
	if total:
		cols.append({"fieldname": "total", "label": _("Жами"), "fieldtype": "Currency", "width": width + 10})
	return cols


def get_accounts(company: str, root_types) -> list[frappe._dict]:
	return frappe.get_all(
		"Account",
		filters={"company": company, "root_type": ["in", list(root_types)]},
		fields=["name", "account_name", "parent_account", "is_group", "root_type", "account_type", "lft", "rgt"],
		order_by="lft",
	)


def get_monthly_gl(company: str, root_types, to_date, from_date=None, skip_closing=False) -> dict:
	"""{account: {"2026-09": debit - credit}}: hisob va oy bo'yicha GL yig'indisi (firma valyutasida)."""
	cond = ""
	if from_date:
		cond += " and gle.posting_date >= %(from_date)s"
	if skip_closing:
		# Yil yopish provodkasi daromad/xarajatni nolga tushiradi - P&L da hisobga olinmaydi
		cond += " and gle.voucher_type != 'Period Closing Voucher'"
	rows = frappe.db.sql(
		f"""select gle.account, date_format(gle.posting_date, '%%Y-%%m') ym, sum(gle.debit) - sum(gle.credit) net
		from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
		where gle.company = %(company)s and gle.is_cancelled = 0 and gle.posting_date <= %(to_date)s
			and acc.root_type in %(root_types)s {cond}
		group by gle.account, ym""",
		{"company": company, "to_date": to_date, "from_date": from_date, "root_types": list(root_types)},
		as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.account, {})[r.ym] = flt(r.net)
	return out


def tree_rows(accounts, values: dict, months, sign=1, skip=None, cumulative=False, base_indent=0) -> tuple[list, dict]:
	"""Hisoblar daraxtini hisobot qatorlariga aylantiradi (guruh = bolalari yig'indisi, nol qatorlar tashlanadi).

	values     - get_monthly_gl natijasi
	sign       - 1: debet - kredit (aktiv, xarajat), -1: kredit - debet (passiv, daromad)
	skip       - qatorga kirmaydigan hisoblar (masalan tan narx hisoblari alohida ko'rsatiladi)
	cumulative - True: oy oxiridagi qoldiq (balans), False: oy ichidagi aylanma (P&L)
	Qaytaradi: (qatorlar, {fieldname: jami})
	"""
	skip = skip or set()
	keys = [m.key for m in months]

	def leaf(account):
		per_month = values.get(account, {})
		if cumulative:
			return [sign * sum(v for ym, v in per_month.items() if ym <= k) for k in keys]
		return [sign * flt(per_month.get(k)) for k in keys]

	by_name = {a.name: a for a in accounts}
	totals = {a.name: [0.0] * len(keys) for a in accounts}
	for a in accounts:
		if a.is_group or a.name in skip:
			continue
		vals = leaf(a.name)
		node = a
		while node:  # o'zi va barcha ota guruhlariga qo'shiladi
			totals[node.name] = [x + y for x, y in zip(totals[node.name], vals)]
			node = by_name.get(node.parent_account)

	depth = {}
	rows = []
	grand = [0.0] * len(keys)
	for a in accounts:  # lft bo'yicha tartiblangan
		depth[a.name] = depth.get(a.parent_account, -1) + 1 if a.parent_account in by_name else 0
		vals = totals[a.name]
		if a.name in skip or not any(abs(v) >= 0.005 for v in vals):
			continue
		if depth[a.name] == 0:
			grand = [x + y for x, y in zip(grand, vals)]
		row = {
			"label": ru(a.account_name),
			"account": a.name,
			"indent": base_indent + depth[a.name],
			"is_group": a.is_group,
			"bold": 1 if a.is_group and depth[a.name] <= 1 else 0,
		}
		row.update(month_values(months, vals, total=not cumulative))
		rows.append(row)
	return rows, month_values(months, grand, total=not cumulative)


def month_values(months, vals, total=True) -> dict:
	out = {m.fieldname: flt(v, 2) for m, v in zip(months, vals)}
	if total:
		out["total"] = flt(sum(vals), 2)
	return out


def line(label, months, vals, total=True, **extra) -> dict:
	"""Yig'ma qator (masalan "Итого", "Чистая прибыль")."""
	if isinstance(vals, dict):
		vals = [flt(vals.get(m.fieldname)) for m in months]
	return {"label": label, **month_values(months, vals, total=total), **extra}


def percent_line(label, months, numerator: dict, denominator: dict) -> dict:
	"""Rentabellik qatori: numerator / denominator * 100 (har oy va jami uchun)."""
	row = {"label": label, "is_percent": 1, "indent": 1}
	for f in [m.fieldname for m in months] + ["total"]:
		d = flt(denominator.get(f))
		row[f] = flt(flt(numerator.get(f)) / d * 100, 1) if d else None
	return row
