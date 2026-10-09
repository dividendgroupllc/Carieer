# Balans ("Баланс"): har oy oxiridagi holat, oyma-oy ustunlar.
# Google Sheets'dagi "Баланс" varag'i tuzilishida (hisoblar rejasi daraxti emas, boshqaruv moddalari):
#   Активы:  Внеоборотные активы (Основные средства)
#            Оборотные активы: Запасы, Денежные средства (har kassa alohida),
#                              Дебиторская задолженность (клиентов, выданные авансы, сотрудников, второй фирмы, налог),
#                              Прочие активы
#   Пассивы: Капитал (уставный капитал, ввод остатков, дивиденды; накопленная прибыль: прошлых / текущего периода)
#            Обязательства: Кредиты и займы, Кредиторская задолженность (поставщикам, сотрудникам, налоги,
#                           полученные авансы от клиентов, второй фирме), Прочие обязательства
#   Итого, Разница (doim 0 bo'lishi kerak).
# Mijoz qarzi va mijozdan olingan avans (ta'minotchi qarzi va unga berilgan avans) kontragent bo'yicha ajratiladi:
# bitta Debtors hisobida qarzdor mijozlar aktivga, oldindan to'laganlar passivga tushadi.
# Ikkinchi firmamiz bilan hisob-kitob alohida qator: mijoz va ta'minotchi tomoni netto.
# «Ввод остатков» (Temporary Opening - boshlang'ich qoldiqlar qarshi hisobi) kapitalda ko'rsatiladi, aktivda minus emas.
# Yil yopilmagan bo'lsa ham to'g'ri: foyda daromad/xarajat hisoblari qoldig'idan hisoblanadi.

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
	ru,
)

ICHKI_FIELD = {"Customer": "is_internal_customer", "Supplier": "is_internal_supplier"}

DEBITORKA = [
	("debitor", "Задолженность клиентов"),
	("avans_berilgan", "Выданные авансы"),
	("podotchet", "Задолженность сотрудников (подотчёт)"),
	("ichki_aktiv", "Задолженность второй фирмы"),
	("tax_asset", "Налог"),
]
KREDITORKA = [
	("kreditor", "Задолженность перед поставщиками"),
	("xodim_qarz", "Задолженность перед сотрудниками"),
	("tax", "Задолженность по налогам и сборам"),
	("avans_olingan", "Полученные авансы от клиентов"),
	("ichki_passiv", "Задолженность перед второй фирмой"),
]
# Shu moddalarda har bir hisob alohida qator bo'lib ham chiqadi (kassalar, omborlar, OS, kapital ...)
DETAIL = {"cash", "stock", "fixed", "other_asset", "loans", "other_liability", "equity"}
OPENING_LABEL = "Ввод остатков (начальный капитал)"


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	return month_columns(months, _("Статья"), total=False, width=150), finalize(get_data(filters, months))


