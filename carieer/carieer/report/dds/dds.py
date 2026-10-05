# DDS (движение денежных средств) - jadvaldagi «ДДС» varag'i kabi:
#   qatorlar - kategoriyalar (Kassa'dagi «Kategoriya»; bo'lmasa Клиент / Поставщик / Сотрудник / Перемещение ...),
#   ustunlar - har bir valyuta bo'yicha kirim va chiqim (сўм, $),
#   tepada - har bir valyuta bo'yicha boshlang'ich qoldiq, davr oboroti, yakuniy qoldiq.
# «Batafsil» belgilansa - har bir pul harakati alohida qatorda.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import blank_zeros, bold, prepare, resolve_party
from carieer.utils import get_internal_company

CATEGORY_MAP = {
	"Покупатели": "customer",
	"Поставщики": "supplier",
	"Сотрудники": "employee",
	"Учредители": "shareholder",
	"Дивиденды": "dividend",
	"Расходы": "expense",
	"Прочие доходы": "income",
	"Перемещения": "transfer",
	"Firmalararo": "internal",
	"Прочие": "other",
}
CATEGORY_LABELS = {v: k for k, v in CATEGORY_MAP.items()}
# Kassa'da kategoriya ko'rsatilmagan pul harakati qaysi qatorga tushadi (jadvaldagi nomlar)
CATEGORY_DEFAULT = {
	"customer": "Клиент",
	"supplier": "Поставщик",
	"employee": "Сотрудник",
	"shareholder": "Дивиденд",
	"dividend": "Дивиденд",
	"transfer": "Перемещение",
	"other": "Прочие",
}
PARTY_CATEGORY = {
	"Customer": "customer",
	"Supplier": "supplier",
	"Employee": "employee",
	"Shareholder": "shareholder",
}
PARTY_NAME_FIELD = {
	"Customer": "customer_name",
	"Supplier": "supplier_name",
	"Employee": "employee_name",
	"Shareholder": "title",
}


def execute(filters=None):
	filters = prepare(filters, period="month")
	resolve_party(filters)
	data, _expense, _opening, _closing = get_data(filters)
	if filters.get("kategoriya"):
		data = [d for d in data if d["dds_kategoriya"] == filters.kategoriya]
	balances = get_balances(filters)
	message = get_summary_html(balances, filters)
	if filters.get("batafsil"):
		return get_detail_columns(), data, message
	return summary(data, filters, balances)


def summary(data, filters, balances):
	"""Kategoriya x valyuta: kirim / chiqim."""
	company_currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	currencies = sorted(
		{d["acc_currency"] for d in data} | set(balances), key=lambda c: (c != company_currency, c)
	)
	columns = [{"fieldname": "kategoriya", "label": _("Категория"), "fieldtype": "Data", "width": 260}]
	for cur in currencies:
		f = frappe.scrub(cur)
		columns += [
			{
				"fieldname": f"kirim_{f}",
				"label": _("Кирим ({0})").format(cur),
				"fieldtype": "Currency",
				"options": cur,
				"width": 150,
			},
			{
				"fieldname": f"chiqim_{f}",
				"label": _("Чиқим ({0})").format(cur),
				"fieldtype": "Currency",
				"options": cur,
				"width": 150,
			},
		]
	groups = {}
	for d in data:
		g = groups.setdefault(d["dds_kategoriya"], {"kategoriya": d["dds_kategoriya"]})
		f = frappe.scrub(d["acc_currency"])
		g[f"kirim_{f}"] = flt(g.get(f"kirim_{f}")) + d["kirim_acc"]
		g[f"chiqim_{f}"] = flt(g.get(f"chiqim_{f}")) + d["chiqim_acc"]
	rows = sorted(groups.values(), key=lambda g: g["kategoriya"])
	total = {"kategoriya": bold(_("Жами оборот"))}
	for cur in currencies:
		f = frappe.scrub(cur)
		total[f"kirim_{f}"] = sum(flt(r.get(f"kirim_{f}")) for r in rows)
		total[f"chiqim_{f}"] = sum(flt(r.get(f"chiqim_{f}")) for r in rows)
	start = {"kategoriya": bold(_("Остаток на начало периода"))}
	end = {"kategoriya": bold(_("Остаток на конец периода"))}
	for cur, b in balances.items():
		f = frappe.scrub(cur)
		start[f"kirim_{f}"] = b["opening"]
		end[f"kirim_{f}"] = b["closing"]
	fields = [c["fieldname"] for c in columns[1:]]
	return columns, blank_zeros([start, *rows, total, end], fields), get_summary_html(balances, filters)


