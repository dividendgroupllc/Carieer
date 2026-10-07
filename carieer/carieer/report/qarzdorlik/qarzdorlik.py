# Qarzdorlik ("Қарздорликлар"): kim qancha qarz, NIMA UCHUN va qancha vaqtdan beri.
#
# Har bir kontragent - bitta qator: Jami oldi | To'ladi | Qarz | eng eski qarz (kun) | muddat ustunlari.
# Uning ostida (daraxt) - qarzni tashkil qilgan hujjatlar: sana, hujjat (Sotuv, Nachislenie, Kassa ...),
# nima olgani ("Beton 4 t × 490 000 · 01A123BC"), hujjat summasi, to'langan qismi, qolgan qarz, necha kun.
# Avans bo'lsa (oldindan to'lagan) - qaysi to'lov ortib qolgani ko'rsatiladi.
#
# Manba - GL (buxgalteriya daftari): sotuv, nachislenie, kassa, boshlang'ich qoldiq, to'lovlar hammasi hisobga olinadi.
# Taqsimot FIFO: har bir to'lov eng eski to'lanmagan hujjatni yopadi; avans keyingi hujjatlarga ishlatiladi.

import frappe
from frappe import _
from frappe.utils import date_diff, escape_html, flt, fmt_money

from carieer.carieer.report.common import bold, prepare
from carieer.carieer.report.firmalararo_qarzlar.firmalararo_qarzlar import fmt_qty, items_text

BUCKETS = ("d0_7", "d8_14", "d15_21", "d21")
NAME_FIELD = {"Customer": "customer_name", "Supplier": "supplier_name", "Employee": "employee_name"}
TURI = {"Mijozlar": "Customer", "Ta'minotchilar": "Supplier", "Xodimlar": "Employee"}
# ustun nomlari kontragent turiga qarab (kim kimga qarz - aniq bo'lsin)
LABELS = {
	"Customer": (_("Oldi (sotuv, xizmat)"), _("To'ladi"), _("Qarzi (bizga)")),
	"Supplier": (_("Bizga berdi (xarid, xizmat)"), _("Biz to'ladik"), _("Bizning qarz")),
	"Employee": (_("Hisoblandi"), _("Berildi"), _("Bizning qarz")),
}
NUMERIC = ("jami", "tolandi", "qoldiq", *BUCKETS, "kun")


def execute(filters=None):
	filters = prepare(filters)
	filters.party_type = TURI.get(filters.get("turi") or "Mijozlar", "Customer")
	data, parties = get_data(filters)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	return (
		get_columns(filters),
		data,
		get_message(parties, filters, currency),
		None,
		get_summary(parties, filters, currency),
	)


