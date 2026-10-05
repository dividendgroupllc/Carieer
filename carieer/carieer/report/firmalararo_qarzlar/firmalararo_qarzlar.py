# Firmalararo Qarzlar: o'zimizning firmalar bir-biriga qancha qarzdor va nima uchun - bitta qarashda.
#
# Har bir firma juftligi (masalan Eko Beton ↔ Eko Karer) FAQAT BIR MARTA chiqadi. Bitta voqea ikkala kitobda ham
# bor (sotuv: sotuvchida Sales Invoice + xaridorda Purchase Invoice; to'lov: ikki Payment Entry), shuning uchun
# ular bitta qatorga birlashtiriladi va «Tekshiruv» ustunida ikkala kitob mos kelishi ko'rsatiladi.
# «Biz / ular» yo'q - hamma joyda firma nomi: «Sotuv: Eko Karer → Eko Beton», «Eko Karer Eko Betonga qarzdor».
#
# Kitobdagi qoldiq: ichki mijoz (Customer.is_internal_customer) va ichki ta'minotchi (Supplier.is_internal_supplier)
# bo'yicha GL (debet - kredit). Musbat -> boshqa firma bizga qarzdor, manfiy -> biz unga qarzdormiz.
#
# Yuqorida: xulosa kartochkalari (kim kimga qancha qarzdor) va «kim nima berdi» jadvali (tovar / pul).

import frappe
from frappe import _
from frappe.utils import escape_html, flt, fmt_money, get_first_day, getdate, today

from carieer.carieer.report.common import bold
from carieer.permissions import check_report_company, get_allowed_companies

TOVAR, PUL, BOSHQA = "tovar", "pul", "boshqa"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.to_date = getdate(filters.get("to_date") or today())
	filters.from_date = getdate(filters.get("from_date") or get_first_day(filters.to_date))
	if filters.from_date > filters.to_date:
		frappe.throw(_("«Dan» sanasi «Gacha» sanasidan katta"))
	if get_allowed_companies() or filters.get("company"):
		check_report_company(filters)

	pairs = get_pairs(filters)
	data, summary, messages = [], [], []
	for a, b in pairs:
		pair = Pair(a, b, filters)
		if not pair.events:
			continue
		data += pair.rows(with_header=len(pairs) > 1)
		summary += pair.summary()
		messages.append(pair.message())

	if not pairs:
		messages.append(
			_("Ichki firmalar topilmadi (Customer «Is Internal Customer» / Supplier «Is Internal Supplier»).")
		)
	elif not data:
		messages.append(_("{0} gacha firmalar o'rtasida hech qanday hisob-kitob yo'q.").format(fdate(filters.to_date)))
	return get_columns(), data, "".join(messages), None, summary


# ------------------------------------------------------------------ juftliklar
def get_pairs(filters):
	"""(A, B) juftliklari, har biri bir marta. Firma tanlangan bo'lsa u doim chapda (A) turadi."""
	companies = sorted(internal_companies() | set(frappe.get_all("Company", pluck="name")))
	pairs = []
	for i, a in enumerate(companies):
		for b in companies[i + 1 :]:
			if filters.get("company") and filters.company not in (a, b):
				continue
			if filters.get("boshqa_firma") and filters.boshqa_firma not in (a, b):
				continue
			if not (internal_parties(b) or internal_parties(a)):
				continue
			pairs.append((b, a) if filters.get("company") == b else (a, b))
	return pairs


def internal_companies():
	return {
		c
		for c in frappe.get_all("Customer", {"is_internal_customer": 1}, pluck="represents_company")
		+ frappe.get_all("Supplier", {"is_internal_supplier": 1}, pluck="represents_company")
		if c
	}


def other_companies(company):
	return sorted(c for c in internal_companies() if c != company)


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
	"""company kitobida: other firma bizga qancha qarzdor (manfiy - biz unga qarzdormiz).
	Firmalararo To'lov formasi ham ishlatadi."""
	cond, values = party_condition(internal_parties(other))
	return flt(
		frappe.db.sql(
			f"""select sum(debit) - sum(credit) from `tabGL Entry`
			where company=%(company)s and posting_date<=%(to_date)s and is_cancelled=0 and {cond}""",
			{"company": company, "to_date": to_date, **values},
		)[0][0]
	)


