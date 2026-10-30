# Pereraschet ("Перерасчет"): oyma-oy qayta hisob - hisobdagi qoldiq bilan haqiqiy (fakt) qoldiq orasidagi farq.
# Google Sheets'dagi «Перерасчет» varag'i qatorlari:
#   Курс                       - oy oxiridagi USD kursi (Currency Exchange)
#   Перерасчет контрагентов    - valyutadagi kontragent qoldig'i oy oxiri kursida - hisobdagi (so'mdagi) qoldig'i
#   Курсовая разница (деньги)  - valyutadagi kassa / bank qoldig'i oy oxiri kursida - hisobdagi qoldig'i
#   Сырьёвая разница (склад)   - ombordagi tovar qoldig'i (Stock Ledger) - balansdagi «Склад» hisoblari (GL)
# Har bir blokda: «Факт» va «По учёту» - oy oxiridagi qoldiq, blok sarlavhasi - shu oy ichidagi farq o'zgarishi
# (jadvaldagi kabi: oldingi oylar farqi ayirib tashlanadi), «Жами» - davr bo'yicha jami.
# Firma valyutasidagi (so'm) hisoblar qayta baholanmaydi: jadvaldagi $ hisobidan farqli, ERPNext kitoblari so'mda.
# Kurs farqi Kassa / Sotuv'da allaqachon provodka qilingan bo'lsa, u «По учёту» ga kirgan - bu yerda qolgani
# hali provodka qilinmagan (realizatsiya qilinmagan) farq.

import frappe
from frappe import _
from frappe.utils import add_days, flt

from carieer.carieer.report.common import prepare
from carieer.carieer.report.moliya import card, finalize, get_months, month_columns, note_box

CASH_TYPES = ("Cash", "Bank")


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	ctx = frappe._dict(
		company=filters.company,
		currency=currency,
		months=months,
		prev_date=add_days(months[0].start, -1),
		rates={},
	)

	data = [rate_row(ctx)]
	party_block = fx_block(ctx, _("Перерасчет контрагентов"), party=True)
	cash_block = fx_block(ctx, _("Курсовая разница (деньги)"), party=False)
	stock_block = stock_rows(ctx)
	for block in (party_block, cash_block, stock_block):
		data += block.rows

	itogo = [sum(v) for v in zip(party_block.change, cash_block.change, stock_block.change, strict=True)]
	data.append(change_line(_("Итого перерасчет"), months, itogo, bold=1))

	columns = month_columns(months, _("Статья"), total=True, width=140)
	totals = {
		"party": sum(party_block.change),
		"cash": sum(cash_block.change),
		"stock": sum(stock_block.change),
	}
	return columns, finalize(data), get_message(totals, currency), None, get_summary(totals, currency)


# ------------------------------------------------------------------ kurs
def get_rate(ctx, from_currency: str, date) -> float:
	"""Sana bo'yicha kurs (from_currency -> firma valyutasi). Topilmasa 0."""
	from erpnext.setup.utils import get_exchange_rate

	key = (from_currency, date)
	if key not in ctx.rates:
		ctx.rates[key] = flt(get_exchange_rate(from_currency, ctx.currency, date)) if from_currency else 0
	return ctx.rates[key]


def rate_row(ctx) -> dict:
	row = {"label": _("Курс USD (на конец месяца)"), "indent": 0}
	if ctx.currency != "USD":
		for m in ctx.months:
			row[m.fieldname] = get_rate(ctx, "USD", m.end)
	return row


# ------------------------------------------------------------------ valyutadagi qoldiqlar
def points(by_ym: dict, months) -> list[float]:
	"""Oy bo'yicha harakat -> qoldiq: [davr boshidan oldin, 1-oy oxiri, 2-oy oxiri, ...]."""
	first = months[0].key
	out = [sum(v for ym, v in by_ym.items() if ym < first)]
	for m in months:
		out.append(sum(v for ym, v in by_ym.items() if ym <= m.key))
	return out


def fx_block(ctx, title: str, party: bool) -> frappe._dict:
	"""Firma valyutasidan boshqa valyutadagi hisoblar: qoldiq (hisob valyutasida) oy oxiri kursida - hisobdagi qoldiq."""
	party_cond = "ifnull(gle.party, '') != ''" if party else "ifnull(gle.party, '') = ''"
	rows = frappe.db.sql(
		f"""select gle.account, gle.party_type, gle.party, gle.account_currency,
			date_format(gle.posting_date, '%%Y-%%m') ym,
			sum(gle.debit_in_account_currency) - sum(gle.credit_in_account_currency) net_ac,
			sum(gle.debit) - sum(gle.credit) net
		from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
		where gle.company = %(company)s and gle.is_cancelled = 0 and gle.posting_date <= %(to_date)s
			and gle.account_currency != %(currency)s and {party_cond}
			{"" if party else "and acc.account_type in %(cash_types)s"}
		group by gle.account, gle.party_type, gle.party, gle.account_currency, ym""",
		{
			"company": ctx.company,
			"to_date": ctx.months[-1].end,
			"currency": ctx.currency,
			"cash_types": CASH_TYPES,
		},
		as_dict=True,
	)
	groups = {}
	for r in rows:
		key = (r.account, r.party_type or "", r.party or "", r.account_currency)
		g = groups.setdefault(key, {"ac": {}, "book": {}})
		g["ac"][r.ym] = g["ac"].get(r.ym, 0) + flt(r.net_ac)
		g["book"][r.ym] = g["book"].get(r.ym, 0) + flt(r.net)

	dates = [ctx.prev_date] + [m.end for m in ctx.months]
	n = len(ctx.months)
	fact_total, book_total, change_total = [0.0] * n, [0.0] * n, [0.0] * n
	children = []
	for (account, _party_type, party_name, account_currency), g in sorted(groups.items()):
		ac = points(g["ac"], ctx.months)
		book = points(g["book"], ctx.months)
		fact = [a * get_rate(ctx, account_currency, d) for a, d in zip(ac, dates, strict=True)]
		diff = [f - b for f, b in zip(fact, book, strict=True)]
		change = [diff[i + 1] - diff[i] for i in range(n)]
		fact_total = [x + y for x, y in zip(fact_total, fact[1:], strict=True)]
		book_total = [x + y for x, y in zip(book_total, book[1:], strict=True)]
		change_total = [x + y for x, y in zip(change_total, change, strict=True)]
		if any(abs(v) >= 0.005 for v in change + fact[1:]):
			label = f"{party_name or account} ({account_currency})"
			children.append(change_line(label, ctx.months, change, indent=2))

	out = [change_line(title, ctx.months, change_total, bold=1)]
	out.append(balance_line(_("Факт: остаток по курсу на конец месяца"), ctx.months, fact_total))
	out.append(balance_line(_("По учёту"), ctx.months, book_total))
	out += children
	return frappe._dict(rows=out, change=change_total)


