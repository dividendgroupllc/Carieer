# Kontragent Otchet ("Оборотка контрагентов") - Google Sheets'dagi varaq tuzilishida:
#   har bir kontragent BITTA qatorda: Начальное сальдо | Оборот | Конечное сальдо, har birida
#   Кредит Сум, Дебет Сум, Кредит $, Дебет $ (so'm va dollar yonma-yon), oxirida Сальдо (Д-К).
#   Tepada «Общая задолженность» - ustunlar jami.
# Kredit qoldiq = biz qarzdormiz (kontragent oldindan to'lagan / biz undan oldik), Debet = kontragent bizdan qarzdor.
# Summalar kontragent hisobi valyutasida: so'm hisobidagilari «Сум» ustunlarida, dollar hisobidagilari «$» ustunlarida.
# Kontragent qatorida davr ichida nima olingani / sotilgani («Маҳсулот») va oxirgi harakat sanasi; qator ochilsa
# ostida har bir hujjat: sana, hujjat, tovarlar (miqdor x narx) va oborot summasi.

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.akt_sverka.akt_sverka import (
	get_invoice_items,
	get_komments,
	item_label,
	voucher_label,
)
from carieer.carieer.report.common import (
	PARTY_LABELS,
	bold,
	kontragent_turi,
	normalize_turi,
	party_types_for_turi,
	prepare,
	resolve_party,
	turi_ok,
)

PARTY_FIELD = {"Customer": "customer", "Supplier": "supplier", "Employee": "employee"}
BOSQICH = (("nach", _("нач.")), ("obor", _("оборот")), ("kon", _("кон.")))
# (ustun qo'shimchasi, valyuta guruhi): sum - firma valyutasi, usd - boshqa valyuta (dollar)
VALYUTA = (("sum", _("Сум")), ("usd", "$"))
AMOUNT_FIELDS = [f"{b}_{side}_{v}" for b, _l in BOSQICH for v, _vl in VALYUTA for side in ("kr", "dt")] + [
	"saldo_sum",
	"saldo_usd",
]


def execute(filters=None):
	filters = prepare(filters, period="month")
	resolve_party(filters)
	data, totals = get_data(filters)
	return get_columns(), data, None, None, get_summary(totals)