def book_entries(company, other, to_date):
	"""company kitobidagi other firma bilan bo'lgan barcha yozuvlar (hujjat bo'yicha yig'ilgan)."""
	cond, values = party_condition(internal_parties(other))
	return frappe.db.sql(
		f"""select posting_date, voucher_type, voucher_no, sum(debit) - sum(credit) as amount,
			max(remarks) as remarks, min(creation) as creation
		from `tabGL Entry`
		where company=%(company)s and posting_date<=%(to_date)s and is_cancelled=0 and {cond}
		group by posting_date, voucher_type, voucher_no
		having abs(sum(debit) - sum(credit)) >= 0.005
		order by posting_date, creation""",
		{"company": company, "to_date": to_date, **values},
		as_dict=True,
	)


# ------------------------------------------------------------------ bitta juftlik
class Pair:
	"""A va B firmalari. Ishora: musbat = B A'ga qarzdor bo'ldi (A tovar / pul berdi)."""

	def __init__(self, a, b, filters):
		self.a, self.b, self.filters = a, b, filters
		self.currency = frappe.get_cached_value("Company", a, "default_currency")
		self.events = self.load_events()

	# ---------------------------------------------------------- ma'lumot
	def load_events(self):
		entries = [(self.a, e, flt(e.amount)) for e in book_entries(self.a, self.b, self.filters.to_date)]
		entries += [(self.b, e, -flt(e.amount)) for e in book_entries(self.b, self.a, self.filters.to_date)]
		keys = event_keys([e for _book, e, _s in entries])
		events = {}
		for book, e, s in entries:
			key = keys.get((e.voucher_type, e.voucher_no)) or (e.voucher_type, e.voucher_no)
			ev = events.get(key)
			if not ev:
				ev = events[key] = frappe._dict(
					key=key,
					posting_date=e.posting_date,
					creation=e.creation,
					amounts={},
					first=(book, e),
					vouchers=[],
				)
			ev.posting_date = min(ev.posting_date, e.posting_date)
			ev.creation = min(ev.creation, e.creation)
			ev.amounts[book] = flt(ev.amounts.get(book)) + s
			ev.vouchers.append((book, e))
		out = sorted(events.values(), key=lambda ev: (ev.posting_date, ev.creation))
		details = get_details([e for ev in out for _book, e in ev.vouchers], keys)
		for ev in out:
			book, e = ev.first
			ev.amount = flt(ev.amounts.get(self.a, ev.amounts.get(self.b)), 2)
			ev.turi, ev.kind = self.describe(book, e)
			ev.detail = details.get(ev.key) or details.get((e.voucher_type, e.voucher_no)) or frappe._dict()
		return out

	def describe(self, book, e):
		"""Voqea nomi (firma nomlari bilan) va turi (tovar / pul / boshqa)."""
		other = self.b if book == self.a else self.a
		raw = flt(e.amount)  # shu kitobda: musbat = other bizga qarzdor bo'ldi
		if e.voucher_type == "Sales Invoice":
			if raw >= 0:
				return _("Sotuv: {0} → {1}").format(book, other), TOVAR
			return _("Qaytarildi: {0} → {1}").format(other, book), TOVAR
		if e.voucher_type == "Purchase Invoice":
			if raw <= 0:
				return _("Sotuv: {0} → {1}").format(other, book), TOVAR
			return _("Qaytarildi: {0} → {1}").format(book, other), TOVAR
		if e.voucher_type == "Payment Entry":
			if raw > 0:
				return _("Pul: {0} → {1}").format(book, other), PUL
			return _("Pul: {0} → {1}").format(other, book), PUL
		return _("Hisob-kitob ({0})").format(_(e.voucher_type)), BOSHQA

	# ---------------------------------------------------------- hisob
	def book_total(self, book, upto=None):
		return flt(
			sum(
				flt(ev.amounts.get(book))
				for ev in self.events
				if book in ev.amounts and (upto is None or ev.posting_date < upto)
			),
			2,
		)

	def kim_qarz(self, value):
		value = flt(value, 2)
		if value > 0:
			return _("{0} {1}ga qarzdor").format(self.b, self.a)
		if value < 0:
			return _("{0} {1}ga qarzdor").format(self.a, self.b)
		return _("Qarz yo'q")

	def tekshiruv(self, ev):
		a, b = ev.amounts.get(self.a), ev.amounts.get(self.b)
		if a is None:
			return _("⚠ faqat {0} kitobida").format(self.b)
		if b is None:
			return _("⚠ faqat {0} kitobida").format(self.a)
		if abs(flt(a) - flt(b)) >= 0.01:
			return _("⚠ farq: {0} / {1}").format(self.money(a), self.money(b))
		return _("✔ ikkala firmada")

	def money(self, value, precision=0):
		return fmt_money(abs(flt(value)), precision, self.currency)

	# ---------------------------------------------------------- jadval
	def rows(self, with_header=False):
		from_date = self.filters.from_date
		rows = []
		if with_header:
			rows.append(self.row(turi=bold(f"{self.a} ↔ {self.b}"), kind="header"))
		opening = sum(ev.amount for ev in self.events if ev.posting_date < from_date)
		if flt(opening, 2):
			rows.append(
				self.row(
					posting_date=from_date,
					turi=_("Davr boshiga qoldiq"),
					kind="opening",
					tafsilot=_("{0} gacha bo'lgan hisob-kitoblar natijasi").format(fdate(from_date)),
					qoldiq=abs(opening),
					kim_qarz=self.kim_qarz(opening),
				)
			)
		running = opening
		for ev in self.events:
			if ev.posting_date < from_date:
				continue
			running += ev.amount
			d = ev.detail
			book, e = ev.first
			rows.append(
				self.row(
					posting_date=ev.posting_date,
					turi=ev.turi,
					kind=ev.kind,
					hujjat_turi=d.doctype or e.voucher_type,
					hujjat=d.name or e.voucher_no,
					tafsilot=d.text or (e.remarks or "")[:120],
					summa=abs(ev.amount),
					qoldiq=abs(running),
					kim_qarz=self.kim_qarz(running),
					tekshiruv=self.tekshiruv(ev),
				)
			)
		rows.append(
			self.row(
				turi=bold(_("Yakuniy qoldiq")),
				kind="total",
				tafsilot=_("{0} holatiga").format(fdate(self.filters.to_date)),
				qoldiq=abs(running),
				kim_qarz=bold(self.kim_qarz(running)),
			)
		)
		return rows

	def row(self, **kw):
		row = dict.fromkeys(("summa", "qoldiq"))  # bo'sh kataklar «0.00» emas, bo'sh ko'rinsin
		row.update(kw, currency=self.currency)
		if row.get("qoldiq") is not None and abs(flt(row["qoldiq"])) < 0.005 and kw.get("kind") != "total":
			row["qoldiq"] = None
		return row

	# ---------------------------------------------------------- xulosa
	def final(self):
		return flt(sum(ev.amount for ev in self.events), 2)

	def summary(self):
		final = self.final()
		out = [
			{
				"value": abs(final),
				"label": self.kim_qarz(final) if final else _("{0} ↔ {1}: qarz yo'q").format(self.a, self.b),
				"datatype": "Currency",
				"currency": self.currency,
				"indicator": "Red" if final else "Green",
			}
		]
		period = [ev for ev in self.events if ev.posting_date >= self.filters.from_date]
		for kind, label in ((TOVAR, _("Davrda sotildi (tovar)")), (PUL, _("Davrda to'landi (pul)"))):
			out.append(
				{
					"value": sum(abs(ev.amount) for ev in period if ev.kind == kind),
					"label": label,
					"datatype": "Currency",
					"currency": self.currency,
					"indicator": "Blue",
				}
			)
		diff = flt(self.book_total(self.a) - self.book_total(self.b), 2)
		if diff:
			out.append(
				{
					"value": abs(diff),
					"label": _("⚠ Kitoblar mos emas ({0} / {1})").format(self.a, self.b),
					"datatype": "Currency",
					"currency": self.currency,
					"indicator": "Orange",
				}
			)
		return out

	def message(self):
		"""«Kim nima berdi» jadvali: qarz qayerdan kelib chiqqani bir qarashda ko'rinadi."""
		gave = {self.a: {TOVAR: 0, PUL: 0, BOSHQA: 0}, self.b: {TOVAR: 0, PUL: 0, BOSHQA: 0}}
		for ev in self.events:
			giver = self.a if ev.amount > 0 else self.b
			gave[giver][ev.kind] += abs(ev.amount)
		final = self.final()
		if final > 0:
			creditor, debtor = self.a, self.b
		else:
			creditor, debtor = self.b, self.a

		label_td = "<td style='padding:4px 16px 4px 0'>{0}</td>"
		num_td = "<td style='text-align:right;padding:4px 12px'>{0}</td>"

		def cell(value, strong=False):
			text = escape_html(self.money(value)) if flt(value) else "—"
			return num_td.format(f"<b>{text}</b>" if strong else text)

		labels = ((TOVAR, _("Tovar berdi (sotuv)")), (PUL, _("Pul to'ladi")), (BOSHQA, _("Boshqa hisob-kitob")))
		body = "".join(
			f"<tr>{label_td.format(escape_html(label))}{cell(gave[creditor][kind])}{cell(gave[debtor][kind])}</tr>"
			for kind, label in labels
			if kind != BOSHQA or gave[creditor][kind] or gave[debtor][kind]
		)
		body += (
			f"<tr style='border-top:1px solid var(--border-color)'>"
			f"{label_td.format('<b>' + escape_html(_('Jami berdi')) + '</b>')}"
			f"{cell(sum(gave[creditor].values()), True)}{cell(sum(gave[debtor].values()), True)}</tr>"
		)
		head = (
			f"<tr style='color:var(--text-muted)'>{label_td.format('')}"
			f"{num_td.format(escape_html(f'{creditor} → {debtor}'))}"
			f"{num_td.format(escape_html(f'{debtor} → {creditor}'))}</tr>"
		)
		if final:
			headline = _("{0} {1}ga {2} qarzdor").format(debtor, creditor, self.money(final))
			why = _(
				"{0} {1}ga {2} ko'proq bergan. {1} bu qarzni tovar berib yoki pul qaytarib yopadi."
			).format(creditor, debtor, self.money(final))
			color = "var(--red-600, #e03636)"
		else:
			headline = _("{0} va {1} o'rtasida qarz yo'q").format(self.a, self.b)
			why = _("Ikkala firma bir-biriga teng qiymat bergan.")
			color = "var(--green-600, #2f9e44)"
		return f"""
<div style="margin:4px 0 12px;padding:12px 14px;border:1px solid var(--border-color);border-radius:8px;
	background:var(--card-bg, transparent)">
	<div style="font-size:15px;font-weight:600;color:{color}">{escape_html(headline)}
		<span style="font-weight:400;color:var(--text-muted);font-size:13px">
		· {escape_html(_("{0} holatiga").format(fdate(self.filters.to_date)))}</span></div>
	<div style="color:var(--text-muted);font-size:13px;margin:2px 0 8px">{escape_html(why)}</div>
	<table style="border-collapse:collapse;font-size:13px">{head}{body}</table>
</div>"""


