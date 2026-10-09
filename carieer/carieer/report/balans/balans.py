# Balans ("Баланс"): har oy oxiridagi holat, oyma-oy ustunlar - Google Sheets'dagi «Баланс» varag'i bilan BIR XIL
# qatorlar (nol bo'lsa ham qator turadi, katak bo'sh ko'rinadi):
#   АКТИВЫ
#     Внеоборотные активы -> Основные средства: Оборудование, Офисная техника, Прочее
#     Оборотные активы    -> Запасы: Продукция
#                            Денежные средства: har bir kassa, Разница в перемещении
#                            Дебиторская задолженность: клиентов, выданные авансы, сотрудников, второй фирмы,
#                                                       прочих дебиторов, налог
#                            Прочие активы: Расходы будущих периодов, Прочее
#     Итого активы
#   ПАССИВЫ
#     Капитал: Уставный капитал, Ввод остатков, Накопленная прибыль (прошлых / текущего периода), Дивиденды, Инвестиция
#     Обязательства -> Долгосрочные: Кредиты банков, Займы, Задолженность по лизингу
#                      Краткосрочные: Кредиты банков, Займы
#                      Кредиторская задолженность: поставщикам, сотрудникам, налоги, авансы клиентов, второй фирме,
#                                                  зарплата собственника, прочие
#     Итого пассивы, Разница (doim 0)
# Kontragent qoldig'i ishorasiga qarab: qarzdor mijoz - aktivda, oldindan to'lagan mijoz - passivda (avans).
# «Ввод остатков» (Temporary Opening - boshlang'ich qoldiqlar qarshi hisobi) kapitalda ko'rsatiladi.
# Yil yopilmagan bo'lsa ham to'g'ri: foyda daromad/xarajat hisoblari qoldig'idan hisoblanadi.

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
	ru,
)

ICHKI_FIELD = {"Customer": "is_internal_customer", "Supplier": "is_internal_supplier"}
# ERPNext asosiy vositalar hisoblari -> Sheets qatorlari
OS_GURUH = {
	"Capital Equipment": "Оборудование",
	"Plants and Machineries": "Оборудование",
	"Office Equipment": "Офисная техника",
	"Electronic Equipment": "Офисная техника",
	"Furniture and Fixtures": "Офисная техника",
}


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	data, totals = get_data(filters, months)
	data = finalize(data)
	columns, shown = drop_empty_months(month_columns(months, _("Статья"), total=False, width=150), data, months)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	return columns, data, get_message(totals, shown, currency), None, get_summary(totals, currency)


def get_summary(t, currency):
	return [
		card(_("Активы (bor narsamiz)"), t["aktiv"], "Blue", currency),
		card(_("Капитал (o'zimizniki)"), t["kapital"], "Green", currency),
		card(_("Обязательства (qarzlarimiz)"), t["majburiyat"], "Orange", currency),
		card(_("Разница (0 bo'lishi kerak)"), t["diff"], "Green" if abs(t["diff"]) < 1 else "Red", currency),
	]


def get_message(t, months, currency):
	date = months[-1].end.strftime("%d.%m.%Y") if months else ""
	lines = [
		_("Bor narsamiz (aktivlar) = o'zimizniki (kapital) + qarzlarimiz (majburiyatlar): <b>{0}</b> = <b>{1}</b> + <b>{2}</b>").format(
			money(t["aktiv"], currency), money(t["kapital"], currency), money(t["majburiyat"], currency)
		),
		_("Pul: <b>{0}</b>, ombordagi tovar: <b>{1}</b>, bizga qarzlar: <b>{2}</b>").format(
			money(t["cash"], currency), money(t["stock"], currency), money(t["debitorka"], currency)
		),
	]
	if abs(t["diff"]) >= 1:
		lines.append(_("⚠ Разница {0}: buxgalteriyada muvozanat buzilgan - administratorga xabar bering").format(money(t["diff"], currency)))
	return note_box(_("{0} holatiga balans").format(date), lines, "var(--text-color)")


