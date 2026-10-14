# Foyda Zarar (P&L, "Отчет о прибылях и убытках"): oyma-oy - Google Sheets'dagi «P&L» varag'i qatorlari bilan:
#   Выручка (продукции / услуг) -> Себестоимость -> Маржинальная прибыль (+ рентабельность)
#   -> Прочие доходы -> Общепроизводственные расходы (statya bo'yicha) -> Валовая прибыль
#   -> Административные расходы -> Коммерческие расходы -> Операционная прибыль -> Налог на прибыль -> Чистая прибыль
# Manba: GL Entry (daromad va xarajat hisoblari). Xarajat statyasi (modda) qaysi blokka tushishi - Kassa Kategoriya
# «Оборот» (taqsimot) bo'yicha: Произв -> Общепроизводственные, Прибыль va boshqalar -> Административные.
# Jadvaldagi P&L naqd + hisoblash aralash edi (kassa xarajatlari kontragentsiz + Начисление «Закуп услуga»);
# ERPNext'da xarajat hujjat (Nachislenie / Purchase Invoice / Kassa) kiritilgan kunda hisoblarga tushadi, kontragentga
# to'lov esa xarajat emas (qarzni yopish) - natija bir xil. Jadvaldagi cheklov (qat'iy qatorlar diapazoni) yo'q:
# davrdagi BARCHA yozuvlar hisobga olinadi. «Чистая прибыль» Balans'dagi foyda bilan har doim mos.
# «P&L Разбитый» - xarajatlar 1-tur -> 2-tur -> statya daraxti bilan (alohida hisobot).

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import prepare
from carieer.carieer.report.moliya import (
	COGS_TYPES,
	INVENTAR_TYPES,
	PROFIT_TAX,
	TAQSIM_OS,
	TAQSIM_PROIZV,
	card,
	category_info,
	drop_empty_months,
	finalize,
	get_accounts,
	get_monthly_gl,
	get_months,
	income_kind,
	line,
	money,
	month_columns,
	net_by_account,
	note_box,
	percent_line,
	ru,
	vsum,
)


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	data, totals = get_data(filters, months, with_totals=True)
	data = finalize(data)
	columns, shown = drop_empty_months(month_columns(months, _("Модда")), data, months)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	return columns, data, get_message(totals, shown, currency), None, get_summary(totals, currency)


def get_summary(t, currency):
	"""Tepadagi kartochkalar: daromad -> tannarx -> yalpi foyda -> xarajatlar -> sof foyda."""
	income, net = t["income"], t["net"]
	margin_pct = f" ({flt(t['margin'] / income * 100, 1)}%)" if income else ""
	net_pct = f" ({flt(net / income * 100, 1)}%)" if income else ""
	return [
		card(_("Daromad (Выручка)"), income, "Blue", currency),
		card(_("Tannarx (Себестоимость)"), t["cogs"], "Orange", currency),
		card(_("Yalpi foyda") + margin_pct, t["margin"], "Green" if t["margin"] >= 0 else "Red", currency),
		card(_("Xarajatlar (Расходы)"), t["expenses"], "Orange", currency),
		card(_("Sof foyda") + net_pct if net >= 0 else _("Zarar") + net_pct, net, "Green" if net >= 0 else "Red", currency),
	]


def get_message(t, months, currency):
	"""Oddiy tilda: davr natijasi va eng katta xarajatlar."""
	period = months[0].label if len(months) == 1 else f"{months[0].label} – {months[-1].label}"
	net = t["net"]
	if not (t["income"] or t["cogs"] or t["expenses"] or t["other_income"]):
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
		_("Xarajatlar (ish haqi, yoqilg'i, ijara ...): <b>{0}</b>").format(money(t["expenses"], currency)),
	]
	if t["other_income"]:
		lines.append(_("Boshqa daromadlar: <b>{0}</b>").format(money(t["other_income"], currency)))
	top = sorted(t["expense_items"].items(), key=lambda p: -p[1])[:3]
	if top:
		lines.append(
			_("Eng katta xarajatlar: {0}").format(
				", ".join(f"{frappe.utils.escape_html(k)} — {money(v, currency)}" for k, v in top if v > 0)
			)
		)
	if t["income"] and not t["cogs"]:
		lines.append(
			_("Diqqat: tannarx 0 - sotilgan tovarning kirim narxi (tan narxi) kiritilmagan, foyda haqiqiydan katta ko'rinadi.")
		)
	color = "var(--green-600, #2f9e44)" if net >= 0 else "var(--red-600, #e03636)"
	return note_box(frappe.utils.escape_html(headline), lines, color)