# ------------------------------------------------------------------ voqealarni birlashtirish
def event_keys(entries):
	"""Ikkala kitobdagi bir voqeani bitta kalitga bog'laydi:
	Sotuv (Sales Invoice + Purchase Invoice), Firmalararo To'lov (2 ta Payment Entry), firmalararo jurnal."""
	by_type = {}
	for e in entries:
		by_type.setdefault(e.voucher_type, set()).add(e.voucher_no)
	keys = {}
	si, pi = list(by_type.get("Sales Invoice", ())), list(by_type.get("Purchase Invoice", ()))
	if si:
		for s in frappe.get_all("Sotuv", {"docstatus": 1, "sales_invoice": ["in", si]}, ["name", "sales_invoice"]):
			keys[("Sales Invoice", s.sales_invoice)] = ("Sotuv", s.name)
		for name in si:
			keys.setdefault(("Sales Invoice", name), ("Sales Invoice", name))
	if pi:
		for s in frappe.get_all(
			"Sotuv", {"docstatus": 1, "purchase_invoice": ["in", pi]}, ["name", "purchase_invoice"]
		):
			keys[("Purchase Invoice", s.purchase_invoice)] = ("Sotuv", s.name)
		for p in frappe.get_all(
			"Purchase Invoice", {"name": ["in", pi]}, ["name", "inter_company_invoice_reference"]
		):
			ref = p.inter_company_invoice_reference
			if ("Purchase Invoice", p.name) not in keys and ref:
				keys[("Purchase Invoice", p.name)] = keys.get(("Sales Invoice", ref)) or ("Sales Invoice", ref)
	pe = list(by_type.get("Payment Entry", ()))
	if pe:
		for p in frappe.get_all("Payment Entry", {"name": ["in", pe]}, ["name", "reference_no"]):
			if p.reference_no and frappe.db.exists("Firmalararo Tolov", p.reference_no):
				keys[("Payment Entry", p.name)] = ("Firmalararo Tolov", p.reference_no)
	je = list(by_type.get("Journal Entry", ()))
	if je:
		for j in frappe.get_all("Journal Entry", {"name": ["in", je]}, ["name", "inter_company_journal_entry_reference"]):
			ref = j.inter_company_journal_entry_reference
			keys[("Journal Entry", j.name)] = ("Journal Entry", min(j.name, ref) if ref else j.name)
	return keys


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


