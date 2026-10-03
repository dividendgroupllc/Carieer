# Kassa va Qarzlar: bitta sahifada firmaning moliyaviy holati (buxgalter uchun oddiy jadval).
#   1. Kassalar      - har bir kassa / bank hisobida qancha pul bor (o'z valyutasida va so'mda)
#   2. Bizdan qarz   - kim bizdan qarz (debitorlar: mijozlar, ikkinchi firmamiz, xodimlar ...)
#   3. Biz qarzmiz   - biz kimdan qarzmiz (kreditorlar: ta'minotchilar, ikkinchi firmamiz ...)
# Manba: GL Entry (bekor qilinganlarsiz), tanlangan sanagacha.

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from carieer.utils import check_report_company

TURI = {"Customer": _("Mijoz"), "Supplier": _("Ta'minotchi"), "Employee": _("Xodim"), "Shareholder": _("Ta'sischi")}
NOMI_FIELD = {"Customer": "customer_name", "Supplier": "supplier_name", "Employee": "employee_name", "Shareholder": "title"}
ICHKI_FIELD = {"Customer": "is_internal_customer", "Supplier": "is_internal_supplier"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.to_date = getdate(filters.get("to_date") or today())
	check_report_company(filters)
	if not filters.get("company"):
		filters.company = frappe.defaults.get_user_default("Company") or frappe.get_all("Company", pluck="name", limit=1)[0]
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")

	data = []
	data += kassalar(filters, currency)
	debitorlar, kreditorlar = qarzlar(filters, currency)
	data += section(_("Kim bizdan qarz"), debitorlar, _("Jami bizdan qarz"), currency, "debitor")
	data += section(_("Biz kimdan qarzmiz"), kreditorlar, _("Jami biz qarzmiz"), currency, "kreditor")
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "link_doctype", "label": "Link", "fieldtype": "Data", "hidden": 1},
		{"fieldname": "nomi", "label": _("Nomi"), "fieldtype": "Dynamic Link", "options": "link_doctype", "width": 260},
		{"fieldname": "turi", "label": _("Turi"), "fieldtype": "Data", "width": 130},
		{"fieldname": "summa", "label": _("Summa"), "fieldtype": "Currency", "options": "valyuta", "width": 160},
		{"fieldname": "valyuta", "label": _("Valyuta"), "fieldtype": "Link", "options": "Currency", "width": 80},
		{"fieldname": "somda", "label": _("So'mda"), "fieldtype": "Currency", "options": "company_currency", "width": 170},
		{"fieldname": "kind", "label": "kind", "fieldtype": "Data", "hidden": 1},
		{"fieldname": "company_currency", "label": "cc", "fieldtype": "Data", "hidden": 1},
	]


def kassalar(filters, currency):
	rows = frappe.db.sql(
		"""select a.name, a.account_name, a.account_currency, a.account_type,
			sum(gl.debit_in_account_currency) - sum(gl.credit_in_account_currency) as summa,
			sum(gl.debit) - sum(gl.credit) as somda
		from `tabAccount` a
		left join `tabGL Entry` gl on gl.account = a.name and gl.is_cancelled = 0 and gl.posting_date <= %(to_date)s
		where a.company = %(company)s and a.is_group = 0 and a.account_type in ('Cash', 'Bank') and a.disabled = 0
		group by a.name order by a.account_type desc, a.account_name""",
		filters,
		as_dict=True,
	)
	# Hisob -> kassa nomi (to'lov turi), kassir shu nomni biladi
	mop = dict(
		frappe.db.sql(
			"""select default_account, parent from `tabMode of Payment Account` where company = %s""", filters.company
		)
	)
	out = [{"nomi": _("Kassalarda bor pul"), "kind": "section"}]
	jami = 0
	for r in rows:
		if not flt(r.summa, 2) and r.name not in mop:
			continue
		jami += flt(r.somda)
		out.append(
			{
				"link_doctype": "Mode of Payment" if r.name in mop else "Account",
				"nomi": mop.get(r.name) or r.name,
				"turi": _("Naqd kassa") if r.account_type == "Cash" else _("Bank / karta"),
				"summa": flt(r.summa, 2),
				"valyuta": r.account_currency,
				"somda": flt(r.somda, 2),
				"company_currency": currency,
			}
		)
	out.append({"nomi": _("Jami kassalarda"), "kind": "total", "somda": jami, "company_currency": currency})
	return out


def qarzlar(filters, currency):
	balances = frappe.db.sql(
		"""select party_type, party, sum(debit) - sum(credit) as qoldiq
		from `tabGL Entry`
		where company = %(company)s and is_cancelled = 0 and posting_date <= %(to_date)s
			and party_type is not null and party_type != '' and party is not null and party != ''
		group by party_type, party
		having abs(sum(debit) - sum(credit)) >= 0.5
		order by abs(sum(debit) - sum(credit)) desc""",
		filters,
		as_dict=True,
	)
	# Ikkinchi firmamiz kitobda ikki kontragent (ichki mijoz + ichki yetkazib beruvchi) - bitta sof qatorga yig'iladi
	qoldiqlar = {}
	for b in balances:
		key = (b.party_type, b.party, TURI.get(b.party_type, b.party_type))
		ichki = ICHKI_FIELD.get(b.party_type)
		if ichki:
			firma = frappe.db.get_value(b.party_type, b.party, ["represents_company", ichki], as_dict=True) or {}
			if firma.get(ichki) and firma.get("represents_company"):
				key = ("Company", firma["represents_company"], _("O'zimizning firma"))
		qoldiqlar[key] = qoldiqlar.get(key, 0) + flt(b.qoldiq)

	debitorlar, kreditorlar = [], []
	for (link_doctype, nomi, turi), qoldiq in sorted(qoldiqlar.items(), key=lambda x: -abs(x[1])):
		if abs(qoldiq) < 0.5:
			continue
		row = {
			"link_doctype": link_doctype,
			"nomi": nomi,
			"turi": turi,
			"summa": abs(flt(qoldiq, 2)),
			"valyuta": currency,
			"somda": abs(flt(qoldiq, 2)),
			"company_currency": currency,
		}
		(debitorlar if qoldiq > 0 else kreditorlar).append(row)
	return debitorlar, kreditorlar


def section(title, rows, total_label, currency, kind):
	out = [{"nomi": title, "kind": "section"}]
	if not rows:
		out.append({"nomi": _("Yo'q"), "kind": "empty"})
	for r in rows:
		r["kind"] = kind
		out.append(r)
	out.append(
		{"nomi": total_label, "kind": "total", "somda": sum(flt(r["somda"]) for r in rows), "company_currency": currency}
	)
	return out
