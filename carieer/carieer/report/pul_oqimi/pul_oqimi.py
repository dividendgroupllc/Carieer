# Pul Oqimi ("Cash Flow" / "Движение денежных средств"): oyma-oy, kategoriyalar kesimida.
# Google Sheets'dagi "Cash Flow" varag'i tartibida:
#   Денег на начало месяца
#   Поступления: от клиентов, прочие доходы (kategoriya bo'yicha), учредители ...
#   Выплаты: поставщикам, сотрудникам, keyin xarajatlar jadvaldagi guruhlar bo'yicha
#            (Административный / Операционный / Производственный / Инвестиционные / Финансовые -> kategoriya)
#   Перемещение между кассами (faqat bitta kassa tanlanganda ma'noli, aks holda 0)
#   Изменение за месяц, Денег на конец месяца
# Manba DDS hisoboti bilan bir xil (kassa hisoblaridagi GL yozuvlar), shuning uchun ikkalasi doim mos keladi.
# Xarajat guruhi: Kassa hujjatidagi kategoriya -> Kassa Kategoriya.guruh_1; kategoriya bo'lmasa xarajat moddasining
# hisoblar rejasidagi ota guruhi (install.make_moddalar jadvaldagi daraxtni yaratgan).
# Bitta kassa tanlansa - o'sha kassa valyutasida, aks holda firma valyutasida.

import frappe
from frappe import _
from frappe.utils import flt, getdate

from carieer.carieer.report.common import prepare
from carieer.carieer.report.dds.dds import get_data as get_dds_data
from carieer.carieer.report.moliya import (
	card,
	drop_empty_months,
	finalize,
	get_months,
	line,
	money,
	month_columns,
	note_box,
	ru,
)
from carieer.utils import get_kassa_info
from carieer.install import XARAJAT_KATEGORIYALARI

# Jadvaldagi "Категория 1 типа" tartibi
GURUH_TARTIBI = list(dict.fromkeys(g1 for _k, g1, _g2, _t in XARAJAT_KATEGORIYALARI))
BOSHQA_XARAJAT = "Прочие расходы"

KIRIM_NOMI = {
	"customer": "Поступления от клиентов",
	"supplier": "Возвраты от поставщиков",
	"employee": "Возврат подотчёта сотрудников",
	"shareholder": "Взносы учредителей",
	"dividend": "Взносы учредителей",
}
CHIQIM_NOMI = {
	"customer": "Возвраты клиентам",
	"supplier": "Оплата поставщикам",
	"employee": "Выплаты сотрудникам",
	"shareholder": "Выплаты учредителям / дивиденды",
	"dividend": "Выплаты учредителям / дивиденды",
}
PEREMESHENIE = "Перемещение между кассами"


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	data, t = get_data(filters, months, with_totals=True)
	data = finalize(data)
	columns, shown = drop_empty_months(month_columns(months, _("Статья")), data, months)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	if filters.get("mode_of_payment"):
		currency = get_kassa_info(filters.mode_of_payment, filters.company).currency or currency
	return columns, data, get_message(t, shown, currency, filters), None, get_summary(t, currency)


def get_summary(t, currency):
	"""Pul qayerdan keldi va qayerga ketdi: boshida -> kirdi -> chiqdi -> oxirida."""
	return [
		card(_("Davr boshida kassada"), t["opening"], "Blue", currency),
		card(_("Kirdi (Поступления)"), t["kirim"], "Green", currency),
		card(_("Chiqdi (Выплаты)"), t["chiqim"], "Red", currency),
		card(_("Davr oxirida kassada"), t["closing"], "Blue" if t["closing"] >= 0 else "Red", currency),
	]


def get_message(t, months, currency, filters):
	esc = frappe.utils.escape_html
	period = months[0].label if len(months) == 1 else f"{months[0].label} – {months[-1].label}"
	change = t["closing"] - t["opening"]
	where = esc(filters.mode_of_payment) if filters.get("mode_of_payment") else _("kassalarda")
	headline = (
		_("{0}: {1} pul {2} ko'paydi").format(period, where, money(change, currency))
		if change >= 0
		else _("{0}: {1} pul {2} kamaydi").format(period, where, money(-change, currency))
	)

	def top(items):
		pairs = sorted(((k, sum(v)) for k, v in items.items()), key=lambda p: -p[1])
		return ", ".join(f"{esc(k)} — {money(v, currency)}" for k, v in pairs[:3] if v)

	lines = [
		_("Boshida: <b>{0}</b> → kirdi <b>{1}</b> → chiqdi <b>{2}</b> → oxirida <b>{3}</b>").format(
			money(t["opening"], currency), money(t["kirim"], currency), money(t["chiqim"], currency), money(t["closing"], currency)
		),
	]
	if t["kirim_items"]:
		lines.append(_("Pul qayerdan keldi: {0}").format(top(t["kirim_items"])))
	if t["chiqim_items"]:
		lines.append(_("Pul qayerga ketdi: {0}").format(top(t["chiqim_items"])))
	if t["transfer"] and filters.get("mode_of_payment"):
		lines.append(_("Boshqa kassalar bilan o'tkazma: {0}").format(money(t["transfer"], currency)))
	negative = [m.label for m in months if flt(t["ends_by_month"].get(m.key)) < -0.005]
	if negative:
		lines.append(
			_("⚠ Minus qoldiq ({0}): kassadan unda yo'q pul chiqarilgan - kirim kiritilmagan bo'lishi mumkin").format(
				", ".join(negative)
			)
		)
	color = "var(--green-600, #2f9e44)" if change >= 0 else "var(--red-600, #e03636)"
	return note_box(headline, lines, color)


