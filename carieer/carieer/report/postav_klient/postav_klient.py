# Postav Klient ("ПоставКлиент"): har bir kontragentning har oy oxiridagi qoldig'i - oyma-oy ustunlar (kumulyativ).
# Google Sheets'dagi varaq kabi: chapda Тип контрагента (Клиент, Поставщик, Прочие лица, Налог, Сотрудник) va nomi,
# o'ngda oylar. Qoldiq = Кредит - Дебет (firma valyutasida), jadvaldagi ishora bilan:
#   musbat (+) - biz kontragentga qarzdormiz (ta'minotchi tovar bergan / mijoz oldindan to'lagan - avans)
#   manfiy (-) - kontragent bizga qarzdor (mijoz to'lamagan / ta'minotchiga avans berilgan)
# Yuqorida jami: musbat qoldiqlar (kreditorlar), manfiy qoldiqlar (debitorlar) va umumiy.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import (
	bold,
	kontragent_turi,
	normalize_turi,
	party_types_for_turi,
	prepare,
	turi_ok,
)
from carieer.carieer.report.moliya import get_months


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
	turi = normalize_turi(filters.get("turi"))
	filters.party_types = party_types_for_turi(turi)
	rows = frappe.db.sql(
		"""select party_type, party, date_format(posting_date, '%%Y-%%m') ym, sum(credit) - sum(debit) net
		from `tabGL Entry`
		where company = %(company)s and is_cancelled = 0 and posting_date <= %(to_date)s
			and party_type in %(party_types)s and ifnull(party, '') != ''
		group by party_type, party, ym""",
		filters,
		as_dict=True,
	)
	per_party = {}
	for r in rows:
		if turi_ok(turi, r.party_type, r.party):
			per_party.setdefault((r.party_type, r.party), {})[r.ym] = flt(r.net)

	keys = [m.key for m in months]
	data = []
	for (party_type, party), per_month in per_party.items():
		vals = [flt(sum(v for ym, v in per_month.items() if ym <= k), 2) for k in keys]
		if not filters.get("show_zero") and not any(abs(v) >= 0.005 for v in vals):
			continue
		row = {"party_type": party_type, "party": party, "turi": kontragent_turi(party_type, party)}
		row.update({m.fieldname: v for m, v in zip(months, vals, strict=True)})
		data.append(row)
	data.sort(key=lambda r: (r["turi"], r["party"]))

	def total(label, pick):
		return {"turi": bold(label), **{m.fieldname: sum(pick(flt(r[m.fieldname])) for r in data) for m in months}}

	head = [
		total(_("Бизнинг қарз (кредитор, +)"), lambda v: max(v, 0)),
		total(_("Бизга қарз (дебитор, −)"), lambda v: min(v, 0)),
		total(_("Жами"), lambda v: v),
	]
	for r in [*head, *data]:
		for m in months:
			if abs(flt(r.get(m.fieldname))) < 0.005:
				r[m.fieldname] = None
	return [*head, *data] if data else []