def get_data(filters, months):
	company = filters.company
	keys = [m.key for m in months]
	n = len(keys)
	zero = [0.0] * n

	all_accounts = get_accounts(company, ("Asset", "Liability", "Equity"))
	by_name = {a.name: a for a in all_accounts}
	accounts = [a for a in all_accounts if not a.is_group]
	values = get_monthly_gl(company, ("Asset", "Liability", "Equity"), filters.to_date)
	party_accounts = {a.name for a in accounts if a.account_type in ("Receivable", "Payable")}
	# bitta hisobga eski (o'chirilgan) kassa ham ulangan bo'lishi mumkin («Cash») - faol kassa nomi ustun turadi
	kassa_nomi = dict(
		frappe.db.sql(
			"""select a.default_account, a.parent from `tabMode of Payment Account` a
			join `tabMode of Payment` m on m.name = a.parent where a.company = %s order by m.enabled""",
			company,
		)
	)
	kassalar = frappe.get_all(
		"Mode of Payment Account",
		filters={"company": company, "parent": ["in", frappe.get_all("Mode of Payment", {"enabled": 1}, pluck="name")]},
		pluck="default_account",
	)

	def under(account, group_name):
		node = by_name.get(account.parent_account)
		while node:
			if node.account_name == group_name:
				return True
			node = by_name.get(node.parent_account)
		return False

	def cumulative(per_month):
		return [sum(v for ym, v in per_month.items() if ym <= k) for k in keys]

	b = {}  # qator kaliti -> [oylar]
	cash_rows = {kassa_nomi.get(acc, acc): list(zero) for acc in kassalar}  # har bir faol kassa - nol bo'lsa ham

	def add(key, vals):
		b[key] = [x + y for x, y in zip(b.get(key, zero), vals)]

	# 1. kontragentlar: har biri alohida (bir mijozning qarzi boshqasining avansini yopmasin)
	for kind, per_month in party_balances(company, party_accounts, filters.to_date):
		bal = cumulative(per_month)  # debet - kredit
		plus, minus = [max(v, 0) for v in bal], [max(-v, 0) for v in bal]
		if kind == "internal":
			add("ichki_aktiv", plus)
			add("ichki_passiv", minus)
		elif kind == "Asset Receivable":
			add("debitor", plus)
			add("avans_olingan", minus)
		elif kind == "Asset Payable":  # xodimlar
			add("podotchet", plus)
			add("xodim_qarz", minus)
		else:  # ta'minotchilar
			add("avans_berilgan", plus)
			add("kreditor", minus)

	# 2. qolgan hisoblar
	for a in accounts:
		if a.name in party_accounts or a.name not in values:
			continue
		bal = cumulative(values[a.name])
		neg = [-v for v in bal]
		if a.root_type == "Asset":
			if a.account_type in ("Cash", "Bank"):
				label = kassa_nomi.get(a.name) or ru(a.account_name)
				cash_rows[label] = [x + y for x, y in zip(cash_rows.get(label, zero), bal)]
			elif a.account_type == "Stock":
				add("stock", bal)
			elif a.account_type in ("Fixed Asset", "Accumulated Depreciation", "Capital Work in Progress"):
				add("os:" + OS_GURUH.get(a.account_name, "Прочее"), bal)
			elif a.account_type == "Temporary":
				add("opening", neg)  # boshlang'ich qoldiqlar qarshi hisobi = kapital
			elif a.account_type == "Tax":
				add("tax_asset", bal)
			elif a.account_name == "Prepaid Expenses":
				add("prepaid", bal)
			elif a.account_type == "Receivable" or under(a, "Accounts Receivable") or under(a, "Loans and Advances (Assets)"):
				add("prochie_debitor", bal)
			else:
				add("other_asset", bal)
		elif a.root_type == "Liability":
			if a.account_name == "Customer Advances":
				add("avans_olingan", neg)
			elif a.account_type == "Tax":
				add("tax", neg)
			elif a.account_name == "Payroll Payable":
				add("xodim_qarz", neg)
			elif under(a, "Non-Current Liabilities"):
				add("long:" + ("Кредиты банков" if "Secured" in a.account_name or "Bank" in a.account_name else "Займы"), neg)
			elif under(a, "Loans (Liabilities)"):
				add("short:" + ("Кредиты банков" if "Secured" in a.account_name or "Bank" in a.account_name else "Займы"), neg)
			else:
				add("other_liability", neg)
		else:
			if a.account_name == "Capital Stock":
				add("ustav", neg)
			elif a.account_name == "Dividends Paid":
				add("dividend", neg)
			elif a.account_name == "Opening Balance Equity":
				add("opening", neg)
			else:
				add("investitsiya", neg)

	# 3. foyda: daromad - xarajat
	pl = {}
	for per_month in get_monthly_gl(company, ("Income", "Expense"), filters.to_date).values():
		for ym, net in per_month.items():
			pl[ym] = pl.get(ym, 0) - flt(net)
	current = [flt(pl.get(k)) for k in keys]
	profit = [sum(v for ym, v in pl.items() if ym <= k) for k in keys]
	previous = [p - c for p, c in zip(profit, current)]

	def g(key):
		return b.get(key, zero)

	def s(*vals_list):
		return [sum(v[i] for v in vals_list) for i in range(n)]

	def row(label, vals, indent, bold=0, **extra):
		return line(_(label), months, vals, total=False, indent=indent, bold=bold, **extra)

	os_rows = [(lbl, g("os:" + lbl)) for lbl in ("Оборудование", "Офисная техника", "Прочее")]
	os_total = s(*[v for _l, v in os_rows])
	cash_total = s(*cash_rows.values()) if cash_rows else zero
	peremeshenie = zero  # yo'ldagi pul (kassadan kassaga o'tkazma bir kunda yopiladi)
	debitorka = [
		("Задолженность клиентов", g("debitor")),
		("Выданные авансы (поставщикам)", g("avans_berilgan")),
		("Задолженность сотрудников (подотчёт)", g("podotchet")),
		("Задолженность второй фирмы", g("ichki_aktiv")),
		("Долг прочих дебиторов", g("prochie_debitor")),
		("Налог", g("tax_asset")),
	]
	debitorka_total = s(*[v for _l, v in debitorka])
	prochie = [("Расходы будущих периодов", g("prepaid")), ("Прочее", g("other_asset"))]
	prochie_total = s(*[v for _l, v in prochie])
	oborot = s(g("stock"), cash_total, debitorka_total, prochie_total)
	aktiv = s(os_total, oborot)

	kapital_rows = [
		("Уставный капитал", g("ustav")),
		("Ввод остатков (начальный капитал)", g("opening")),
	]
	dividend, investitsiya = g("dividend"), g("investitsiya")
	kapital = s(*[v for _l, v in kapital_rows], profit, dividend, investitsiya)
	long_rows = [(lbl, g("long:" + lbl)) for lbl in ("Кредиты банков", "Займы")] + [("Задолженность по лизингу", zero)]
	short_rows = [(lbl, g("short:" + lbl)) for lbl in ("Кредиты банков", "Займы")]
	kreditorka = [
		("Задолженность перед поставщиками", g("kreditor")),
		("Задолженность перед сотрудниками", g("xodim_qarz")),
		("Задолженность по налогам и сборам", g("tax")),
		("Полученные авансы от клиентов", g("avans_olingan")),
		("Задолженность перед второй фирмой", g("ichki_passiv")),
		("Зарплата собственника/партнеров", zero),
		("Прочие обязательства", g("other_liability")),
	]
	long_total = s(*[v for _l, v in long_rows])
	short_total = s(*[v for _l, v in short_rows])
	kreditorka_total = s(*[v for _l, v in kreditorka])
	majburiyat = s(long_total, short_total, kreditorka_total)
	passiv = s(kapital, majburiyat)
	diff = [flt(a - p, 2) for a, p in zip(aktiv, passiv)]

	data = [
		{"label": _("АКТИВЫ"), "is_header": 1, "bold": 1},
		row("Внеоборотные активы", os_total, 1, 1),
		row("Основные средства", os_total, 2, 1),
		*[row(lbl, v, 3) for lbl, v in os_rows],
		row("Оборотные активы", oborot, 1, 1),
		row("Запасы", g("stock"), 2, 1),
		row("Продукция (склад)", g("stock"), 3),
		row("Денежные средства", cash_total, 2, 1),
		*[row(lbl, v, 3) for lbl, v in sorted(cash_rows.items())],
		row("Разница в перемещении", peremeshenie, 3),
		row("Дебиторская задолженность", debitorka_total, 2, 1),
		*[row(lbl, v, 3) for lbl, v in debitorka],
		row("Прочие активы", prochie_total, 2, 1),
		*[row(lbl, v, 3) for lbl, v in prochie],
		row("Итого активы", aktiv, 0, 1, total_row=1),
		{"label": _("ПАССИВЫ"), "is_header": 1, "bold": 1},
		row("Капитал", kapital, 1, 1),
		*[row(lbl, v, 2) for lbl, v in kapital_rows],
		row("Накопленная прибыль/убыток", profit, 2, 1),
		row("— прошлых периодов", previous, 3),
		row("— текущего периода (месяц)", current, 3),
		row("Дивиденды", dividend, 2),
		row("Инвестиция", investitsiya, 2),
		row("Обязательства", majburiyat, 1, 1),
		row("Долгосрочные", long_total, 2, 1),
		*[row(lbl, v, 3) for lbl, v in long_rows],
		row("Краткосрочные", short_total, 2, 1),
		*[row(lbl, v, 3) for lbl, v in short_rows],
		row("Кредиторская задолженность", kreditorka_total, 2, 1),
		*[row(lbl, v, 3) for lbl, v in kreditorka],
		row("Итого пассивы", passiv, 0, 1, total_row=1),
		{**row("Разница (должна быть 0)", diff, 0, 1), "is_check": 1},
	]
	last = -1
	totals = {
		"aktiv": aktiv[last] if n else 0,
		"kapital": kapital[last] if n else 0,
		"majburiyat": majburiyat[last] if n else 0,
		"diff": diff[last] if n else 0,
		"cash": cash_total[last] if n else 0,
		"stock": g("stock")[last] if n else 0,
		"debitorka": debitorka_total[last] if n else 0,
	}
	return data, totals