# ------------------------------------------------------------------ ombor
def stock_rows(ctx) -> frappe._dict:
	"""Ombordagi tovar qoldig'i (Stock Ledger) va balansdagi «Склад» (Stock turidagi hisoblar)."""
	values = {"company": ctx.company, "to_date": ctx.months[-1].end}
	sle = dict(
		frappe.db.sql(
			"""select date_format(posting_date, '%%Y-%%m'), sum(stock_value_difference)
			from `tabStock Ledger Entry`
			where company = %(company)s and is_cancelled = 0 and posting_date <= %(to_date)s
			group by date_format(posting_date, '%%Y-%%m')""",
			values,
		)
	)
	gl = dict(
		frappe.db.sql(
			"""select date_format(gle.posting_date, '%%Y-%%m'), sum(gle.debit) - sum(gle.credit)
			from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
			where gle.company = %(company)s and gle.is_cancelled = 0 and gle.posting_date <= %(to_date)s
				and acc.account_type = 'Stock'
			group by date_format(gle.posting_date, '%%Y-%%m')""",
			values,
		)
	)
	fact = points({k: flt(v) for k, v in sle.items()}, ctx.months)
	book = points({k: flt(v) for k, v in gl.items()}, ctx.months)
	diff = [f - b for f, b in zip(fact, book, strict=True)]
	change = [diff[i + 1] - diff[i] for i in range(len(ctx.months))]
	rows = [
		change_line(_("Сырьёвая разница (склад)"), ctx.months, change, bold=1),
		balance_line(_("Факт: товарный остаток (склад)"), ctx.months, fact[1:]),
		balance_line(_("По учёту (баланс, счета «Склад»)"), ctx.months, book[1:]),
	]
	return frappe._dict(rows=rows, change=change)


# ------------------------------------------------------------------ qatorlar
def change_line(label, months, vals, indent=0, **extra) -> dict:
	"""Oy ichidagi farq o'zgarishi + «Жами»."""
	row = {"label": label, "indent": indent, **extra}
	for m, v in zip(months, vals, strict=True):
		row[m.fieldname] = flt(v, 2)
	row["total"] = flt(sum(vals), 2)
	return row


def balance_line(label, months, vals) -> dict:
	"""Oy oxiridagi qoldiq (jami ustuni bo'sh)."""
	row = {"label": label, "indent": 1}
	for m, v in zip(months, vals, strict=True):
		row[m.fieldname] = flt(v, 2)
	return row


def get_message(totals, currency):
	from carieer.carieer.report.moliya import money

	jami = sum(totals.values())
	if all(abs(v) < 0.5 for v in totals.values()):
		return note_box(
			_("Farq yo'q: hisobdagi qoldiqlar fakt bilan bir xil"),
			[_("Valyutadagi qoldiqlar va ombor qoldig'i balans bilan mos.")],
			"var(--green-600)",
		)
	return note_box(
		_("Davr bo'yicha qayta hisob: {0}").format(money(jami, currency)),
		[
			_("Kontragentlar: {0}").format(money(totals["party"], currency)),
			_("Pul (valyutadagi kassa / bank): {0}").format(money(totals["cash"], currency)),
			_("Ombor (Stock Ledger - balans): {0}").format(money(totals["stock"], currency)),
			_(
				"Musbat - fakt qoldiq hisobdagidan ko'p (kurs foydasi / ortiqcha tovar), manfiy - kam. "
				"Valyuta farqini yopish uchun ERPNext'ning «Exchange Rate Revaluation» hujjatidan foydalaning."
			),
		],
	)


def get_summary(totals, currency):
	def ind(v):
		return "Green" if v > 0.5 else "Red" if v < -0.5 else "Gray"

	return [
		card(_("Перерасчет контрагентов"), totals["party"], ind(totals["party"]), currency),
		card(_("Курсовая разница (деньги)"), totals["cash"], ind(totals["cash"]), currency),
		card(_("Сырьёвая разница (склад)"), totals["stock"], ind(totals["stock"]), currency),
	]
