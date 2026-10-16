# Kontragent Oylik ("Контрагент отчет нев"): har bir kontragent bitta qatorda, oyma-oy harakat - jadvaldagi varaq:
#   Сальдо нач. (Кредит / Дебит) | har oy: Приход, Продажа, Услуга, Деньги Кредит, Деньги Дебит | Сальдо кон.
# Ishora jadvaldagidek (kredit tomoni): Сальдо кон. = нач. + Приход - Продажа + Услуга + Деньги Кр - Деньги Дт;
# musbat - biz qarzdormiz (Кредит), manfiy - kontragent bizdan qarzdor (Дебит).
#   Приход       - Purchase Invoice / Purchase Receipt, Приход ОС
#   Продажа      - Sales Invoice (Sotuv), Sotuv korrektirovkasi
#   Услуга       - Начисление (Закуп услуга +, Продажа услуга -)
#   Деньги Кр/Дт - Payment Entry (Kassa, Sotuv to'lovi): kontragentdan olingan pul / kontragentga berilgan pul
#   Прочие       - boshqa provodkalar (masalan qoldiq kiritish) - bo'lsa alohida ustun, jami doim mos chiqadi
# Manba: GL Entry, summalar firma valyutasida (so'm). Valyuta bo'yicha ajratilgani - «Оборотка Контрагентов».

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import (
	bold,
	kontragent_turi,
	normalize_turi,
	party_types_for_turi,
	prepare,
	resolve_party,
	turi_ok,
)
from carieer.carieer.report.kontragent_otchet.kontragent_otchet import akt_link
from carieer.carieer.report.moliya import get_months

USTUNLAR = (
	("prixod", _("Приход")),
	("prodazha", _("Продажа")),
	("usluga", _("Услуга")),
	("dengi_kr", _("Деньги Кредит")),
	("dengi_dt", _("Деньги Дебит")),
	("prochie", _("Прочие")),
)


def execute(filters=None):
	filters = prepare(filters, period="year")
	resolve_party(filters)
	months = get_months(filters.from_date, filters.to_date)
	data, used = get_data(filters, months)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	return get_columns(months, used, currency), data, None, None, get_summary(data, currency)


def get_columns(months, used, currency):
	money = {"fieldtype": "Currency", "options": currency, "width": 125}
	cols = [
		{"label": _("Тип"), "fieldname": "turi", "fieldtype": "Data", "width": 95},
		{"label": "", "fieldname": "party_type", "fieldtype": "Data", "hidden": 1},
		{
			"label": _("Контрагент"),
			"fieldname": "party",
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 190,
			"sticky": True,
		},
		{"label": _("Акт сверка"), "fieldname": "akt_sverka", "fieldtype": "Data", "width": 95},
		{"label": _("Сальдо кредит"), "fieldname": "nach_kr", **money},
		{"label": _("Сальдо дебит"), "fieldname": "nach_dt", **money},
	]
	for m in months:
		for key, label in USTUNLAR:
			if (m.fieldname, key) in used:
				cols.append({"label": f"{label} ({m.label})", "fieldname": f"{m.fieldname}_{key}", **money})
	cols += [
		{"label": _("Конец сальдо кредит"), "fieldname": "kon_kr", **money},
		{"label": _("Конец сальдо дебит"), "fieldname": "kon_dt", **money},
	]
	return cols


def voucher_kinds(company):
	"""Journal Entry -> ustun: qaysi hujjatdan yaratilgan (Начисление, Приход ОС, Sotuv korrektirovkasi)."""
	kinds = {}
	for doctype, kind in (("Nachislenie", "usluga"), ("Prixod OS", "prixod"), ("Sotuv", "prodazha")):
		for name in frappe.get_all(
			doctype,
			filters={"company": company, "docstatus": 1, "journal_entry": ["is", "set"]},
			pluck="journal_entry",
		):
			kinds[name] = kind
	return kinds