def get_columns(filters):
	jami, tolandi, qoldiq = LABELS[filters.party_type]
	cur = {"fieldtype": "Currency", "options": "currency", "width": 135}
	return [
		{"label": _("Kim / nima uchun"), "fieldname": "nomi", "fieldtype": "Data", "width": 330},
		{"label": "", "fieldname": "party_type", "fieldtype": "Data", "hidden": 1},
		{
			"label": _("Kontragent"),
			"fieldname": "party",
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"hidden": 1,
		},
		{"label": "", "fieldname": "hujjat_turi", "fieldtype": "Data", "hidden": 1},
		{
			"label": _("Hujjat"),
			"fieldname": "hujjat",
			"fieldtype": "Dynamic Link",
			"options": "hujjat_turi",
			"width": 135,
		},
		{"label": _("Sana"), "fieldname": "sana", "fieldtype": "Date", "width": 95},
		{"label": jami, "fieldname": "jami", **cur},
		{"label": tolandi, "fieldname": "tolandi", **cur},
		{"label": qoldiq, "fieldname": "qoldiq", **cur, "width": 145},
		{"label": _("Necha kun"), "fieldname": "kun", "fieldtype": "Int", "width": 85},
		{"label": _("Izoh"), "fieldname": "izoh", "fieldtype": "Data", "width": 230},
		{"label": _("7 кун ичи"), "fieldname": "d0_7", **cur, "width": 115},
		{"label": _("8-14 кун"), "fieldname": "d8_14", **cur, "width": 115},
		{"label": _("15-21 кун"), "fieldname": "d15_21", **cur, "width": 115},
		{"label": _("21 кундан кўп"), "fieldname": "d21", **cur, "width": 125},
		{
			"label": _("Валюта"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"width": 70,
		},
	]


# ------------------------------------------------------------------ ma'lumot
def get_entries(filters):
	cond = [
		"company = %(company)s",
		"party_type = %(party_type)s",
		"is_cancelled = 0",
		"posting_date <= %(to_date)s",
	]
	if filters.get("party"):
		cond.append("party = %(party)s")
	if not filters.get("ichki_firma"):
		# o'zimizning ikkinchi firmamiz - «Firmalararo qarzlar» hisobotida
		table = {"Customer": "Customer", "Supplier": "Supplier"}.get(filters.party_type)
		if table:
			flag = "is_internal_customer" if table == "Customer" else "is_internal_supplier"
			cond.append(f"party not in (select name from `tab{table}` where {flag} = 1)")
	return frappe.db.sql(
		f"""select party, account_currency currency, voucher_type, voucher_no,
			min(posting_date) posting_date, min(creation) creation,
			sum(debit_in_account_currency) - sum(credit_in_account_currency) net, max(remarks) remarks
		from `tabGL Entry` where {" and ".join(cond)}
		group by party, account_currency, voucher_type, voucher_no
		having abs(sum(debit_in_account_currency) - sum(credit_in_account_currency)) >= 0.005
		order by party, account_currency, posting_date, creation""",
		filters,
		as_dict=True,
	)


def fifo(rows, sign):
	"""Xronologik FIFO: qarz oshiruvchi hujjatlar (increases) va to'lovlar (decreases) bir-birini yopadi.
	Qaytaradi: (hujjatlar ro'yxati [har birida paid, left], ortib qolgan to'lovlar [avans])."""
	docs, open_inc, open_dec = [], [], []
	for r in rows:
		amount = sign * flt(r.net)
		if amount > 0:
			doc = frappe._dict(row=r, amount=amount, paid=0.0, left=amount)
			docs.append(doc)
			while doc.left > 0.005 and open_dec:  # oldindan to'langan avans shu hujjatga ishlatiladi
				d = open_dec[0]
				used = min(doc.left, d.left)
				doc.left -= used
				doc.paid += used
				d.left -= used
				if d.left <= 0.005:
					open_dec.pop(0)
			if doc.left > 0.005:
				open_inc.append(doc)
		else:
			dec = frappe._dict(row=r, amount=-amount, left=-amount)
			while dec.left > 0.005 and open_inc:
				doc = open_inc[0]
				used = min(dec.left, doc.left)
				doc.left -= used
				doc.paid += used
				dec.left -= used
				if doc.left <= 0.005:
					open_inc.pop(0)
			if dec.left > 0.005:
				open_dec.append(dec)
	return docs, open_dec


def get_data(filters, only_debt=False):
	"""only_debt: faqat qoldig'i musbat (qarz bor) kontragentlar - «Qarzlarimiz» hisoboti uchun."""
	entries = get_entries(filters)
	sign = 1 if filters.party_type == "Customer" else -1  # ta'minotchi / xodim: biz qarz bo'lsak musbat
	by_party = {}
	for e in entries:
		by_party.setdefault((e.party, e.currency), []).append(e)
	details = get_details(entries, filters.party_type)

	parties = []
	for (party, currency), rows in by_party.items():
		docs, advances = fifo(rows, sign)
		jami = sum(d.amount for d in docs)
		tolandi = sum(sign * -flt(r.net) for r in rows if sign * flt(r.net) < 0)
		qoldiq = flt(sum(sign * flt(r.net) for r in rows), 2)
		if abs(qoldiq) < 0.5 and not filters.get("show_zero"):
			continue
		if only_debt and qoldiq < 0.5:
			continue
		p = frappe._dict(
			party=party,
			currency=currency,
			nomi=frappe.db.get_value(filters.party_type, party, NAME_FIELD[filters.party_type]) or party,
			jami=flt(jami, 2),
			tolandi=flt(tolandi, 2),
			qoldiq=qoldiq,
			kun=0,
			docs=docs,
			advances=advances,
			last_payment=max((r for r in rows if sign * flt(r.net) < 0), key=lambda r: r.posting_date, default=None),
			**{b: 0.0 for b in BUCKETS},
		)
		for d in docs:
			if d.left > 0.005:
				days = max(date_diff(filters.to_date, d.row.posting_date), 0)
				bucket = "d0_7" if days <= 7 else "d8_14" if days <= 14 else "d15_21" if days <= 21 else "d21"
				p[bucket] = flt(p[bucket] + d.left, 2)
				p.kun = max(p.kun, days)
		parties.append(p)

	parties.sort(key=lambda p: (p.currency or "", -p.qoldiq))
	data, totals = [], {}
	for p in parties:
		data.append(party_row(p, filters))
		data += doc_rows(p, details, filters, sign)
		t = totals.setdefault(p.currency, {f: 0.0 for f in ("jami", "tolandi", "qoldiq", *BUCKETS)})
		for f in t:
			t[f] += flt(p[f])
	for currency, t in totals.items():
		data.append({"nomi": bold(_("ЖАМИ")), "currency": currency, "indent": 0, **t})
	for row in data:
		for f in NUMERIC:
			# yo'q kalitni Frappe «0.00» deb ko'rsatadi - bo'sh qolsin
			if row.get(f) is None or abs(flt(row[f])) < 0.005:
				row[f] = None
	return data, parties


def party_row(p, filters):
	open_docs = [d for d in p.docs if d.left > 0.005]
	if p.qoldiq < 0:
		izoh = (
			_("Avans: oldindan to'lagan, tovar olmagan")
			if filters.party_type == "Customer"
			else _("Avans: biz oldindan to'laganmiz")
		)
	elif open_docs:
		izoh = _("{0} ta to'lanmagan hujjat").format(len(open_docs))
	else:
		izoh = ""
	if p.last_payment:
		izoh += (" · " if izoh else "") + _("oxirgi to'lov {0}").format(frappe.format(p.last_payment.posting_date, "Date"))
	return {
		"nomi": bold(p.nomi),
		"party_type": filters.party_type,
		"party": p.party,
		"hujjat_turi": filters.party_type,
		"hujjat": p.party,
		"currency": p.currency,
		"jami": p.jami,
		"tolandi": p.tolandi,
		"qoldiq": p.qoldiq,
		"kun": p.kun,
		"izoh": izoh,
		"indent": 0,
		**{b: p[b] for b in BUCKETS},
	}


def doc_rows(p, details, filters, sign):
	"""Qarzni tashkil qilgan hujjatlar (to'langanlari - faqat «to'langan hujjatlar ham» belgilansa)."""
	rows = []
	for d in p.docs:
		if d.left <= 0.005 and not filters.get("hammasi"):
			continue
		info = details.get((d.row.voucher_type, d.row.voucher_no)) or frappe._dict()
		days = max(date_diff(filters.to_date, d.row.posting_date), 0)
		rows.append(
			{
				"nomi": escape_html(info.text or (d.row.remarks or d.row.voucher_type)[:120]),
				"hujjat_turi": info.doctype or d.row.voucher_type,
				"hujjat": info.name or d.row.voucher_no,
				"sana": d.row.posting_date,
				"currency": p.currency,
				"jami": flt(d.amount, 2),
				"tolandi": flt(d.paid, 2),
				"qoldiq": flt(d.left, 2),
				"kun": days if d.left > 0.005 else None,
				"izoh": _("to'langan") if d.left <= 0.005 else (_("qisman to'langan") if d.paid > 0.005 else _("to'lanmagan")),
				"indent": 1,
			}
		)
	for a in p.advances:
		info = details.get((a.row.voucher_type, a.row.voucher_no)) or frappe._dict()
		rows.append(
			{
				"nomi": escape_html(info.text or (a.row.remarks or a.row.voucher_type)[:120]),
				"hujjat_turi": info.doctype or a.row.voucher_type,
				"hujjat": info.name or a.row.voucher_no,
				"sana": a.row.posting_date,
				"currency": p.currency,
				"tolandi": flt(a.amount, 2),
				"qoldiq": -flt(a.left, 2),
				"izoh": _("avans (hali tovar / xizmat bilan yopilmagan)"),
				"indent": 1,
			}
		)
	return rows


# ------------------------------------------------------------------ hujjat izohlari
def get_details(entries, party_type):
	"""{(voucher_type, voucher_no): {doctype, name, text}} - asl hujjat va oddiy tildagi izoh."""
	by_type = {}
	for e in entries:
		by_type.setdefault(e.voucher_type, set()).add(e.voucher_no)
	out = {}
	si = list(by_type.get("Sales Invoice", ()))
	pi = list(by_type.get("Purchase Invoice", ()))
	for doctype, names in (("Sales Invoice", si), ("Purchase Invoice", pi)):
		texts = items_text(doctype, names)
		for name in names:
			out[(doctype, name)] = frappe._dict(
				text=(_("Xarid: {0}") if doctype == "Purchase Invoice" else _("Sotuv: {0}")).format(
					texts.get(name) or name
				)
			)
	for doctype, field, names in (("Sales Invoice", "sales_invoice", si), ("Purchase Invoice", "purchase_invoice", pi)):
		if not names:
			continue
		for s in frappe.get_all("Sotuv", {"docstatus": 1, field: ["in", names]}, ["name", field, "mashina_raqami"]):
			d = out[(doctype, s[field])]
			d.update(doctype="Sotuv", name=s.name)
			if s.mashina_raqami:
				d.text += f" · {s.mashina_raqami}"

	je = list(by_type.get("Journal Entry", ()))
	if je:
		for j in frappe.get_all("Journal Entry", {"name": ["in", je]}, ["name", "user_remark", "is_opening"]):
			out[("Journal Entry", j.name)] = frappe._dict(
				text=_("Boshlang'ich qoldiq") if j.is_opening == "Yes" else (j.user_remark or _("Jurnal yozuvi"))
			)
		for n in frappe.get_all(
			"Nachislenie",
			{"docstatus": 1, "journal_entry": ["in", je]},
			["name", "journal_entry", "turi", "kategoriya", "qty", "rate", "currency", "izoh"],
		):
			what = n.kategoriya or n.turi
			text = _("Nachislenie: {0} {1} × {2}").format(what, fmt_qty(n.qty), fmt_qty(n.rate))
			if n.izoh:
				text += f" · {n.izoh}"
			out[("Journal Entry", n.journal_entry)] = frappe._dict(doctype="Nachislenie", name=n.name, text=text)

	pe = list(by_type.get("Payment Entry", ()))
	if pe:
		for p in frappe.get_all(
			"Payment Entry", {"name": ["in", pe]}, ["name", "mode_of_payment", "payment_type", "remarks"]
		):
			verb = _("To'lov olindi") if p.payment_type == "Receive" else _("Pul berildi")
			out[("Payment Entry", p.name)] = frappe._dict(
				text=f"{verb} ({p.mode_of_payment})" if p.mode_of_payment else verb
			)
	for linked in (je, pe):
		if not linked:
			continue
		for k in frappe.get_all(
			"Kassa",
			{"docstatus": 1, "linked_entry": ["in", linked]},
			["name", "linked_doctype", "linked_entry", "turi", "mode_of_payment", "kategoriya", "izoh"],
		):
			verb = _("Kassaga kirim") if k.turi == "Kirim" else _("Kassadan berildi")
			parts = dict.fromkeys(filter(None, (f"{verb} ({k.mode_of_payment})", k.kategoriya, k.izoh)))
			out[(k.linked_doctype, k.linked_entry)] = frappe._dict(
				doctype="Kassa", name=k.name, text=" · ".join(parts)
			)
	return out


# ------------------------------------------------------------------ xulosa
def get_summary(parties, filters, currency):
	mine = [p for p in parties if p.currency == currency]
	debt = sum(p.qoldiq for p in mine if p.qoldiq > 0)
	advance = -sum(p.qoldiq for p in mine if p.qoldiq < 0)
	old = sum(p.d21 for p in mine)
	if filters.party_type == "Customer":
		labels = (_("Mijozlar bizga qarz"), _("Mijozlar avansi (biz qarzmiz)"))
	elif filters.party_type == "Supplier":
		labels = (_("Biz ta'minotchilarga qarzmiz"), _("Ta'minotchilarga avans berilgan"))
	else:
		labels = (_("Biz xodimlarga qarzmiz"), _("Xodimlarda (podotchet)"))
	out = [
		{"label": labels[0], "value": debt, "datatype": "Currency", "currency": currency, "indicator": "Red"},
		{"label": _("21 kundan eski qarz"), "value": old, "datatype": "Currency", "currency": currency, "indicator": "Orange"},
		{"label": labels[1], "value": advance, "datatype": "Currency", "currency": currency, "indicator": "Blue"},
		{"label": _("Qarzdorlar soni"), "value": len([p for p in mine if p.qoldiq > 0]), "datatype": "Int", "indicator": "Grey"},
	]
	for cur in sorted({p.currency for p in parties} - {currency}):
		out.append(
			{
				"label": _("Qarz ({0})").format(cur),
				"value": sum(p.qoldiq for p in parties if p.currency == cur and p.qoldiq > 0),
				"datatype": "Currency",
				"currency": cur,
				"indicator": "Red",
			}
		)
	return out


def get_message(parties, filters, currency):
	esc = escape_html
	debtors = sorted((p for p in parties if p.qoldiq > 0), key=lambda p: -p.qoldiq)
	date = frappe.format(filters.to_date, "Date")
	if not parties:
		return f"<div style='margin:4px 0 12px;color:var(--text-muted)'>{esc(_('{0} holatiga qarz yo‘q').format(date))}</div>"
	lines = []
	for p in debtors[:5]:
		open_docs = [d for d in p.docs if d.left > 0.005]
		oldest = open_docs[0].row.posting_date if open_docs else None
		lines.append(
			_("<b>{0}</b> — {1}: {2} ta hujjat, eng eskisi {3} ({4} kun)").format(
				esc(p.nomi),
				fmt_money(p.qoldiq, 0, p.currency),
				len(open_docs),
				frappe.format(oldest, "Date") if oldest else "—",
				p.kun,
			)
		)
	who = {"Customer": _("Mijozlar bizga"), "Supplier": _("Biz ta'minotchilarga"), "Employee": _("Biz xodimlarga")}[
		filters.party_type
	]
	total = sum(p.qoldiq for p in debtors if p.currency == currency)
	headline = _("{0} holatiga: {1} {2} qarz").format(date, who, fmt_money(total, 0, currency))
	items = "".join(f"<li style='margin:2px 0'>{line}</li>" for line in lines)
	hint = esc(_("Har bir kontragent ostida - qarzni tashkil qilgan hujjatlar (nima olgan, qancha to'lagan, qancha qolgan)."))
	return f"""
<div style="margin:4px 0 12px;padding:12px 14px;border:1px solid var(--border-color);border-radius:8px">
	<div style="font-size:15px;font-weight:600">{esc(headline)}</div>
	<ul style="margin:6px 0 4px;padding-left:18px;font-size:13px">{items}</ul>
	<div style="color:var(--text-muted);font-size:12px">{hint}</div>
</div>"""