def get_data(filters, months, with_totals=False):
	dds_filters = frappe._dict(
		company=filters.company,
		from_date=months[0].start,
		to_date=getdate(filters.to_date),
		mode_of_payment=filters.get("mode_of_payment"),
	)
	rows, _expense, opening, _closing = get_dds_data(dds_filters)
	guruh_of = expense_groups(filters.company)

	index = {m.key: i for i, m in enumerate(months)}
	n = len(months)
	kirim = {}  # qator -> [oylar]
	chiqim = {}  # guruh -> {qator -> [oylar]}
	transfer = [0.0] * n

	def put(target, label, i, value):
		target.setdefault(label, [0.0] * n)[i] += value

	for d in rows:
		i = index.get(getdate(d["posting_date"]).strftime("%Y-%m"))
		if i is None:
			continue
		k, c = flt(d["kirim"]), flt(d["chiqim"])
		cat = d["category"]
		if cat == "transfer":
			transfer[i] += k - c
			continue
		if cat == "internal":  # o'zimizning ikkinchi firmamiz bilan pul (Firmalararo To'lov)
			if k:
				put(kirim, d["dds_kategoriya"], i, k)
			if c:
				put(chiqim.setdefault("", {}), d["dds_kategoriya"], i, c)
			continue
		if k:
			if d.get("kategoriya"):
				label = d["kategoriya"]
			elif cat in KIRIM_NOMI:
				label = KIRIM_NOMI[cat]
			else:
				label = ru(d["description"])
			put(kirim, _(label), i, k)
		if c:
			if cat in CHIQIM_NOMI and not d.get("kategoriya"):
				put(chiqim.setdefault("", {}), _(CHIQIM_NOMI[cat]), i, c)
				continue
			label = d.get("kategoriya") or ru(d["description"])
			guruh = guruh_of.get(d.get("kategoriya")) or guruh_of.get(d["description"]) or BOSHQA_XARAJAT
			put(chiqim.setdefault(guruh, {}), label, i, c)

	kirim_total = [sum(v[i] for v in kirim.values()) for i in range(n)]
	chiqim_total = [sum(v[i] for g in chiqim.values() for v in g.values()) for i in range(n)]
	change = [k - c + t for k, c, t in zip(kirim_total, chiqim_total, transfer)]
	start, end, balance = [], [], flt(opening)
	for i in range(n):
		start.append(balance)
		balance += change[i]
		end.append(balance)

	def balance_line(label, vals):
		# qoldiq qatorlarida "Жами" ustuni ma'nosiz (oylar qoldig'ini qo'shib bo'lmaydi)
		return {**line(label, months, vals, total=False), "bold": 1, "total_row": 1}

	def neg(vals):
		return [-v for v in vals]

	data = [balance_line(_("Денег на начало месяца"), start)]
	data.append(line(_("Поступления"), months, kirim_total, bold=1, is_header_line=1))
	data += [line(label, months, vals, indent=1) for label, vals in sorted(kirim.items())]

	data.append(line(_("Выплаты"), months, neg(chiqim_total), bold=1, is_header_line=1))
	for label, vals in sorted(chiqim.get("", {}).items()):
		data.append(line(label, months, neg(vals), indent=1))
	order = GURUH_TARTIBI + sorted(g for g in chiqim if g and g not in GURUH_TARTIBI and g != BOSHQA_XARAJAT)
	for guruh in [*order, BOSHQA_XARAJAT]:
		items = chiqim.get(guruh)
		if not items:
			continue
		group_total = [sum(v[i] for v in items.values()) for i in range(n)]
		data.append(line(_(guruh), months, neg(group_total), bold=1, indent=1))
		data += [line(label, months, neg(vals), indent=2) for label, vals in sorted(items.items())]

	if any(abs(v) >= 0.005 for v in transfer):
		data.append(line(_(PEREMESHENIE), months, transfer, bold=1))
	data.append(line(_("Изменение за месяц"), months, change, bold=1))
	data.append(balance_line(_("Денег на конец месяца"), end))
	if not with_totals:
		return data
	chiqim_items = {}
	for guruh, items in chiqim.items():
		for label, vals in items.items():
			chiqim_items[label] = [a + b for a, b in zip(chiqim_items.get(label, [0.0] * n), vals)]
	ends = dict(zip([m.key for m in months], end))
	return data, {
		"opening": flt(start[0]) if start else flt(opening),
		"kirim": flt(sum(kirim_total)),
		"chiqim": flt(sum(chiqim_total)),
		"transfer": flt(sum(transfer)),
		"closing": flt(end[-1]) if end else flt(opening),
		"kirim_items": kirim,
		"chiqim_items": chiqim_items,
		"ends_by_month": ends,
	}


def expense_groups(company) -> dict:
	"""{kategoriya yoki xarajat moddasi nomi: "Категория 1 типа"}.
	Kassa Kategoriya.guruh_1 dan, keyin hisoblar rejasidan (modda -> 2-tur -> 1-tur guruhi)."""
	out = {}
	for k in frappe.get_all("Kassa Kategoriya", fields=["name", "guruh_1", "hisob_nomi"]):
		if k.guruh_1:
			out[k.name] = k.guruh_1
			if k.hisob_nomi:
				out[k.hisob_nomi] = k.guruh_1
	guruhlar = set(GURUH_TARTIBI)
	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "root_type": "Expense"},
		fields=["name", "account_name", "parent_account", "is_group"],
	)
	by_name = {a.name: a for a in accounts}
	for a in accounts:
		if a.is_group or a.account_name in out:
			continue
		node = by_name.get(a.parent_account)
		while node:
			if node.account_name in guruhlar:
				out[a.account_name] = node.account_name
				break
			node = by_name.get(node.parent_account)
	return out