def get_balances(filters) -> dict:
	"""Har bir valyuta bo'yicha: boshlang'ich qoldiq, kirim, chiqim, yakuniy qoldiq (kassa valyutasida)."""
	accounts = get_cash_accounts(filters)
	if not accounts:
		return {}
	out = {}
	for r in frappe.db.sql(
		"""select account_currency cur,
			sum(if(posting_date < %(from_date)s, debit_in_account_currency - credit_in_account_currency, 0)) opening,
			sum(if(posting_date >= %(from_date)s, debit_in_account_currency, 0)) kirim,
			sum(if(posting_date >= %(from_date)s, credit_in_account_currency, 0)) chiqim
		from `tabGL Entry`
		where account in %(acc)s and posting_date <= %(to_date)s and is_cancelled = 0
		group by account_currency""",
		{"acc": accounts, "from_date": filters.from_date, "to_date": filters.to_date},
		as_dict=True,
	):
		out[r.cur] = {
			"opening": flt(r.opening, 2),
			"kirim": flt(r.kirim, 2),
			"chiqim": flt(r.chiqim, 2),
			"closing": flt(flt(r.opening) + flt(r.kirim) - flt(r.chiqim), 2),
		}
	return out


def get_kassa_balances(filters) -> list[frappe._dict]:
	"""Har bir kassa (hisob) bo'yicha: boshlang'ich qoldiq, kirim, chiqim, yakuniy qoldiq (kassa valyutasida)."""
	accounts = get_cash_accounts(filters)
	if not accounts:
		return []
	names = {}
	for m in frappe.db.sql(
		"""select a.default_account, a.parent, m.enabled from `tabMode of Payment Account` a
		join `tabMode of Payment` m on m.name = a.parent where a.company = %s order by m.enabled desc, a.parent""",
		filters.company,
		as_dict=True,
	):
		names.setdefault(m.default_account, m.parent)
	rows = frappe.db.sql(
		"""select account, account_currency cur,
			sum(if(posting_date < %(from_date)s, debit_in_account_currency - credit_in_account_currency, 0)) opening,
			sum(if(posting_date >= %(from_date)s, debit_in_account_currency, 0)) kirim,
			sum(if(posting_date >= %(from_date)s, credit_in_account_currency, 0)) chiqim
		from `tabGL Entry`
		where account in %(acc)s and posting_date <= %(to_date)s and is_cancelled = 0
		group by account, account_currency""",
		{"acc": accounts, "from_date": filters.from_date, "to_date": filters.to_date},
		as_dict=True,
	)
	by_account = {r.account: r for r in rows}
	out = []
	for acc in accounts:
		r = by_account.get(acc) or frappe._dict(
			cur=frappe.get_cached_value("Account", acc, "account_currency"), opening=0, kirim=0, chiqim=0
		)
		out.append(
			frappe._dict(
				kassa=names.get(acc, acc),
				cur=r.cur,
				opening=flt(r.opening, 2),
				kirim=flt(r.kirim, 2),
				chiqim=flt(r.chiqim, 2),
				closing=flt(flt(r.opening) + flt(r.kirim) - flt(r.chiqim), 2),
			)
		)
	return out


def get_summary_html(balances, filters=None) -> str:
	"""Tepadagi jadval: har bir kassa alohida (kassa nazorati), keyin valyuta bo'yicha jami.
	Minus qoldiq qizil - kassada yo'q pul chiqarilgan."""
	if not balances:
		return ""
	esc = frappe.utils.escape_html

	def fmt(v):
		return f"{flt(v):,.2f}".replace(",", " ")

	td = "padding:6px 10px;border:1px solid var(--border-color);text-align:right"
	red = "color:var(--red-600, #e03636)"

	def tr(label, b, strong=False):
		closing_style = red if flt(b["closing"]) < -0.005 else ""
		warn = " ⚠" if flt(b["closing"]) < -0.005 else ""
		cells = "".join(f"<td style='{td}'>{fmt(b[k])}</td>" for k in ("opening", "kirim", "chiqim"))
		label = f"<b>{label}</b>" if strong else label
		return (
			f"<tr><td style='{td};text-align:left'>{label}</td>{cells}"
			f"<td style='{td};{closing_style}'><b>{fmt(b['closing'])}{warn}</b></td></tr>"
		)

	kassalar = get_kassa_balances(filters) if filters else []
	body = ""
	for cur, b in balances.items():
		items = [k for k in kassalar if k.cur == cur]
		for k in items:
			body += tr(f"{esc(k.kassa)} <span style='color:var(--text-muted)'>({esc(cur)})</span>", k)
		if len(items) != 1:
			body += tr(esc(_("Jami {0}").format(cur)), b, strong=True)
	head = "".join(
		f"<th style='{td}'>{h}</th>"
		for h in (_("Касса"), _("Остаток на начало"), _("Кирим"), _("Чиқим"), _("Остаток на конец"))
	)
	note = ""
	if any(flt(k.closing) < -0.005 for k in kassalar):
		note = (
			f"<div style='{red};margin:-8px 0 12px;font-size:13px'>"
			+ esc(_("⚠ Minus qoldiq: kassadan unda yo'q pul chiqarilgan. Kirimi kiritilmagan yoki xato kassa tanlangan."))
			+ "</div>"
		)
	return f"<table style='border-collapse:collapse;margin:8px 0 14px'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>{note}"