def kind_of(voucher_type, voucher_no, je_kinds):
	if voucher_type in ("Purchase Invoice", "Purchase Receipt"):
		return "prixod"
	if voucher_type == "Sales Invoice":
		return "prodazha"
	if voucher_type == "Payment Entry":
		return "dengi"
	if voucher_type == "Journal Entry":
		return je_kinds.get(voucher_no, "prochie")
	return "prochie"


def get_data(filters, months):
	cond = [
		"company = %(company)s",
		"ifnull(party, '') != ''",
		"is_cancelled = 0",
		"posting_date <= %(to_date)s",
	]
	turi = normalize_turi(filters.get("turi"))
	if filters.get("party_type"):
		cond.append("party_type = %(party_type)s")
	else:
		filters.party_types = party_types_for_turi(turi)
		cond.append("party_type in %(party_types)s")
	if filters.get("party"):
		cond.append("party = %(party)s")
	gl = frappe.db.sql(
		f"""select party_type, party, voucher_type, voucher_no,
			if(posting_date < %(from_date)s, '', date_format(posting_date, '%%Y-%%m')) ym,
			sum(credit) - sum(debit) net, sum(credit) credit, sum(debit) debit
		from `tabGL Entry`
		where {" and ".join(cond)}
		group by party_type, party, voucher_type, voucher_no, ym""",
		filters,
		as_dict=True,
	)
	field_of = {m.key: m.fieldname for m in months}
	je_kinds = voucher_kinds(filters.company)
	parties, used = {}, set()
	for r in gl:
		if not turi_ok(turi, r.party_type, r.party):
			continue
		row = parties.setdefault(
			(r.party_type, r.party), {"party_type": r.party_type, "party": r.party, "_nach": 0.0, "_kon": 0.0}
		)
		row["_kon"] += flt(r.net)
		if not r.ym:
			row["_nach"] += flt(r.net)
			continue
		month = field_of[r.ym]
		kind = kind_of(r.voucher_type, r.voucher_no, je_kinds)
		if kind == "dengi":
			parts = (("dengi_kr", flt(r.credit)), ("dengi_dt", flt(r.debit)))
		elif kind == "prodazha":
			parts = (("prodazha", -flt(r.net)),)  # Продажа ayriladi: debet - kredit
		else:
			parts = ((kind, flt(r.net)),)
		for key, value in parts:
			if abs(value) >= 0.005:
				f = f"{month}_{key}"
				row[f] = row.get(f, 0.0) + value
				used.add((month, key))

	data = []
	for (party_type, party), row in sorted(parties.items(), key=lambda x: (kontragent_turi(*x[0]), x[0][1])):
		nach, kon = row.pop("_nach"), row.pop("_kon")
		moved = any(k.startswith("m_") for k in row)
		if not filters.get("show_zero") and not (moved or abs(nach) >= 0.005 or abs(kon) >= 0.005):
			continue
		row.update(
			turi=kontragent_turi(party_type, party),
			akt_sverka=akt_link(filters, party_type, party),
			nach_kr=max(nach, 0) or None,
			nach_dt=max(-nach, 0) or None,
			kon_kr=max(kon, 0) or None,
			kon_dt=max(-kon, 0) or None,
		)
		data.append(row)
	if data:
		totals = {}
		for r in data:
			for k, v in r.items():
				if k.startswith(("m_", "nach_", "kon_")) and v:
					totals[k] = totals.get(k, 0.0) + flt(v)
		data.insert(0, {"turi": bold(_("Итого")), **totals})
	return data, used


def get_summary(data, currency):
	if not data:
		return []
	t = data[0]
	return [
		{
			"label": _("Конец сальдо кредит (биз қарздормиз)"),
			"value": flt(t.get("kon_kr")),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Red" if flt(t.get("kon_kr")) else "Gray",
		},
		{
			"label": _("Конец сальдо дебит (бизга қарздор)"),
			"value": flt(t.get("kon_dt")),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green" if flt(t.get("kon_dt")) else "Gray",
		},
	]