def get_columns():
	cols = [
		{"label": _("Тип"), "fieldname": "turi", "fieldtype": "Data", "width": 120},
		{"label": "", "fieldname": "party_type", "fieldtype": "Data", "hidden": 1},
		{
			"label": _("Контрагент"),
			"fieldname": "party",
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 190,
		},
		{"label": _("Сана"), "fieldname": "sana", "fieldtype": "Date", "width": 105},
		{"label": "", "fieldname": "voucher_type", "fieldtype": "Data", "hidden": 1},
		{
			"label": _("Ҳужжат"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 150,
		},
		{"label": _("Маҳсулот"), "fieldname": "mahsulot", "fieldtype": "Data", "width": 280},
		{"label": _("Акт сверка"), "fieldname": "akt_sverka", "fieldtype": "Data", "width": 95},
	]
	for b, b_label in BOSQICH:
		for v, v_label in VALYUTA:
			for side, side_label in (("kr", _("Кредит")), ("dt", _("Дебет"))):
				cols.append(
					{
						"label": f"{side_label} {v_label} ({b_label})",
						"fieldname": f"{b}_{side}_{v}",
						"fieldtype": "Currency",
						"options": f"cur_{v}",
						"width": 130,
					}
				)
	cols += [
		{
			"label": _("Сальдо Сум (Д-К)"),
			"fieldname": "saldo_sum",
			"fieldtype": "Currency",
			"options": "cur_sum",
			"width": 135,
		},
		{
			"label": _("Сальдо $ (Д-К)"),
			"fieldname": "saldo_usd",
			"fieldtype": "Currency",
			"options": "cur_usd",
			"width": 120,
		},
		{"label": "", "fieldname": "cur_sum", "fieldtype": "Data", "hidden": 1},
		{"label": "", "fieldname": "cur_usd", "fieldtype": "Data", "hidden": 1},
	]
	return cols


def get_data(filters):
	cond = [
		"company = %(company)s",
		"ifnull(party, '') != ''",
		"ifnull(party_type, '') != ''",
		"is_cancelled = 0",
	]
	turi = normalize_turi(filters.get("turi"))
	if filters.get("party_type"):
		cond.append("party_type = %(party_type)s")
	else:
		filters.party_types = party_types_for_turi(turi)
		cond.append("party_type in %(party_types)s")
	if filters.get("party"):
		cond.append("party = %(party)s")
	rows = frappe.db.sql(
		f"""select party_type, party, account_currency as currency,
			sum(if(posting_date < %(from_date)s, credit_in_account_currency, 0)) opening_credit,
			sum(if(posting_date < %(from_date)s, debit_in_account_currency, 0)) opening_debit,
			sum(if(posting_date >= %(from_date)s, credit_in_account_currency, 0)) period_credit,
			sum(if(posting_date >= %(from_date)s, debit_in_account_currency, 0)) period_debit
		from `tabGL Entry`
		where {" and ".join(cond)} and posting_date <= %(to_date)s
		group by party_type, party, account_currency
		order by party_type, party""",
		filters,
		as_dict=True,
	)
	company_currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	foreign = next((r.currency for r in rows if r.currency != company_currency), "USD")
	parties = {}
	for r in rows:
		v = "sum" if r.currency == company_currency else "usd"
		opening = flt(r.opening_credit) - flt(r.opening_debit)  # musbat - kredit (biz qarzdormiz)
		final = opening + flt(r.period_credit) - flt(r.period_debit)
		if not turi_ok(turi, r.party_type, r.party):
			continue
		if not filters.get("show_zero") and not any((opening, r.period_credit, r.period_debit)):
			continue
		row = parties.get((r.party_type, r.party))
		if not row:
			row = parties[(r.party_type, r.party)] = {
				"party_type": r.party_type,
				"party": r.party,
				"turi": kontragent_turi(r.party_type, r.party),
				"akt_sverka": akt_link(filters, r.party_type, r.party),
				"cur_sum": company_currency,
				"cur_usd": foreign,
				**{f: 0.0 for f in AMOUNT_FIELDS},
			}
		row[f"nach_kr_{v}"] += max(opening, 0)
		row[f"nach_dt_{v}"] += max(-opening, 0)
		row[f"obor_kr_{v}"] += flt(r.period_credit)
		row[f"obor_dt_{v}"] += flt(r.period_debit)
		row[f"kon_kr_{v}"] += max(final, 0)
		row[f"kon_dt_{v}"] += max(-final, 0)
		row[f"saldo_{v}"] += -final

	data = sorted(parties.values(), key=lambda r: (r["turi"], r["party"]))
	totals = {f: sum(flt(r[f]) for r in data) for f in AMOUNT_FIELDS}
	totals.update(cur_sum=company_currency, cur_usd=foreign)
	details = get_details(filters, cond, company_currency)
	tree = []
	for row in data:
		key = (row["party_type"], row["party"])
		children = details.get(key, [])
		row.update(name="|".join(key), indent=0, mahsulot=mahsulot_jami(children))
		if children:
			row["sana"] = children[-1]["sana"]
		tree.append(row)
		for child in children:
			tree.append({**child, "parent_row": row["name"], "cur_sum": company_currency, "cur_usd": foreign})
	if tree:
		# jadvaldagi kabi «Общая задолженность» qatori ro'yxat tepasida
		tree.insert(0, {"name": "total", "indent": 0, "turi": bold(_("Общая задолженность")), **totals})
	return blank(tree), totals


def get_details(filters, cond, company_currency) -> dict:
	"""Davr ichidagi hujjatlar kontragent bo'yicha: {(party_type, party): [qator, ...]} (sana tartibida)."""
	gl = frappe.db.sql(
		f"""select party_type, party, posting_date, voucher_type, voucher_no, account_currency currency,
			sum(credit_in_account_currency) credit, sum(debit_in_account_currency) debit, min(creation) creation
		from `tabGL Entry`
		where {" and ".join(cond)} and posting_date between %(from_date)s and %(to_date)s
		group by party_type, party, posting_date, voucher_type, voucher_no, account_currency
		order by posting_date, creation""",
		filters,
		as_dict=True,
	)
	items = get_invoice_items(
		list({g.voucher_no for g in gl if g.voucher_type in ("Sales Invoice", "Purchase Invoice")})
	)
	komment = get_komments(gl)
	kassa = dict(
		frappe.get_all(
			"Payment Entry",
			filters={"name": ["in", [g.voucher_no for g in gl] or [""]]},
			fields=["name", "mode_of_payment"],
			as_list=True,
		)
	)
	# Начисление (xizmat): kategoriya, miqdor, narx - tovar qatori kabi ko'rsatiladi va jamlanadi
	nachislenie = {
		n.journal_entry: frappe._dict(item_name=n.kategoriya, qty=n.qty, uom="", rate=n.rate)
		for n in frappe.get_all(
			"Nachislenie",
			filters={"journal_entry": ["in", [g.voucher_no for g in gl] or [""]], "docstatus": 1},
			fields=["journal_entry", "kategoriya", "qty", "rate"],
		)
	}
	out = {}
	for g in gl:
		v = "sum" if g.currency == company_currency else "usd"
		lines = items.get(g.voucher_no) or (
			[nachislenie[g.voucher_no]] if g.voucher_no in nachislenie else []
		)
		tavsif = ", ".join(tovar_qatori(i) for i in lines)
		if not tavsif:
			izoh = komment.get(g.voucher_no) or ""
			if izoh.startswith("Amount "):  # ERPNext'ning avtomatik izohi
				izoh = ""
			tavsif = " · ".join(
				filter(
					None,
					(item_label(g.voucher_type, flt(g.credit), flt(g.debit)), kassa.get(g.voucher_no), izoh),
				)
			)
		out.setdefault((g.party_type, g.party), []).append(
			{
				"name": f"{g.party_type}|{g.party}|{g.voucher_no}|{g.currency}",
				"indent": 1,
				"sana": g.posting_date,
				"voucher_type": g.voucher_type,
				"voucher_no": g.voucher_no,
				"turi": voucher_label(g.voucher_type),
				"mahsulot": tavsif,
				"lines": lines,
				f"obor_kr_{v}": flt(g.credit),
				f"obor_dt_{v}": flt(g.debit),
			}
		)
	return out


def miqdor(qty) -> str:
	return f"{flt(qty, 3):g}"


def tovar_qatori(i) -> str:
	return " ".join(filter(None, (i.item_name, miqdor(i.qty), i.uom, f"× {flt(i.rate):,.0f}"))).replace(
		",", " "
	)


def mahsulot_jami(children) -> str:
	"""Kontragent qatori: davr ichida jami nima va qancha (masalan «Шебень 120 Куба, Клинец 40 Куба»)."""
	jami = {}
	for child in children:
		for i in child.pop("lines", []):
			key = (i.item_name, i.uom or "")
			jami[key] = jami.get(key, 0) + flt(i.qty)
	return ", ".join(f"{name} {miqdor(qty)} {uom}".strip() for (name, uom), qty in jami.items())


def blank(rows):
	"""Nol kataklar bo'sh ko'rinsin (jadvaldagi kabi)."""
	for r in rows:
		for f in AMOUNT_FIELDS:
			if abs(flt(r.get(f))) < 0.005:
				r[f] = None
	return rows


def get_summary(t):
	"""«Общая задолженность»: davr oxiridagi jami kredit va debet qoldiqlari."""

	def card(label, field, cur_field, indicator):
		return {
			"label": label,
			"value": flt(t.get(field)),
			"datatype": "Currency",
			"currency": t.get(cur_field),
			"indicator": indicator if abs(flt(t.get(field))) >= 0.005 else "Gray",
		}

	out = [
		card(_("Кредит Сум (биз қарздормиз)"), "kon_kr_sum", "cur_sum", "Red"),
		card(_("Дебет Сум (бизга қарздор)"), "kon_dt_sum", "cur_sum", "Green"),
	]
	if flt(t.get("kon_kr_usd")) or flt(t.get("kon_dt_usd")):
		out += [
			card(_("Кредит $"), "kon_kr_usd", "cur_usd", "Red"),
			card(_("Дебет $"), "kon_dt_usd", "cur_usd", "Green"),
		]
	return out


def akt_link(filters, party_type, party):
	field = PARTY_FIELD.get(party_type)
	if not field:
		return PARTY_LABELS.get(party_type, "")
	query = urlencode(
		{
			"company": filters.company,
			field: party,
			"from_date": str(filters.from_date),
			"to_date": str(filters.to_date),
		}
	)
	return (
		f'<a href="/desk/query-report/Akt Sverka?{query}" style="color: var(--blue-500)">'
		f"📊 {_('Акт Сверка')}</a>"
	)
