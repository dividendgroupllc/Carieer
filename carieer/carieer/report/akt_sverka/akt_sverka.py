# Akt Sverka (акт сверки) - Armada andozasi asosida.
# Bitta kontragent bilan davr ichidagi barcha hisob-kitob: sotuv/xarid (tovar, miqdor, narx), to'lovlar,
# hisoblashlar (Начисление / Journal Entry) va har qatordan keyingi qoldiq. Tepada yig'ma jadval.
# Ishora: Kredit = kontragent foydasiga (biz qarzdor), Debet = bizning foydamizga (kontragent qarzdor).

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import bold, prepare, resolve_party

GROUPS = {
	"Sales Invoice": "goods",
	"Purchase Invoice": "goods",
	"Payment Entry": "money",
	"Journal Entry": "accruals",
}


def execute(filters=None):
	filters = prepare(filters, period="year")
	if not resolve_party(filters):
		return get_columns(), [], _("Контрагентни танланг: Мижоз, Таъминотчи ёки Ходим")
	data, summary = get_data(filters)
	return get_columns(), data, get_summary_html(summary, filters)


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency", "width": 120}
	return [
		{"label": _("Сана"), "fieldname": "posting_date", "fieldtype": "Date", "width": 90},
		{"label": _("Ҳужжат"), "fieldname": "voucher_label", "fieldtype": "Data", "width": 110},
		{
			"label": _("Ҳужжат №"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 150,
		},
		{"label": _("Наименование"), "fieldname": "item_name", "fieldtype": "Data", "width": 170},
		{"label": _("Кол-во"), "fieldname": "qty", "fieldtype": "Float", "precision": 2, "width": 80},
		{"label": _("Ед.изм"), "fieldname": "uom", "fieldtype": "Data", "width": 70},
		{"label": _("Цена"), "fieldname": "rate", "fieldtype": "Float", "precision": 2, "width": 100},
		{"label": _("Кредит"), "fieldname": "credit", **cur},
		{"label": _("Дебет"), "fieldname": "debit", **cur},
		{"label": _("Қолдиқ (Кред)"), "fieldname": "balance_credit", **cur},
		{"label": _("Қолдиқ (Деб)"), "fieldname": "balance_debit", **cur},
		{"label": _("Коммент"), "fieldname": "komment", "fieldtype": "Data", "width": 220},
		{
			"label": _("Валюта"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"width": 65,
		},
		{"label": "", "fieldname": "voucher_type", "fieldtype": "Data", "hidden": 1},
	]


def party_currency(filters) -> str:
	if filters.get("currency"):
		return filters.currency
	row = frappe.db.sql(
		"""select account_currency from `tabGL Entry`
		where company=%(company)s and party_type=%(party_type)s and party=%(party)s and is_cancelled=0
		order by posting_date desc, creation desc limit 1""",
		filters,
	)
	return row[0][0] if row else frappe.get_cached_value("Company", filters.company, "default_currency")


def get_data(filters):
	filters.currency = party_currency(filters)
	opening = flt(
		frappe.db.sql(
			"""select sum(credit_in_account_currency) - sum(debit_in_account_currency) from `tabGL Entry`
			where company=%(company)s and party_type=%(party_type)s and party=%(party)s and account_currency=%(currency)s
			and posting_date < %(from_date)s and is_cancelled=0""",
			filters,
		)[0][0]
	)
	gl = frappe.db.sql(
		"""select posting_date, voucher_type, voucher_no,
			sum(credit_in_account_currency) credit, sum(debit_in_account_currency) debit, min(creation) creation
		from `tabGL Entry`
		where company=%(company)s and party_type=%(party_type)s and party=%(party)s and account_currency=%(currency)s
			and posting_date between %(from_date)s and %(to_date)s and is_cancelled=0
		group by posting_date, voucher_type, voucher_no
		order by posting_date, creation""",
		filters,
		as_dict=True,
	)
	items = get_invoice_items(
		[g.voucher_no for g in gl if g.voucher_type in ("Sales Invoice", "Purchase Invoice")]
	)
	komment = get_komments(gl)

	cur = filters.currency
	summary = {"opening": opening, "goods": [0, 0], "money": [0, 0], "accruals": [0, 0], "other": [0, 0]}
	data = [
		{
			"posting_date": filters.from_date,
			"voucher_label": bold(_("Бошланғич қолдиқ")),
			"currency": cur,
			**split_balance(opening),
		}
	]
	balance = opening
	for g in gl:
		credit, debit = flt(g.credit), flt(g.debit)
		group = GROUPS.get(g.voucher_type, "other")
		summary[group][0] += credit
		summary[group][1] += debit
		balance += credit - debit
		base = {
			"posting_date": g.posting_date,
			"voucher_type": g.voucher_type,
			"voucher_no": g.voucher_no,
			"voucher_label": voucher_label(g.voucher_type),
			"currency": cur,
			"komment": komment.get(g.voucher_no, ""),
		}
		lines = items.get(g.voucher_no)
		if lines:
			# GL summasi (hisob valyutasida) qatorlar orasida ulushiga qarab bo'linadi (valyuta va soliq ham hisobga olinadi)
			total = sum(flt(i.base_net_amount) for i in lines) or 1
			for idx, i in enumerate(lines):
				share = flt(i.base_net_amount) / total
				row = {
					**base,
					"item_name": i.item_name,
					"qty": i.qty,
					"uom": i.uom,
					"rate": i.rate,
					"credit": flt(credit * share, 2),
					"debit": flt(debit * share, 2),
				}
				if idx == len(lines) - 1:
					row.update(split_balance(balance))
				data.append(row)
		else:
			data.append(
				{
					**base,
					"item_name": item_label(g.voucher_type, credit, debit),
					"credit": credit,
					"debit": debit,
					**split_balance(balance),
				}
			)

	summary["closing"] = balance
	data.append(
		{
			"posting_date": filters.to_date,
			"voucher_label": bold(_("Жами")),
			"currency": cur,
			"credit": sum(summary[k][0] for k in ("goods", "money", "accruals", "other")),
			"debit": sum(summary[k][1] for k in ("goods", "money", "accruals", "other")),
			**split_balance(balance),
		}
	)
	return data, summary


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
		return _("Оплата (приход)") if credit else _("Оплата (расход)")
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
	def fmt(v):
		return f"{flt(v):,.2f}".replace(",", " ")

	td = "padding:8px 10px;border:1px solid var(--border-color);"
	head = "background:var(--subtle-accent);font-weight:600;"
	o, c = flt(s["opening"]), flt(s["closing"])
	rows = [
		(_("Сальдо на начало"), max(o, 0), abs(min(o, 0)), head),
		(_("Отгрузка (товары, услуги)"), *s["goods"], ""),
		(_("Оплата (деньги)"), *s["money"], ""),
		(_("Начисления"), *s["accruals"], ""),
	]
	if any(s["other"]):
		rows.append((_("Прочие"), *s["other"], ""))
	rows.append((_("Сальдо на конец"), max(c, 0), abs(min(c, 0)), head))
	body = "".join(
		f"""<tr style="{style}"><td style="{td}">{label}</td>
		<td style="{td}text-align:right;color:#d32f2f">{fmt(cr)}</td>
		<td style="{td}text-align:right;color:#388e3c">{fmt(dr)}</td></tr>"""
		for label, cr, dr, style in rows
	)
	who = frappe.utils.escape_html(filters.party)
	return f"""<div style="margin:10px 0 16px">
		<div style="margin-bottom:6px"><b>{_("Контрагент")}:</b> {who} · <b>{_("Валюта")}:</b> {filters.currency}
		· {frappe.format(filters.from_date, "Date")} – {frappe.format(filters.to_date, "Date")}</div>
		<table style="width:100%;border-collapse:collapse">
			<thead><tr style="{head}"><th style="{td}width:40%"></th>
			<th style="{td}text-align:right;color:#d32f2f">{_("Кредит")}</th>
			<th style="{td}text-align:right;color:#388e3c">{_("Дебет")}</th></tr></thead>
			<tbody>{body}</tbody>
		</table></div>"""
