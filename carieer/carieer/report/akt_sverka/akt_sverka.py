# Akt Sverka (акт сверки) - Google Sheets'dagi varaq tuzilishida.
# Bitta kontragent bilan davr ichidagi barcha hisob-kitob. Tepada yig'ma jadval: Сальдо на начало, Сумма оплаты,
# Сумма отгрузки, Сальдo на конец - har biri Кредит Сум / Дебет Сум / Кредит $ / Дебет $ ustunlarida.
# Pastda xronologik ro'yxat: sotuv / xarid (tovar, miqdor, narx), hisoblashlar (Начисление) va to'lovlar (Касса).
# Ishora: Кредит = kontragent foydasiga (biz qarzdor), Дебет = bizning foydamizga (kontragent qarzdor).
# Manba - GL: mijozga sotuv Дебет, mijoz to'lovi Кредит; ta'minotchidan xarid Кредит, unga to'lov Дебет.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import PARTY_FILTERS, blank_zeros, bold, party_condition, prepare

# Hujjat -> yig'ma jadvaldagi qator: to'lov (Касса) yoki otgruzka (sotuv, xarid, начисление)
PAYMENT_TYPES = ("Payment Entry",)
# Hujjatning «tabiiy» yo'nalishi: otgruzka summasi shu tomonda musbat (qaytarish - manfiy)
NATURAL = {"Sales Invoice": "debit", "Purchase Invoice": "credit"}


def execute(filters=None):
	filters = prepare(filters, period="year")
	if not resolve_parties(filters):
		return get_columns(), [], _("Контрагентни танланг: Мижоз, Таъминотчи ёки Ходим")
	data, summary = get_data(filters)
	# tovar bo'lmagan qatorlarda (to'lov, nachislenie) «Кол-во / Цена» bo'sh ko'rinsin, «0.00» emas
	data = blank_zeros(data, ("qty", "rate", "amount", "payment", "balance_credit", "balance_debit"))
	return get_columns(), data, get_summary_html(summary, filters)