def get_detail_columns():
	return [
		{"fieldname": "posting_date", "label": _("Сана"), "fieldtype": "Date", "width": 95},
		{
			"fieldname": "account",
			"label": _("Касса"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 160,
		},
		{"fieldname": "direction", "label": _("Кирим/Чиқим"), "fieldtype": "Data", "width": 95},
		{"fieldname": "description", "label": _("Контрагент / модда"), "fieldtype": "Data", "width": 230},
		{"fieldname": "kategoriya", "label": _("Категория"), "fieldtype": "Data", "width": 140},
		{"fieldname": "summa", "label": _("Сумма"), "fieldtype": "Float", "precision": 2, "width": 130},
		{
			"fieldname": "currency",
			"label": _("Валюта"),
			"fieldtype": "Link",
			"options": "Currency",
			"width": 70,
		},
		{"fieldname": "remarks", "label": _("Изоҳ"), "fieldtype": "Data", "width": 220},
		{"fieldname": "voucher_type", "label": _("Тип"), "fieldtype": "Data", "hidden": 1},
		{
			"fieldname": "voucher_no",
			"label": _("Документ"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 160,
		},
	]


def get_cash_accounts(filters) -> list[str]:
	cond = {"company": filters.company}
	if filters.get("mode_of_payment"):
		cond["parent"] = filters.mode_of_payment
	accounts = frappe.get_all("Mode of Payment Account", filters=cond, pluck="default_account")
	return sorted({a for a in accounts if a})


def get_data(filters):
	"""Kassa hisoblaridagi GL yozuvlar. Har qatorda: kirim / chiqim (bitta kassa tanlansa - kassa valyutasida,
	aks holda firma valyutasida), kirim_acc / chiqim_acc / acc_currency (har doim kassa valyutasida)."""
	accounts = get_cash_accounts(filters)
	if not accounts:
		return [], {}, 0, 0
	single = len(accounts) == 1
	dr, cr = ("debit_in_account_currency", "credit_in_account_currency") if single else ("debit", "credit")
	currency = (
		frappe.get_cached_value("Account", accounts[0], "account_currency")
		if single
		else frappe.get_cached_value("Company", filters.company, "default_currency")
	)

	opening = flt(
		frappe.db.sql(
			f"""select sum({dr}) - sum({cr}) from `tabGL Entry`
			where account in %(acc)s and posting_date < %(from_date)s and is_cancelled = 0""",
			{"acc": accounts, "from_date": filters.from_date},
		)[0][0]
	)
	rows = frappe.db.sql(
		f"""select posting_date, account, account_currency, voucher_type, voucher_no, party_type, party, against,
			{dr} as kirim, {cr} as chiqim,
			debit_in_account_currency as kirim_acc, credit_in_account_currency as chiqim_acc
		from `tabGL Entry`
		where account in %(acc)s and posting_date between %(from_date)s and %(to_date)s and is_cancelled = 0
		order by posting_date, creation""",
		{"acc": accounts, "from_date": filters.from_date, "to_date": filters.to_date},
		as_dict=True,
	)

	vouchers = list({r.voucher_no for r in rows}) or [""]
	kassa = {
		k.linked_entry: k
		for k in frappe.db.sql(
			"""select linked_entry, izoh, kategoriya, party_type from `tabKassa`
			where linked_entry in %s and docstatus = 1""",
			[vouchers],
			as_dict=True,
		)
	}
	pe = {
		p.name: p
		for p in frappe.db.sql(
			"""select name, party_type, party, payment_type, remarks from `tabPayment Entry` where name in %s""",
			[vouchers],
			as_dict=True,
		)
	}
	je_rows = {}
	for a in frappe.db.sql(
		"""select jea.parent, jea.account, jea.party_type, jea.party, acc.root_type, acc.account_name, je.user_remark
		from `tabJournal Entry Account` jea
		join `tabJournal Entry` je on je.name = jea.parent
		left join `tabAccount` acc on acc.name = jea.account
		where jea.parent in %s""",
		[vouchers],
		as_dict=True,
	):
		je_rows.setdefault(a.parent, []).append(a)

	data, expense_summaries = [], {}
	balance = opening
	for r in rows:
		kirim, chiqim = flt(r.kirim), flt(r.chiqim)
		balance += kirim - chiqim
		info = resolve(r, pe, je_rows, accounts)
		if filters.get("party_type") and info.get("party_type") != filters.party_type:
			continue
		if filters.get("party") and info.get("party") != filters.party:
			continue
		k = kassa.get(r.voucher_no) or {}
		# o'zimizning ikkinchi firmamiz bilan pul (Firmalararo To'lov) - mijoz / ta'minotchi emas
		ichki = internal(info.get("party_type"), info.get("party"))
		if ichki:
			info["category"] = "internal"
			info["description"] = _("Firmalararo: {0}").format(ichki)
		if info["category"] == "expense":
			s = expense_summaries.setdefault(info["description"], {"kirim": 0, "chiqim": 0})
			s["kirim"] += kirim
			s["chiqim"] += chiqim
		data.append(
			{
				"posting_date": r.posting_date,
				"account": r.account,
				"direction": "Кирим" if kirim else "Чиқим",
				"description": info["description"],
				"kategoriya": k.get("kategoriya") or "",
				"dds_kategoriya": k.get("kategoriya")
				or (info["description"] if ichki else None)
				or CATEGORY_DEFAULT.get(info["category"])
				or info["description"],
				"category": info["category"],
				"summa": kirim or chiqim,
				"currency": currency,
				"remarks": k.get("izoh") or info.get("remarks") or "",
				"voucher_type": r.voucher_type,
				"voucher_no": r.voucher_no,
				"kirim": kirim,
				"chiqim": chiqim,
				"kirim_acc": flt(r.kirim_acc),
				"chiqim_acc": flt(r.chiqim_acc),
				"acc_currency": r.account_currency,
			}
		)
	return data, expense_summaries, opening, balance


def internal(party_type, party) -> str | None:
	"""Kontragent o'zimizning boshqa firmamiz bo'lsa - o'sha firma nomi (so'rov ichida keshlanadi)."""
	if party_type not in ("Customer", "Supplier") or not party:
		return None
	cache = frappe.flags.setdefault("dds_internal", {})
	if (party_type, party) not in cache:
		cache[(party_type, party)] = get_internal_company(party_type, party)
	return cache[(party_type, party)]


def party_name(party_type, party):
	field = PARTY_NAME_FIELD.get(party_type)
	return (field and frappe.db.get_value(party_type, party, field)) or party


def resolve(r, pe, je_rows, accounts) -> dict:
	suffix = "Приход" if flt(r.kirim) else "Расход"
	if r.party_type and r.party:
		return {
			"description": f"{party_name(r.party_type, r.party)} ({suffix})",
			"category": PARTY_CATEGORY.get(r.party_type, "other"),
			"party_type": r.party_type,
			"party": r.party,
		}
	p = pe.get(r.voucher_no)
	if p:
		if p.payment_type == "Internal Transfer":
			return {"description": "Перемещение", "category": "transfer", "remarks": p.remarks}
		if p.party_type and p.party:
			return {
				"description": f"{party_name(p.party_type, p.party)} ({suffix})",
				"category": PARTY_CATEGORY.get(p.party_type, "other"),
				"party_type": p.party_type,
				"party": p.party,
				"remarks": p.remarks,
			}
	for a in je_rows.get(r.voucher_no, []):
		if a.account in accounts:
			continue
		if a.party_type and a.party:
			return {
				"description": party_name(a.party_type, a.party),
				"category": PARTY_CATEGORY.get(a.party_type, "other"),
				"party_type": a.party_type,
				"party": a.party,
				"remarks": a.user_remark,
			}
		if a.root_type == "Expense":
			return {"description": a.account_name, "category": "expense", "remarks": a.user_remark}
		if a.root_type == "Income":
			return {"description": a.account_name, "category": "income", "remarks": a.user_remark}
		if a.root_type == "Equity":
			return {"description": a.account_name, "category": "dividend", "remarks": a.user_remark}
		return {"description": a.account_name, "category": "other", "remarks": a.user_remark}
	if je_rows.get(r.voucher_no):
		# Journal Entry'ning barcha qatorlari kassa hisoblari: kassalar orasida o'tkazma
		return {
			"description": "Перемещение",
			"category": "transfer",
			"remarks": je_rows[r.voucher_no][0].user_remark,
		}
	return {"description": r.against or r.voucher_no, "category": "other"}
