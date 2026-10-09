# Postav Klient ("Постав/Клиент"): har bir kontragentning har oy oxiridagi qoldig'i - oyma-oy ustunlar.
# Google Sheets'dagi varaq kabi: chapda Тип контрагента (Клиент, Поставщик, Прочие лица ...) va nomi,
# o'ngda oylar. Qoldiq = Дебет - Кредит (firma valyutasida):
#   musbat  - kontragent bizga qarzdor (mijoz to'lamagan, ta'minotchiga avans bergan)
#   manfiy  - biz unga qarzdormiz (ta'minotchi tovar bergan, mijoz oldindan to'lagan)
# Tepada jami: debitorlar (+), kreditorlar (-), sof qoldiq.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import bold, kontragent_turi, prepare
from carieer.carieer.report.moliya import get_months

TURI = {"Mijozlar": "Customer", "Ta'minotchilar": "Supplier", "Xodimlar": "Employee"}


def execute(filters=None):
	filters = prepare(filters, period="year")
	months = get_months(filters.from_date, filters.to_date)
	return get_columns(months), get_data(filters, months)


def get_columns(months):
	cols = [
		{"label": _("Тип контрагента"), "fieldname": "turi", "fieldtype": "Data", "width": 110},
		{"label": "", "fieldname": "party_type", "fieldtype": "Data", "hidden": 1},
		{
			"label": _("Контрагент"),
			"fieldname": "party",
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 220,
		},
	]
	for m in months:
		cols.append(
			{"label": m.label, "fieldname": m.fieldname, "fieldtype": "Float", "precision": "0", "width": 130}
		)
	return cols


def get_data(filters, months):
	cond = ""
	if filters.get("turi") in TURI:
		filters.party_type = TURI[filters.turi]
		cond = " and party_type = %(party_type)s"
	rows = frappe.db.sql(
		f"""select party_type, party, date_format(posting_date, '%%Y-%%m') ym, sum(debit) - sum(credit) net
		from `tabGL Entry`
		where company = %(company)s and is_cancelled = 0 and posting_date <= %(to_date)s
			and ifnull(party_type, '') != '' and ifnull(party, '') != ''{cond}
		group by party_type, party, ym""",
		filters,
		as_dict=True,
	)
	per_party = {}
	for r in rows:
		per_party.setdefault((r.party_type, r.party), {})[r.ym] = flt(r.net)

	keys = [m.key for m in months]
	data = []
	for (party_type, party), per_month in per_party.items():
		vals = [flt(sum(v for ym, v in per_month.items() if ym <= k), 2) for k in keys]
		if not filters.get("show_zero") and not any(abs(v) >= 0.005 for v in vals):
			continue
		row = {"party_type": party_type, "party": party, "turi": kontragent_turi(party_type, party)}
		row.update({m.fieldname: v for m, v in zip(months, vals)})
		data.append(row)
	data.sort(key=lambda r: (r["turi"], r["party"]))

	def total(label, pick):
		return {"turi": bold(label), **{m.fieldname: sum(pick(flt(r[m.fieldname])) for r in data) for m in months}}

	head = [
		total(_("Бизга қарз (дебитор)"), lambda v: max(v, 0)),
		total(_("Бизнинг қарз (кредитор)"), lambda v: min(v, 0)),
		total(_("Соф қолдиқ"), lambda v: v),
	]
	for r in [*head, *data]:
		for m in months:
			if abs(flt(r.get(m.fieldname))) < 0.005:
				r[m.fieldname] = None
	return [*head, *data] if data else []
