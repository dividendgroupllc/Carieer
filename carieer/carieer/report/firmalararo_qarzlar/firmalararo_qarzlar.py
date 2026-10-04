# Firmalararo Qarzlar: o'zimizning firmalar bir-biridan qancha qarz (Karer <-> Beton zavod) va nima uchun.
# Har bir firma kitobida ichki mijoz (Customer.is_internal_customer) = boshqa firma bizdan qarzdor,
# ichki yetkazib beruvchi (Supplier.is_internal_supplier) = biz boshqa firmadan qarzdormiz.
# Qoldiq = shu ikki kontragent bo'yicha GL (debet - kredit): musbat -> u bizdan qarz, manfiy -> biz qarzmiz.
# Oddiy jadval: Sana | Operatsiya | Hujjat | Tafsilot | Summa | Qarz qoldig'i | Kim kimdan qarz.

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_first_day, getdate, today

from carieer.carieer.report.common import bold
from carieer.permissions import check_report_company, get_allowed_companies


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.to_date = getdate(filters.get("to_date") or today())
	filters.from_date = getdate(filters.get("from_date") or get_first_day(filters.to_date))
	if get_allowed_companies() or filters.get("company"):
		check_report_company(filters)
	companies = (
		[filters.company]
		if filters.get("company")
		else frappe.get_all("Company", pluck="name", order_by="name")
	)

	pairs = [
		(company, other)
		for company in companies
		for other in other_companies(company)
		if not filters.get("boshqa_firma") or other == filters.boshqa_firma
	]
	data = []
	for company, other in pairs:
		data += get_pair(company, other, filters, with_header=len(pairs) > 1)
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "posting_date", "label": _("Sana"), "fieldtype": "Date", "width": 100},
		{"fieldname": "turi", "label": _("Operatsiya"), "fieldtype": "Data", "width": 125},
		{"fieldname": "hujjat_turi", "label": _("Hujjat turi"), "fieldtype": "Data", "hidden": 1},
		{
			"fieldname": "hujjat",
			"label": _("Hujjat"),
			"fieldtype": "Dynamic Link",
			"options": "hujjat_turi",
			"width": 135,
		},
		{"fieldname": "tafsilot", "label": _("Tafsilot"), "fieldtype": "Data", "width": 330},
		{
			"fieldname": "summa",
			"label": _("Summa"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"fieldname": "qoldiq",
			"label": _("Qarz qoldig'i"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 145,
		},
		{"fieldname": "kim_qarz", "label": _("Kim kimdan qarz"), "fieldtype": "Data", "width": 220},
		{"fieldname": "kind", "label": "kind", "fieldtype": "Data", "hidden": 1},
		{
			"fieldname": "currency",
			"label": _("Valyuta"),
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
	]


def other_companies(company):
	reps = set(
		frappe.get_all("Customer", {"is_internal_customer": 1}, pluck="represents_company")
		+ frappe.get_all("Supplier", {"is_internal_supplier": 1}, pluck="represents_company")
	)
	return sorted(c for c in reps if c and c != company)


def internal_parties(other):
	"""Boshqa firmani bizning kitobda ifodalovchi kontragentlar: [(party_type, party)]."""
	customers = frappe.get_all(
		"Customer", {"is_internal_customer": 1, "represents_company": other}, pluck="name"
	)
	suppliers = frappe.get_all(
		"Supplier", {"is_internal_supplier": 1, "represents_company": other}, pluck="name"
	)
	return [("Customer", c) for c in customers] + [("Supplier", s) for s in suppliers]


def party_condition(parties):
	if not parties:
		return "1=0", {}
	cond, values = [], {}
	for i, (pt, p) in enumerate(parties):
		cond.append(f"(party_type=%(pt{i})s and party=%(p{i})s)")
		values[f"pt{i}"], values[f"p{i}"] = pt, p
	return "(" + " or ".join(cond) + ")", values


def balance(company, other, to_date):
	cond, values = party_condition(internal_parties(other))
	return flt(
		frappe.db.sql(
			f"""select sum(debit) - sum(credit) from `tabGL Entry`
			where company=%(company)s and posting_date<=%(to_date)s and is_cancelled=0 and {cond}""",
			{"company": company, "to_date": to_date, **values},
		)[0][0]
	)


def kim_qarz(balance_value, other):
	if flt(balance_value, 2) > 0:
		return _("{0} bizdan qarz").format(other)
	if flt(balance_value, 2) < 0:
		return _("Biz {0}dan qarzmiz").format(other)
	return _("Qarz yo'q")


def get_pair(company, other, filters, with_header=False):
	currency = frappe.get_cached_value("Company", company, "default_currency")
	cond, values = party_condition(internal_parties(other))
	opening = balance(company, other, add_days(filters.from_date, -1))
	entries = frappe.db.sql(
		f"""select posting_date, voucher_type, voucher_no, sum(debit) - sum(credit) as amount,
			max(remarks) as remarks, min(creation) as creation
		from `tabGL Entry`
		where company=%(company)s and posting_date between %(from_date)s and %(to_date)s and is_cancelled=0 and {cond}
		group by posting_date, voucher_type, voucher_no
		order by posting_date, creation""",
		{"company": company, "from_date": filters.from_date, "to_date": filters.to_date, **values},
		as_dict=True,
	)
	if not entries and not opening:
		return []

	details = get_details(entries)
	rows = []
	if with_header:
		rows.append({"turi": bold(f"{company} ↔ {other}"), "kind": "header", "currency": currency})
	if opening:
		rows.append(
			{
				"posting_date": filters.from_date,
				"turi": _("Boshlang'ich"),
				"kind": "opening",
				"tafsilot": _("Davr boshidagi qarz"),
				"qoldiq": abs(opening),
				"kim_qarz": kim_qarz(opening, other),
				"currency": currency,
			}
		)
	running = opening
	for e in entries:
		amount = flt(e.amount)
		running += amount
		d = details.get(e.voucher_no) or frappe._dict()
		if e.voucher_type == "Sales Invoice":
			turi, kind = _("Biz sotdik"), "berdik"
		elif e.voucher_type == "Purchase Invoice":
			turi, kind = _("Biz oldik"), "oldik"
		else:
			turi, kind = (_("Biz to'ladik"), "tolov") if amount > 0 else (_("Ular to'ladi"), "tolov")
		rows.append(
			{
				"posting_date": e.posting_date,
				"turi": turi,
				"kind": kind,
				"hujjat_turi": d.doctype or e.voucher_type,
				"hujjat": d.name or e.voucher_no,
				"tafsilot": d.text or (e.remarks or "")[:120],
				"summa": abs(amount),
				"qoldiq": abs(running),
				"kim_qarz": kim_qarz(running, other),
				"currency": currency,
			}
		)
	rows.append(
		{
			"turi": bold(_("Yakuniy")),
			"kind": "total",
			"tafsilot": _("{0} sanasiga").format(frappe.format(filters.to_date, "Date")),
			"qoldiq": abs(running),
			"kim_qarz": kim_qarz(running, other),
			"currency": currency,
		}
	)
	return rows


def fmt_qty(qty):
	qty = flt(qty)
	return f"{qty:,.0f}".replace(",", " ") if qty == int(qty) else f"{qty:,.2f}".replace(",", " ")


def items_text(doctype, names):
	"""Hisob-faktura -> "Shagal 30 000 kg × 100, Qum 10 t × 80 000"."""
	out = {}
	if not names:
		return out
	for i in frappe.db.sql(
		f"""select parent, item_name, qty, uom, rate from `tab{doctype} Item`
		where parent in %(names)s order by parent, idx""",
		{"names": names},
		as_dict=True,
	):
		out.setdefault(i.parent, []).append(
			f"{i.item_name} {fmt_qty(i.qty)} {(i.uom or '').lower()} × {fmt_qty(i.rate)}"
		)
	return {k: ", ".join(v) for k, v in out.items()}


def get_details(entries):
	"""Har bir yozuv uchun asl hujjat (Sotuv / Firmalararo To'lov) va tushunarli izoh."""
	by_type = {}
	for e in entries:
		by_type.setdefault(e.voucher_type, []).append(e.voucher_no)
	out = {}
	for doctype in ("Sales Invoice", "Purchase Invoice"):
		names = by_type.get(doctype) or []
		texts = items_text(doctype, names)
		for name in names:
			out[name] = frappe._dict(text=texts.get(name, ""))
	if by_type.get("Sales Invoice"):
		for s in frappe.db.sql(
			"""select name, sales_invoice, mashina_raqami from `tabSotuv` where docstatus=1 and sales_invoice in %(v)s""",
			{"v": by_type["Sales Invoice"]},
			as_dict=True,
		):
			d = out[s.sales_invoice]
			d.update(doctype="Sotuv", name=s.name)
			if s.mashina_raqami:
				d.text = f"{d.text} · {s.mashina_raqami}"
	if by_type.get("Purchase Invoice"):
		for s in frappe.db.sql(
			"""select name, purchase_invoice, mashina_raqami from `tabSotuv` where docstatus=1 and purchase_invoice in %(v)s""",
			{"v": by_type["Purchase Invoice"]},
			as_dict=True,
		):
			d = out[s.purchase_invoice]
			d.update(doctype="Sotuv", name=s.name)
			if s.mashina_raqami:
				d.text = f"{d.text} · {s.mashina_raqami}"
	if by_type.get("Payment Entry"):
		for pe in frappe.db.sql(
			"""select name, mode_of_payment, reference_no from `tabPayment Entry` where name in %(v)s""",
			{"v": by_type["Payment Entry"]},
			as_dict=True,
		):
			d = frappe._dict(
				text=_("Kassa: {0}").format(pe.mode_of_payment) if pe.mode_of_payment else _("To'lov")
			)
			if pe.reference_no and frappe.db.exists("Firmalararo Tolov", pe.reference_no):
				d.update(doctype="Firmalararo Tolov", name=pe.reference_no)
			out[pe.name] = d
	if by_type.get("Journal Entry"):
		for je in frappe.db.sql(
			"""select name, user_remark from `tabJournal Entry` where name in %(v)s""",
			{"v": by_type["Journal Entry"]},
			as_dict=True,
		):
			out[je.name] = frappe._dict(text=(je.user_remark or _("Jurnal yozuvi"))[:120])
	return out