def classify(accounts, by_name, values, months, company):
	"""Hisoblarni jadvaldagi bloklarga ajratadi. Qaytaradi: dict (har biri [oylar] yoki {statya: [oylar]})."""
	n = len(months)
	zero = [0.0] * n
	income = net_by_account([a for a in accounts if a.root_type == "Income"], values, months, -1)
	expense = net_by_account([a for a in accounts if a.root_type == "Expense"], values, months, 1)
	cat = category_info(company)

	out = {"product": zero, "service": zero, "other_income": {}, "cogs": zero, "inv": zero, "tax": zero}
	out.update(proizv={}, admin={}, invest={})
	for a in accounts:
		if a.is_group:
			continue
		if a.root_type == "Income":
			kind = income_kind(a, by_name)
			if kind == "other":
				if a.account_name != "Прочие доходы" and not any(abs(v) >= 0.005 for v in income[a.name]):
					continue
				label = ru(a.account_name)
				out["other_income"][label] = vsum(out["other_income"].get(label, zero), income[a.name], n=n)
			else:
				out[kind] = vsum(out[kind], income[a.name], n=n)
			continue
		vals = expense[a.name]
		if a.account_type in COGS_TYPES:
			out["cogs"] = vsum(out["cogs"], vals, n=n)
		elif a.account_type in INVENTAR_TYPES:
			out["inv"] = vsum(out["inv"], vals, n=n)
		elif a.account_name == PROFIT_TAX:
			out["tax"] = vsum(out["tax"], vals, n=n)
		else:
			info = cat.get(a.account_name)
			if not info and not any(abs(v) >= 0.005 for v in vals):
				continue  # kategoriyasiz (ERPNext standart) hisob - faqat harakat bo'lsa qatorda chiqadi
			taqsim = info.taqsimot if info else ""
			block = "proizv" if taqsim == TAQSIM_PROIZV else "invest" if taqsim == TAQSIM_OS else "admin"
			label = ru(a.account_name)
			out[block][label] = vsum(out[block].get(label, zero), vals, n=n)
	# jadvaldagi kabi: kategoriyasi bor statyalar qiymati nol bo'lsa ham qatorda turadi
	expense_names = {a.account_name for a in accounts if a.root_type == "Expense" and not a.is_group}
	for name, k in cat.items():
		if k.turi == "Kirim" or name not in expense_names or not k.taqsimot:
			continue
		block = "proizv" if k.taqsimot == TAQSIM_PROIZV else "invest" if k.taqsimot == TAQSIM_OS else "admin"
		if block != "invest":
			out[block].setdefault(ru(name), list(zero))
	return out


