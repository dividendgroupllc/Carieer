# DDS (движение денежных средств) - Armada loyihasidagi DDS andozasi asosida.
# Kassa hisoblaridagi har bir GL yozuv: sana, kassa, kirim/chiqim, kategoriya, summa, izoh, hujjat.
# Tepada yig'ma jadval: boshlang'ich qoldiq -> kategoriyalar bo'yicha kirim/chiqim -> yakuniy qoldiq.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.utils import check_report_company

CATEGORY_MAP = {
	"Покупатели": "customer",
	"Поставщики": "supplier",
	"Сотрудники": "employee",
	"Учредители": "shareholder",
	"Дивиденды": "dividend",
	"Расходы": "expense",
	"Прочие доходы": "income",
	"Перемещения": "transfer",
	"Прочие": "other",
}
CATEGORY_LABELS = {v: k for k, v in CATEGORY_MAP.items()}
PARTY_CATEGORY = {"Customer": "customer", "Supplier": "supplier", "Employee": "employee", "Shareholder": "shareholder"}
PARTY_NAME_FIELD = {"Customer": "customer_name", "Supplier": "supplier_name", "Employee": "employee_name", "Shareholder": "title"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	check_report_company(filters)
	data, expense_summaries, opening, closing = get_data(filters)
	return get_columns(), data, get_summary_html(data, expense_summaries, opening, closing)


def get_columns():
	return [
		{"fieldname": "posting_date", "label": _("Сана"), "fieldtype": "Date", "width": 95},
		{"fieldname": "account", "label": _("Касса"), "fieldtype": "Link", "options": "Account", "width": 160},
		{"fieldname": "direction", "label": _("Кирим/Чиқим"), "fieldtype": "Data", "width": 95},
		{"fieldname": "description", "label": _("Контрагент / модда"), "fieldtype": "Data", "width": 230},
		{"fieldname": "kategoriya", "label": _("Категория"), "fieldtype": "Data", "width": 140},
		{"fieldname": "summa", "label": _("Сумма"), "fieldtype": "Float", "precision": 2, "width": 130},
		{"fieldname": "currency", "label": _("Валюта"), "fieldtype": "Link", "options": "Currency", "width": 70},
		{"fieldname": "remarks", "label": _("Изоҳ"), "fieldtype": "Data", "width": 220},
		{"fieldname": "voucher_type", "label": _("Тип"), "fieldtype": "Data", "hidden": 1},
		{"fieldname": "voucher_no", "label": _("Документ"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 160},
	]


def get_cash_accounts(filters) -> list[str]:
	cond = {"company": filters.company}
	if filters.get("mode_of_payment"):
		cond["parent"] = filters.mode_of_payment
	accounts = frappe.get_all("Mode of Payment Account", filters=cond, pluck="default_account")
	return sorted({a for a in accounts if a})


def get_data(filters):
	accounts = get_cash_accounts(filters)
	if not accounts:
		return [], {}, 0, 0
	# Kassalar turli valyutada bo'lishi mumkin: bitta kassa tanlansa - o'z valyutasida, aks holda firma valyutasida
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
		f"""select posting_date, account, voucher_type, voucher_no, party_type, party, against,
			{dr} as kirim, {cr} as chiqim
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

	f_cat = CATEGORY_MAP.get(filters.get("category"))
	data, expense_summaries = [], {}
	balance = opening
	for r in rows:
		kirim, chiqim = flt(r.kirim), flt(r.chiqim)
		balance += kirim - chiqim
		info = resolve(r, pe, je_rows, accounts)
		if f_cat and info["category"] != f_cat:
			continue
		if filters.get("party_type") and info.get("party_type") != filters.party_type:
			continue
		if filters.get("party") and info.get("party") != filters.party:
			continue
		k = kassa.get(r.voucher_no) or {}
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
				"category": info["category"],
				"summa": kirim or chiqim,
				"currency": currency,
				"remarks": k.get("izoh") or info.get("remarks") or "",
				"voucher_type": r.voucher_type,
				"voucher_no": r.voucher_no,
				"kirim": kirim,
				"chiqim": chiqim,
			}
		)
	return data, expense_summaries, opening, balance


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
		return {"description": "Перемещение", "category": "transfer", "remarks": je_rows[r.voucher_no][0].user_remark}
	return {"description": r.against or r.voucher_no, "category": "other"}


def get_summary_html(data, expense_summaries, opening, closing):
	if not data and not opening:
		return ""
	totals = {c: [0, 0] for c in CATEGORY_LABELS}
	for d in data:
		t = totals.setdefault(d["category"], [0, 0])
		t[0] += d["kirim"]
		t[1] += d["chiqim"]

	def fmt(v):
		return "—" if not flt(v) else f"{flt(v):,.2f}".replace(",", " ")

	td = "padding:8px 10px;border:1px solid var(--border-color);"
	rows = ""
	for cat, label in CATEGORY_LABELS.items():
		k, c = totals.get(cat, [0, 0])
		if cat == "expense" and expense_summaries:
			rows += f"""<tr style="cursor:pointer" onclick="document.querySelectorAll('.dds-exp').forEach(e=>e.style.display=e.style.display==='none'?'table-row':'none')">
				<td style="{td}">▸ {label}</td><td style="{td}text-align:right;color:#388e3c">{fmt(k)}</td>
				<td style="{td}text-align:right;color:#d32f2f">{fmt(c)}</td></tr>"""
			for name, s in sorted(expense_summaries.items()):
				rows += f"""<tr class="dds-exp" style="display:none;background:var(--subtle-fg)">
					<td style="{td}padding-left:28px;font-style:italic">{frappe.utils.escape_html(name)}</td>
					<td style="{td}text-align:right;color:#388e3c">{fmt(s['kirim'])}</td>
					<td style="{td}text-align:right;color:#d32f2f">{fmt(s['chiqim'])}</td></tr>"""
			continue
		rows += f"""<tr><td style="{td}">{label}</td><td style="{td}text-align:right;color:#388e3c">{fmt(k)}</td>
			<td style="{td}text-align:right;color:#d32f2f">{fmt(c)}</td></tr>"""
	head = "background:var(--subtle-accent);font-weight:600;"
	return f"""<div style="margin:10px 0 16px">
		<table style="width:100%;border-collapse:collapse">
			<thead><tr style="{head}"><th style="{td}width:40%"></th>
				<th style="{td}text-align:right;color:#388e3c">Кирим</th><th style="{td}text-align:right;color:#d32f2f">Чиқим</th></tr></thead>
			<tbody>
				<tr style="{head}"><td style="{td}">Начальный остаток</td><td style="{td}text-align:right" colspan="2">{fmt(opening) if opening else '0.00'}</td></tr>
				{rows}
				<tr style="{head}"><td style="{td}">Конечный остаток</td><td style="{td}text-align:right" colspan="2">{fmt(closing) if closing else '0.00'}</td></tr>
			</tbody>
		</table></div>"""