def resolve_parties(filters) -> bool:
	"""Mijoz / Ta'minotchi / Xodim. Bir nechtasi tanlansa - birgalikdagi akt (masalan bitta firma bizdan tovar oladi
	va bizga xizmat ko'rsatadi: mijoz va ta'minotchi qarzi bir aktda qo'shib ko'rsatiladi)."""
	chosen = [(dt, filters.get(f)) for f, dt in PARTY_FILTERS if filters.get(f)]
	if not chosen:
		return False
	filters.party_type, filters.party = chosen[0]
	filters.party_label = " + ".join(dict.fromkeys(p for _dt, p in chosen))
	filters.party_cond, values = party_condition(chosen)
	filters.update(values)
	return True


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency", "width": 120}
	return [
		{"label": _("Дата"), "fieldname": "posting_date", "fieldtype": "Date", "width": 90},
		{"label": _("Ҳужжат"), "fieldname": "voucher_label", "fieldtype": "Data", "width": 110},
		{
			"label": _("Ҳужжат №"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 150,
		},
		{"label": _("Наименования"), "fieldname": "item_name", "fieldtype": "Data", "width": 190},
		{"label": _("Кол-во"), "fieldname": "qty", "fieldtype": "Float", "precision": 2, "width": 80},
		{"label": _("Ед изм"), "fieldname": "uom", "fieldtype": "Data", "width": 70},
		{"label": _("Цена"), "fieldname": "rate", "fieldtype": "Float", "precision": 2, "width": 100},
		{
			"label": _("Валюта"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"width": 65,
		},
		{"label": _("Сумма"), "fieldname": "amount", **cur},
		{"label": _("Оплата сумма"), "fieldname": "payment", **cur},
		{"label": _("Қолдиқ (Кред)"), "fieldname": "balance_credit", **cur},
		{"label": _("Қолдиқ (Деб)"), "fieldname": "balance_debit", **cur},
		{"label": _("Коммент"), "fieldname": "komment", "fieldtype": "Data", "width": 220},
		{"label": "", "fieldname": "voucher_type", "fieldtype": "Data", "hidden": 1},
	]


def get_data(filters):
	company_currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	# valyuta bo'yicha boshlang'ich qoldiq (kontragent so'mda ham, dollarda ham hisoblashgan bo'lishi mumkin)
	balances = {
		r.currency: flt(r.net)
		for r in frappe.db.sql(
			f"""select account_currency currency, sum(credit_in_account_currency) - sum(debit_in_account_currency) net
			from `tabGL Entry`
			where company=%(company)s and {filters.party_cond} and posting_date < %(from_date)s and is_cancelled=0
			group by account_currency""",
			filters,
			as_dict=True,
		)
	}
	gl = frappe.db.sql(
		f"""select posting_date, voucher_type, voucher_no, account_currency currency,
			sum(credit_in_account_currency) credit, sum(debit_in_account_currency) debit, min(creation) creation
		from `tabGL Entry`
		where company=%(company)s and {filters.party_cond}
			and posting_date between %(from_date)s and %(to_date)s and is_cancelled=0
		group by posting_date, voucher_type, voucher_no, account_currency
		order by posting_date, creation""",
		filters,
		as_dict=True,
	)
	if filters.get("currency"):
		balances = {k: v for k, v in balances.items() if k == filters.currency}
		gl = [g for g in gl if g.currency == filters.currency]
	currencies = list(dict.fromkeys([*balances, *(g.currency for g in gl)])) or [company_currency]
	filters.company_currency = company_currency
	filters.foreign_currency = next((c for c in currencies if c != company_currency), "USD")

	items = get_invoice_items(
		[g.voucher_no for g in gl if g.voucher_type in ("Sales Invoice", "Purchase Invoice")]
	)
	komment = get_komments(gl)

	# yig'ma jadval: har valyuta (sum / usd) uchun [kredit, debet] juftliklari
	summary = {
		g: {"opening": 0.0, "payment": [0.0, 0.0], "shipment": [0.0, 0.0], "closing": 0.0} for g in ("sum", "usd")
	}
	data = []
	for cur in currencies:
		grp = "sum" if cur == company_currency else "usd"
		summary[grp]["opening"] += balances.get(cur, 0.0)
		data.append(
			{
				"posting_date": filters.from_date,
				"voucher_label": bold(_("Бошланғич қолдиқ")),
				"currency": cur,
				**split_balance(balances.get(cur, 0.0)),
			}
		)
	for g in gl:
		cur = g.currency
		grp = "sum" if cur == company_currency else "usd"
		credit, debit = flt(g.credit), flt(g.debit)
		kind = "payment" if g.voucher_type in PAYMENT_TYPES else "shipment"
		summary[grp][kind][0] += credit
		summary[grp][kind][1] += debit
		balances[cur] = balances.get(cur, 0.0) + credit - debit
		base = {
			"posting_date": g.posting_date,
			"voucher_type": g.voucher_type,
			"voucher_no": g.voucher_no,
			"voucher_label": voucher_label(g.voucher_type),
			"currency": cur,
			"komment": komment.get(g.voucher_no, ""),
		}
		lines = items.get(g.voucher_no)
		if kind == "payment":
			data.append(
				{
					**base,
					"item_name": item_label(g.voucher_type, credit, debit),
					"payment": abs(credit - debit),
					**split_balance(balances[cur]),
				}
			)
			continue
		amount = shipment_amount(g.voucher_type, credit, debit)
		if lines:
			# GL summasi (hisob valyutasida) qatorlar orasida ulushiga qarab bo'linadi (valyuta va soliq ham hisobga olinadi)
			total = sum(flt(i.base_net_amount) for i in lines) or 1
			for idx, i in enumerate(lines):
				row = {
					**base,
					"item_name": i.item_name,
					"qty": i.qty,
					"uom": i.uom,
					"rate": i.rate,
					"amount": flt(amount * flt(i.base_net_amount) / total, 2),
				}
				if idx == len(lines) - 1:
					row.update(split_balance(balances[cur]))
				data.append(row)
		else:
			data.append({**base, "item_name": item_label(g.voucher_type, credit, debit), "amount": amount, **split_balance(balances[cur])})

	for cur in currencies:
		grp = "sum" if cur == company_currency else "usd"
		summary[grp]["closing"] += balances.get(cur, 0.0)
		data.append(
			{
				"posting_date": filters.to_date,
				"voucher_label": bold(_("Жами")),
				"currency": cur,
				"amount": sum(r.get("amount") or 0 for r in data if r.get("currency") == cur and r.get("voucher_no")),
				"payment": sum(r.get("payment") or 0 for r in data if r.get("currency") == cur and r.get("voucher_no")),
				**split_balance(balances.get(cur, 0.0)),
			}
		)
	return data, summary


def shipment_amount(voucher_type, credit, debit) -> float:
	"""Otgruzka summasi (musbat): sotuv - debet, xarid - kredit, nachislenie - qaysi tomonda bo'lsa o'sha."""
	natural = NATURAL.get(voucher_type)
	if natural == "debit":
		return flt(debit - credit, 2)
	if natural == "credit":
		return flt(credit - debit, 2)
	return flt(abs(credit - debit), 2)


def split_balance(value):
	value = flt(value, 2)
	return {"balance_credit": max(value, 0.0), "balance_debit": abs(min(value, 0.0))}


def voucher_label(voucher_type):
	return {
		"Sales Invoice": _("Сотув"),
		"Purchase Invoice": _("Харид"),
		"Payment Entry": _("Тўлов"),
		"Journal Entry": _("Начисление"),
	}.get(voucher_type, voucher_type)


def item_label(voucher_type, credit, debit):
	if voucher_type == "Payment Entry":
		return _("Оплата (приход)") if credit > debit else _("Оплата (расход)")
	return ""


def get_invoice_items(vouchers):
	if not vouchers:
		return {}
	out = {}
	for dt in ("Sales Invoice", "Purchase Invoice"):
		for i in frappe.db.sql(
			f"""select parent, item_name, qty, uom, rate, base_net_amount from `tab{dt} Item`
			where parent in %s order by parent, idx""",
			[vouchers],
			as_dict=True,
		):
			out.setdefault(i.parent, []).append(i)
	return out


def get_komments(gl):
	"""Izoh: Kassa izohi, Sotuv'dagi mashina raqami, Начисление izohi yoki hujjatning o'z izohi."""
	names = [g.voucher_no for g in gl] or [""]
	out = {}
	for r in frappe.db.sql(
		"select name, remarks from `tabPayment Entry` where name in %s", [names], as_dict=True
	):
		out[r.name] = r.remarks or ""
	for r in frappe.db.sql(
		"select name, user_remark from `tabJournal Entry` where name in %s", [names], as_dict=True
	):
		out[r.name] = r.user_remark or ""
	for r in frappe.db.sql(
		"select linked_entry, izoh from `tabKassa` where linked_entry in %s and docstatus=1",
		[names],
		as_dict=True,
	):
		if r.izoh:
			out[r.linked_entry] = r.izoh
	for r in frappe.db.sql(
		"""select sales_invoice, mashina_raqami, izoh from `tabSotuv` where sales_invoice in %s and docstatus=1""",
		[names],
		as_dict=True,
	):
		out[r.sales_invoice] = " · ".join(filter(None, (r.mashina_raqami, r.izoh)))
	return out


def get_summary_html(s, filters):
	"""Jadvaldagi shapka: Сальдо на начало / Сумма оплаты / Сумма отгрузки / Сальдо на конец x (Кредит, Дебет) x (Сум, $)."""

	def fmt(v):
		return f"{flt(v):,.2f}".replace(",", " ") if abs(flt(v)) >= 0.005 else ""

	td = "padding:8px 10px;border:1px solid var(--border-color);"
	head = "background:var(--subtle-accent);font-weight:600;"
	def pair(grp, key):
		v = s[grp][key]
		if isinstance(v, list):
			return v
		return [max(flt(v), 0), abs(min(flt(v), 0))]

	rows = [
		(_("Сальдо на начало"), "opening", head),
		(_("Сумма оплаты"), "payment", ""),
		(_("Сумма отгрузки"), "shipment", ""),
		(_("Сальдо на конец"), "closing", head),
	]
	body = ""
	for label, key, style in rows:
		cells = "".join(
			f'<td style="{td}text-align:right;color:{color}">{fmt(val)}</td>'
			for grp in ("sum", "usd")
			for val, color in zip(pair(grp, key), ("#d32f2f", "#388e3c"), strict=True)
		)
		body += f'<tr style="{style}"><td style="{td}">{label}</td>{cells}</tr>'
	who = frappe.utils.escape_html(filters.get("party_label") or filters.party)
	cur_sum, cur_usd = filters.company_currency, filters.foreign_currency
	return f"""<div style="margin:10px 0 16px">
		<div style="margin-bottom:6px"><b>{_("Начало периода")}:</b> {frappe.format(filters.from_date, "Date")} ·
		<b>{_("Конец периода")}:</b> {frappe.format(filters.to_date, "Date")} · <b>{_("Контрагент")}:</b> {who}</div>
		<table style="width:100%;border-collapse:collapse">
			<thead><tr style="{head}"><th style="{td}width:28%">{_("Валюта")}</th>
			<th style="{td}text-align:right;color:#d32f2f">{_("Кредит")} {cur_sum}</th>
			<th style="{td}text-align:right;color:#388e3c">{_("Дебет")} {cur_sum}</th>
			<th style="{td}text-align:right;color:#d32f2f">{_("Кредит")} {cur_usd}</th>
			<th style="{td}text-align:right;color:#388e3c">{_("Дебет")} {cur_usd}</th></tr></thead>
			<tbody>{body}</tbody>
		</table></div>"""