def party_balances(company, accounts, to_date) -> list[tuple[str, dict]]:
	"""[(tur, {"2026-09": debet - kredit})], har bir kontragent alohida (bir mijozning qarzi boshqasining avansini
	yopmasligi uchun). tur: "Asset Receivable" (mijoz), "Asset Payable" (xodim), "Liability Payable" (ta'minotchi),
	"internal" (ikkinchi firmamiz: mijoz va ta'minotchi tomoni bitta netto qoldiq)."""
	if not accounts:
		return []
	rows = frappe.db.sql(
		"""select acc.root_type, acc.account_type, gle.party_type, gle.party,
			date_format(gle.posting_date, '%%Y-%%m') ym, sum(gle.debit) - sum(gle.credit) net
		from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
		where gle.company = %(company)s and gle.is_cancelled = 0 and gle.posting_date <= %(to_date)s
			and gle.account in %(accounts)s
		group by acc.root_type, acc.account_type, gle.party_type, gle.party, ym""",
		{"company": company, "to_date": to_date, "accounts": list(accounts)},
		as_dict=True,
	)
	ichki = {}
	groups = {}
	for r in rows:
		party = (r.party_type or "", r.party or "")
		if party not in ichki:
			field = ICHKI_FIELD.get(r.party_type)
			firma = field and frappe.db.get_value(
				r.party_type, r.party, ["represents_company", field], as_dict=True
			)
			ichki[party] = firma.represents_company if firma and firma.get(field) else None
		if ichki[party]:
			key = ("internal", ichki[party])
		elif r.party_type == "Employee":
			# Kassa'da xodim -> Creditors hisobiga yoziladi (Party Type Employee = Payable), lekin bu ta'minotchi emas:
			# musbat qoldiq - подотчёт, manfiy - xodimga qarz
			key = ("Asset Payable", party)
		else:
			kind = f"{r.root_type} {r.account_type}" if r.root_type == "Asset" else "Liability Payable"
			key = (kind, party)
		per_month = groups.setdefault(key, {})
		per_month[r.ym] = per_month.get(r.ym, 0) + flt(r.net)
	return [(kind, per_month) for (kind, _party), per_month in groups.items()]