def get_data(filters, months, with_totals=False):
	company = filters.company
	n = len(months)
	zero = [0.0] * n
	accounts = get_accounts(company, ("Income", "Expense"))
	by_name = {a.name: a for a in accounts}
	values = get_monthly_gl(
		company, ("Income", "Expense"), filters.to_date, from_date=months[0].start, skip_closing=True
	)
	c = classify(accounts, by_name, values, months, company)

	revenue = vsum(c["product"], c["service"], n=n)
	margin = [r - k for r, k in zip(revenue, c["cogs"])]
	other_income = vsum(*c["other_income"].values(), zero, n=n)
	proizv_total = vsum(c["inv"], *c["proizv"].values(), n=n)
	gross = [m - p + o for m, p, o in zip(margin, proizv_total, other_income)]
	admin_total = vsum(*c["admin"].values(), zero, n=n)
	invest_total = vsum(*c["invest"].values(), zero, n=n)
	commercial_total = zero
	operating = [g - a - k for g, a, k in zip(gross, admin_total, commercial_total)]
	net = [o - t for o, t in zip(operating, c["tax"])]

	rev_row = line(_("Выручка"), months, revenue, bold=1)
	margin_row = line(_("Маржинальная прибыль"), months, margin, bold=1, total_row=1)
	gross_row = line(_("Валовая прибыль"), months, gross, bold=1, total_row=1)
	operating_row = line(_("Операционная прибыль"), months, operating, bold=1, total_row=1)
	net_row = line(_("Чистая прибыль"), months, net, bold=1, total_row=1)

	def block(title, rows_by_label, total_label, total_vals, first=None):
		out = [{"label": title, "is_header": 1, "bold": 1}]
		if first:
			out.append(line(first[0], months, first[1], indent=1))
		out += [
			line(label, months, vals, indent=1)
			for label, vals in sorted(rows_by_label.items(), key=lambda p: p[0].lower())
		]
		out.append(line(total_label, months, total_vals, bold=1, total_row=1))
		return out

	data = [
		rev_row,
		line(_("Выручка от реализации продукции"), months, c["product"], indent=1),
		line(_("Выручка от реализации услуг"), months, c["service"], indent=1),
		line(_("Себестоимость"), months, c["cogs"], bold=1),
		line(_("Сырьевая себестоимость реализованной продукции"), months, c["cogs"], indent=1),
		margin_row,
		percent_line(_("Рентабельность по маржинальному доходу, %"), months, margin_row, rev_row),
		line(_("Прочие доходы"), months, other_income, bold=1),
		*[
			line(label, months, vals, indent=1)
			for label, vals in sorted(c["other_income"].items(), key=lambda p: p[0].lower())
		],
		*block(
			_("Общепроизводственные расходы"),
			c["proizv"],
			_("Итого общепроизводственные расходы"),
			proizv_total,
			first=(_("Убыток (расходы выше нормы)"), c["inv"]),
		),
		gross_row,
		percent_line(_("Рентабельность, %"), months, gross_row, rev_row),
		{"label": _("Операционные расходы"), "is_header": 1, "bold": 1},
		*block(_("Административные расходы"), c["admin"], _("Итого административные расходы"), admin_total),
	]
	data += [
		{"label": _("Коммерческие расходы"), "is_header": 1, "bold": 1},
		line(_("Итого коммерческие расходы"), months, commercial_total, bold=1, total_row=1),
		operating_row,
		percent_line(_("Рентабельность по операционной прибыли, %"), months, operating_row, rev_row),
		line(_("Налог на прибыль"), months, c["tax"], bold=1),
		net_row,
		percent_line(_("Рентабельность по чистой прибыли, %"), months, net_row, rev_row),
	]
	if any(abs(v) >= 0.005 for v in invest_total):
		# «На ОС»: asosiy vositaga kapital qo'yilma - foyda-zarar emas, Баланс'dagi «Оборудование» qatoriga qo'shiladi
		data += block(
			_("Капитальные вложения (На ОС): в Баланс, прибыль не уменьшают"),
			c["invest"],
			_("Итого капитальные вложения"),
			invest_total,
		)
	if not with_totals:
		return data

	expense_items = {}
	for part in (c["proizv"], c["admin"]):
		for label, vals in part.items():
			expense_items[label] = expense_items.get(label, 0) + sum(vals)
	income_total = flt(sum(revenue))
	expenses = flt(sum(proizv_total) + sum(admin_total) + sum(c["tax"]))
	return data, {
		"income": income_total,
		"cogs": flt(sum(c["cogs"])),
		"margin": flt(sum(margin)),
		"other_income": flt(sum(other_income)),
		"expenses": expenses,
		"net": flt(sum(net)),
		"expense_items": expense_items,
	}