def get_details(entries, keys):
	"""Har bir voqea uchun asl hujjat (Sotuv / Firmalararo To'lov) va tushunarli izoh. Kalit - event_keys natijasi."""
	by_type = {}
	for e in entries:
		by_type.setdefault(e.voucher_type, set()).add(e.voucher_no)
	out = {}

	def put(voucher_type, voucher_no, /, **kw):
		key = keys.get((voucher_type, voucher_no)) or (voucher_type, voucher_no)
		d = out.setdefault(key, frappe._dict())
		for k, v in kw.items():
			if v and not d.get(k):
				d[k] = v

	for doctype in ("Sales Invoice", "Purchase Invoice"):
		names = list(by_type.get(doctype, ()))
		for name, text in items_text(doctype, names).items():
			put(doctype, name, text=text)
	for doctype, field in (("Sales Invoice", "sales_invoice"), ("Purchase Invoice", "purchase_invoice")):
		names = list(by_type.get(doctype, ()))
		if not names:
			continue
		for s in frappe.get_all(
			"Sotuv", {"docstatus": 1, field: ["in", names]}, ["name", field, "mashina_raqami"]
		):
			d = out.get(("Sotuv", s.name))
			if d and s.mashina_raqami and s.mashina_raqami not in (d.text or ""):
				d.text = f"{d.text or ''} · {s.mashina_raqami}"
			put(doctype, s[field], doctype="Sotuv", name=s.name)

	pe = list(by_type.get("Payment Entry", ()))
	if pe:
		ft_names = set()
		for p in frappe.get_all("Payment Entry", {"name": ["in", pe]}, ["name", "mode_of_payment", "reference_no"]):
			key = keys.get(("Payment Entry", p.name))
			if key and key[0] == "Firmalararo Tolov":
				ft_names.add(key[1])
			else:
				put("Payment Entry", p.name, text=_("Kassa: {0}").format(p.mode_of_payment) if p.mode_of_payment else _("To'lov"))
		for ft in frappe.get_all(
			"Firmalararo Tolov",
			{"name": ["in", list(ft_names)]},
			["name", "tolovchi_kassa", "oluvchi_kassa", "summa", "valyuta", "currency", "izoh"],
		):
			parts = [f"{ft.tolovchi_kassa} → {ft.oluvchi_kassa}"]
			if ft.valyuta and ft.valyuta != ft.currency:
				parts.append(fmt_money(ft.summa, 2, ft.valyuta))
			if ft.izoh:
				parts.append(ft.izoh)
			out[("Firmalararo Tolov", ft.name)] = frappe._dict(
				doctype="Firmalararo Tolov", name=ft.name, text=" · ".join(parts)[:160]
			)

	je = list(by_type.get("Journal Entry", ()))
	if je:
		for j in frappe.get_all("Journal Entry", {"name": ["in", je]}, ["name", "user_remark"]):
			put("Journal Entry", j.name, doctype="Journal Entry", name=j.name, text=(j.user_remark or _("Jurnal yozuvi"))[:120])
	return out


def fdate(value):
	return frappe.format(value, "Date")


def get_columns():
	return [
		{"fieldname": "posting_date", "label": _("Sana"), "fieldtype": "Date", "width": 100},
		{"fieldname": "turi", "label": _("Nima bo'ldi"), "fieldtype": "Data", "width": 240},
		{"fieldname": "hujjat_turi", "label": _("Hujjat turi"), "fieldtype": "Data", "hidden": 1},
		{
			"fieldname": "hujjat",
			"label": _("Hujjat"),
			"fieldtype": "Dynamic Link",
			"options": "hujjat_turi",
			"width": 140,
		},
		{"fieldname": "tafsilot", "label": _("Tafsilot"), "fieldtype": "Data", "width": 260},
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
		{"fieldname": "kim_qarz", "label": _("Kim kimga qarzdor"), "fieldtype": "Data", "width": 230},
		{"fieldname": "tekshiruv", "label": _("Tekshiruv"), "fieldtype": "Data", "width": 160},
		{"fieldname": "kind", "label": "kind", "fieldtype": "Data", "hidden": 1},
		{
			"fieldname": "currency",
			"label": _("Valyuta"),
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
	]