def get_data(filters, months):
	company = filters.company
	keys = [m.key for m in months]
	n = len(keys)

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

	def under(account, group_name):
		"""Hisob shu nomli guruh ichidami (masalan «Loans (Liabilities)»)."""
		node = by_name.get(account.parent_account)
		while node:
			if node.account_name == group_name:
				return True
			node = by_name.get(node.parent_account)
		return False

	def cumulative(per_month):
		return [sum(v for ym, v in per_month.items() if ym <= k) for k in keys]

	buckets = {}  # modda -> {"total": [oylar], "rows": {qator: [oylar]}}

	def add(bucket, vals, label=None):
		b = buckets.setdefault(bucket, {"total": [0.0] * n, "rows": {}})
		b["total"] = [x + y for x, y in zip(b["total"], vals)]
		if label and bucket in DETAIL:
			b["rows"][label] = [x + y for x, y in zip(b["rows"].get(label, [0.0] * n), vals)]

	# 1. Kontragent hisoblari (Debtors, Creditors, Employee Advances): har kontragent qoldig'i ishorasiga qarab
	for kind, per_month in party_balances(company, party_accounts, filters.to_date):
		bal = cumulative(per_month)  # debet - kredit
		plus, minus = [max(v, 0) for v in bal], [max(-v, 0) for v in bal]
		if kind == "internal":
			add("ichki_aktiv", plus)
			add("ichki_passiv", minus)
		elif kind == "Asset Receivable":  # mijozlar
			add("debitor", plus)
			add("avans_olingan", minus)
		elif kind == "Asset Payable":  # xodimlar (подотчёт)
			add("podotchet", plus)
			add("xodim_qarz", minus)
		else:  # ta'minotchilar
			add("avans_berilgan", plus)
			add("kreditor", minus)

	# 2. Qolgan hisoblar: hisob turi bo'yicha moddaga
	for a in accounts:
		if a.name in party_accounts or a.name not in values:
			continue
		bal = cumulative(values[a.name])
		label = kassa_nomi.get(a.name) or ru(a.account_name)
		if a.root_type == "Asset":
			if a.account_type in ("Cash", "Bank"):
				add("cash", bal, label)
			elif a.account_type == "Stock":
				add("stock", bal, label)
			elif a.account_type in ("Fixed Asset", "Accumulated Depreciation", "Capital Work in Progress"):
				add("fixed", bal, label)
			elif a.account_type == "Temporary":
				# boshlang'ich qoldiqlar (Инвентаризация «Opening Stock», ochilish provodkasi) qarshi hisobi = kapital
				add("equity", [-v for v in bal], _(OPENING_LABEL))
			elif a.account_type == "Tax":
				add("tax_asset", bal)
			else:
				add("other_asset", bal, label)
		elif a.root_type == "Liability":
			neg = [-v for v in bal]
			if a.account_name == "Customer Advances":
				add("avans_olingan", neg)
			elif a.account_type == "Tax":
				add("tax", neg)
			elif a.account_name == "Payroll Payable":
				add("xodim_qarz", neg)
			elif under(a, "Loans (Liabilities)") or under(a, "Non-Current Liabilities"):
				add("loans", neg, label)
			else:
				add("other_liability", neg, label)
		else:
			add("equity", [-v for v in bal], label)

	# 3. Foyda: daromad - xarajat (kredit - debet). Oy ichidagi va shu oygacha to'plangan.
	pl = {}
	for per_month in get_monthly_gl(company, ("Income", "Expense"), filters.to_date).values():
		for ym, net in per_month.items():
			pl[ym] = pl.get(ym, 0) - flt(net)
	current = [flt(pl.get(k)) for k in keys]
	profit = [sum(v for ym, v in pl.items() if ym <= k) for k in keys]
	previous = [p - c for p, c in zip(profit, current)]

	def total_of(names):
		return [sum(buckets[b]["total"][i] for b in names if b in buckets) for i in range(n)]

	def nonzero(vals):
		return any(abs(v) >= 0.005 for v in vals)

	def detail(bucket, label, indent):
		"""Modda qatori va ostida har bir hisob (kassa, ombor, OS ...)."""
		b = buckets.get(bucket)
		if not b or not (nonzero(b["total"]) or any(nonzero(v) for v in b["rows"].values())):
			return []
		out = [line(_(label), months, b["total"], total=False, bold=1, indent=indent)]
		out += [
			line(row_label, months, vals, total=False, indent=indent + 1)
			for row_label, vals in sorted(b["rows"].items())
			if nonzero(vals)
		]
		return out

	def group(label, items, indent):
		"""Yig'ma qator (masalan «Дебиторская задолженность») va ostida moddalar."""
		vals = total_of([b for b, _label in items])
		if not nonzero(vals):
			return []
		out = [line(_(label), months, vals, total=False, bold=1, indent=indent)]
		for bucket, item_label in items:
			b = buckets.get(bucket)
			if b and nonzero(b["total"]):
				out.append(line(_(item_label), months, b["total"], total=False, indent=indent + 1))
		return out

	def header(label):
		return {"label": label, "is_header": 1, "bold": 1}

	def total(label, vals, **extra):
		return line(label, months, vals, total=False, bold=1, **extra)

	vneoborot = total_of(["fixed"])
	oborot = total_of(["stock", "cash", *[b for b, _label in DEBITORKA], "other_asset"])
	aktiv_total = [x + y for x, y in zip(vneoborot, oborot)]
	kapital_total = [k + p for k, p in zip(total_of(["equity"]), profit)]
	majburiyat_total = total_of(["loans", *[b for b, _label in KREDITORKA], "other_liability"])
	passiv_total = [k + m for k, m in zip(kapital_total, majburiyat_total)]
	diff = [flt(a - p, 2) for a, p in zip(aktiv_total, passiv_total)]

	data = [header(_("АКТИВЫ"))]
	if nonzero(vneoborot):
		data += [total(_("Внеоборотные активы"), vneoborot, indent=1), *detail("fixed", "Основные средства", 2)]
	data += [
		total(_("Оборотные активы"), oborot, indent=1),
		*detail("stock", "Запасы", 2),
		*detail("cash", "Денежные средства", 2),
		*group("Дебиторская задолженность", DEBITORKA, 2),
		*detail("other_asset", "Прочие активы", 2),
		total(_("Итого активы"), aktiv_total, total_row=1),
		header(_("ПАССИВЫ")),
		total(_("Капитал"), kapital_total, indent=1),
	]
	equity = buckets.get("equity", {"rows": {}})
	data += [
		line(row_label, months, vals, total=False, indent=2)
		for row_label, vals in sorted(equity["rows"].items())
		if nonzero(vals)
	]
	data += [
		line(_("Накопленная прибыль/убыток"), months, profit, total=False, bold=1, indent=2),
		line(_("прошлых периодов"), months, previous, total=False, indent=3),
		line(_("текущего периода (месяц)"), months, current, total=False, indent=3),
		total(_("Обязательства"), majburiyat_total, indent=1),
		*detail("loans", "Кредиты и займы", 2),
		*group("Кредиторская задолженность", KREDITORKA, 2),
		*detail("other_liability", "Прочие обязательства", 2),
		total(_("Итого пассивы"), passiv_total, total_row=1),
		{**total(_("Разница (должна быть 0)"), diff), "is_check": 1},
	]
	return data


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
