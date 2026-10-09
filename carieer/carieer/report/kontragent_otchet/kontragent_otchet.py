# Kontragent Otchet ("Оборотка контрагентов") - Google Sheets'dagi varaq tuzilishida:
#   har bir kontragent BITTA qatorda: Начальное сальдо | Оборот | Конечное сальдо, har birida
#   Кредит Сум, Дебет Сум, Кредит $, Дебет $ (so'm va dollar yonma-yon), oxirida Сальдо (Д-К).
#   Tepada «Общая задолженность» - yakuniy qoldiqlar jami.
# Kredit qoldiq = biz qarzdormiz (kontragent oldindan to'lagan / biz undan oldik), Debet = kontragent bizdan qarzdor.
# Summalar kontragent hisobi valyutasida: so'm hisobidagilari «Сум» ustunlarida, dollar hisobidagilari «$» ustunlarida.

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import PARTY_LABELS, bold, kontragent_turi, prepare, resolve_party

PARTY_FIELD = {"Customer": "customer", "Supplier": "supplier", "Employee": "employee"}
BOSQICH = (("nach", _("нач.")), ("obor", _("оборот")), ("kon", _("кон.")))
# (ustun qo'shimchasi, valyuta guruhi): sum - firma valyutasi, usd - boshqa valyuta (dollar)
VALYUTA = (("sum", _("Сум")), ("usd", "$"))
AMOUNT_FIELDS = [
	f"{b}_{side}_{v}" for b, _l in BOSQICH for v, _vl in VALYUTA for side in ("kr", "dt")
] + ["saldo_sum", "saldo_usd"]


def execute(filters=None):
	filters = prepare(filters, period="month")
	resolve_party(filters)
	data, totals = get_data(filters)
	return get_columns(), data, None, None, get_summary(totals)


def get_columns():
	cols = [
		{"label": _("Тип"), "fieldname": "turi", "fieldtype": "Data", "width": 95},
		{"label": "", "fieldname": "party_type", "fieldtype": "Data", "hidden": 1},
		{
			"label": _("Контрагент"),
			"fieldname": "party",
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 190,
		},
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
		{"label": _("Сальдо Сум (Д-К)"), "fieldname": "saldo_sum", "fieldtype": "Currency", "options": "cur_sum", "width": 135},
		{"label": _("Сальдо $ (Д-К)"), "fieldname": "saldo_usd", "fieldtype": "Currency", "options": "cur_usd", "width": 120},
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
	if filters.get("party_type"):
		cond.append("party_type = %(party_type)s")
	elif filters.get("turi"):
		filters.party_type = filters.turi
		cond.append("party_type = %(party_type)s")
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
	if data:
		data.append({"turi": bold(_("ЖАМИ")), **totals})
	return blank(data), totals


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
			"indicator": indicator,
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
	return f'<a href="/desk/query-report/Akt Sverka?{query}">{_("Акт сверка")}</a>'
