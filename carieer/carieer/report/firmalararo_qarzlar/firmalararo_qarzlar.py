# Firmalararo Qarzlar: zavod firmalari (Karer <-> Beton) bir-biriga qancha qarz va qarz nimadan kelib chiqqan.
# Har bir firma o'z hisobida boshqa firmani ichki mijoz (Customer) va ichki ta'minotchi (Supplier) sifatida yuritadi
# (install.setup_firmalararo). Ko'rinish ERPNext General Ledger («Group by Party») uslubida, har firma juftligi bir guruh:
#   «Qarzdor -> Kreditor» sarlavhasi, Бошланғич қолдиқ, hujjatlar (Дебет / Кредит / Қолдиқ, tovarlar), Жами, Якуний қолдиқ.
# Asosiy hisob - kreditor firma kitobi (qarz unga tegishli), shuning uchun qarz bir marta sanaladi.
# Qarzdor firma kitobidagi juft hujjat yonida ko'rsatiladi: hisob-fakturalar ERPNext inter_company_invoice_reference
# orqali, to'lov va boshqa yozuvlar - sana va summa bo'yicha moslanadi. Jufti yo'q hujjat - farq sababi.

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from carieer.carieer.report.common import bold, items_text
from carieer.permissions import get_allowed_companies

INVOICES = ("Sales Invoice", "Purchase Invoice")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.to_date = getdate(filters.get("to_date") or today())
	filters.from_date = getdate(filters.from_date) if filters.get("from_date") else None
	data, summary = get_data(filters)
	return get_columns(), data, None, None, summary


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency", "width": 130}
	return [
		{"label": _("Сана"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Ҳужжат тури"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 230},
		{
			"label": _("Ҳужжат №"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 165,
		},
		{"label": _("Дебет (қарз ошди)"), "fieldname": "debit", **cur},
		{"label": _("Кредит (тўланди)"), "fieldname": "credit", **cur},
		{"label": _("Қолдиқ"), "fieldname": "balance", **cur, "width": 140},
		{"label": _("Товарлар"), "fieldname": "tovarlar", "fieldtype": "Data", "width": 280},
		{
			"label": _("Қарздордаги ҳужжат"),
			"fieldname": "mirror_no",
			"fieldtype": "Dynamic Link",
			"options": "mirror_type",
			"width": 165,
		},
		{"label": _("Қарздор ҳисобида"), "fieldname": "mirror_amount", **cur, "width": 140},
		{"label": _("Ҳолат"), "fieldname": "holat", "fieldtype": "Data", "width": 190},
		{"label": _("Изоҳ"), "fieldname": "komment", "fieldtype": "Data", "width": 240},
		{"label": "", "fieldname": "mirror_type", "fieldtype": "Data", "hidden": 1},
		{"label": "", "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


# ---------------------------------------------------------------- ma'lumot
def internal_parties(company: str, other: str) -> list[tuple[str, str]]:
	"""company hisobida other firmani ifodalovchi ichki mijoz va ta'minotchi: [(party_type, party), ...]."""
	out = []
	for doctype, flag in (("Customer", "is_internal_customer"), ("Supplier", "is_internal_supplier")):
		names = frappe.get_all(doctype, filters={flag: 1, "represents_company": other}, pluck="name")
		allowed = [
			n
			for n in names
			if frappe.db.exists("Allowed To Transact With", {"parent": n, "parenttype": doctype, "company": company})
		]
		out += [(doctype, n) for n in (allowed or names)]
	return out


def ledger(company: str, other: str, to_date, sign: int) -> list[frappe._dict]:
	"""company hisobidagi other bilan hisob-kitob, hujjat bo'yicha. value = other'ning bizga qarzi qanchaga oshdi
	(sign=1: debet - kredit) yoki company'ning other'ga qarzi qanchaga oshdi (sign=-1: kredit - debet)."""
	parties = internal_parties(company, other)
	if not parties:
		return []
	cond = " or ".join("(party_type=%s and party=%s)" for _p in parties)
	values = [company, to_date] + [x for p in parties for x in p]
	rows = frappe.db.sql(
		f"""select posting_date, voucher_type, voucher_no, sum(debit) - sum(credit) net, min(creation) creation
		from `tabGL Entry`
		where company=%s and is_cancelled=0 and posting_date<=%s and ({cond})
		group by posting_date, voucher_type, voucher_no
		having abs(sum(debit) - sum(credit)) >= 0.005
		order by posting_date, creation""",
		values,
		as_dict=True,
	)
	for r in rows:
		r.value = flt(sign * flt(r.net), 2)
	return rows


def invoice_refs(vouchers: list[str]) -> dict[str, str]:
	"""Hisob-faktura -> boshqa firmadagi juftining nomi (ERPNext inter_company_invoice_reference)."""
	out = {}
	if not vouchers:
		return out
	for dt in INVOICES:
		for name, ref in frappe.db.sql(
			f"select name, inter_company_invoice_reference from `tab{dt}` where name in %s", [vouchers]
		):
			if ref:
				out[name] = ref
	return out


def match(main: list, mirror: list) -> list[tuple]:
	"""Ikki tomon yozuvlarini juftlaydi: [(main_row | None, mirror_row | None, how), ...]."""
	refs = invoice_refs([r.voucher_no for r in main + mirror if r.voucher_type in INVOICES])
	free = list(mirror)
	out = []
	for m in main:
		pair, how = None, None
		if m.voucher_type in INVOICES:
			for c in free:
				if c.voucher_type in INVOICES and (refs.get(m.voucher_no) == c.voucher_no or refs.get(c.voucher_no) == m.voucher_no):
					pair, how = c, "ref"
					break
		else:
			# to'lov / provodka: avval aynan shu sana va summa, keyin faqat summa
			for same_date in (True, False):
				pair = next(
					(
						c
						for c in free
						if c.voucher_type not in INVOICES
						and abs(c.value - m.value) < 0.01
						and (not same_date or c.posting_date == m.posting_date)
					),
					None,
				)
				if pair:
					how = "sum"
					break
		if pair:
			free.remove(pair)
		out.append((m, pair, how))
	out += [(None, c, None) for c in free]
	out.sort(key=lambda t: ((t[0] or t[1]).posting_date, (t[0] or t[1]).creation))
	return out


def sotuv_map(vouchers: list[str]) -> dict[str, frappe._dict]:
	"""Hisob-faktura (Karer Sales Invoice yoki Beton'dagi firmalararo xarid) -> Sotuv (nomi, mashina, izoh)."""
	out = {}
	if not vouchers:
		return out
	for r in frappe.db.sql(
		"""select name, sales_invoice, firmalararo_xarid, mashina_raqami, izoh from `tabSotuv`
		where docstatus=1 and (sales_invoice in %(v)s or firmalararo_xarid in %(v)s)""",
		{"v": vouchers},
		as_dict=True,
	):
		for key in (r.sales_invoice, r.firmalararo_xarid):
			if key:
				out[key] = r
	return out


def komments(vouchers: list[str]) -> dict[str, str]:
	"""Kassa izohi (to'lovlar) va provodka izohi."""
	out = {}
	if not vouchers:
		return out
	for name, izoh in frappe.db.sql(
		"select name, user_remark from `tabJournal Entry` where name in %s", [vouchers]
	):
		if izoh:
			out[name] = izoh
	for name, izoh in frappe.db.sql(
		"select linked_entry, izoh from `tabKassa` where docstatus=1 and linked_entry in %s", [vouchers]
	):
		if izoh:
			out[name] = izoh
	return out


def get_data(filters):
	companies = sorted(set(frappe.get_all("Zavod", pluck="company")))
	allowed = set(get_allowed_companies() or [])
	pairs = [
		(a, b)
		for i, a in enumerate(companies)
		for b in companies[i + 1 :]
		if not allowed or a in allowed or b in allowed
	]
	data = []
	total = farq_total = 0.0
	mismatched = 0
	for a, b in pairs:
		# kreditor (qarz unga tegishli) - asosiy hisob; qarz yo'q bo'lsa alifbo tartibida
		main = ledger(a, b, filters.to_date, 1)
		if sum(r.value for r in main) < 0:
			a, b = b, a
			main = ledger(a, b, filters.to_date, 1)
		mirror = ledger(b, a, filters.to_date, -1)
		rows, stats = pair_rows(a, b, main, mirror, filters)
		data += rows
		total += abs(stats["saldo"])
		farq_total += abs(stats["farq"])
		mismatched += stats["mismatched"]
	return data, get_summary(data, total, farq_total, mismatched)


def dc(value: float) -> dict:
	"""Qarz o'zgarishi -> Дебет (oshdi) / Кредит (kamaydi)."""
	value = flt(value, 2)
	return {"debit": value if value > 0 else None, "credit": -value if value < 0 else None}


def row_holat(m, c, how) -> str:
	if not m:
		return _("⚠ Кредитор ҳисобида йўқ")
	if not c:
		return _("⚠ Қарздор ҳисобида йўқ")
	if abs(m.value - c.value) >= 0.01:
		return _("⚠ Суммалар фарқ қилади")
	return _("✓ Мос") if how == "ref" else _("✓ Мос (сана/сумма бўйича)")


def pair_rows(creditor: str, debtor: str, main: list, mirror: list, filters):
	currency = frappe.get_cached_value("Company", creditor, "default_currency")
	invoices = [r for r in main + mirror if r.voucher_type in INVOICES]
	tovarlar = {}
	for dt in INVOICES:
		tovarlar.update(items_text(dt, [r.voucher_no for r in invoices if r.voucher_type == dt]))
	sotuvlar = sotuv_map([r.voucher_no for r in invoices])
	izoh = komments([r.voucher_no for r in main + mirror])

	rows = []
	balance = opening = opening_mirror = 0.0
	total_debit = total_credit = 0.0
	mismatched = 0
	for m, c, how in match(main, mirror):
		value = m.value if m else 0.0
		mvalue = c.value if c else 0.0
		balance += value
		base = m or c
		if filters.from_date and base.posting_date < filters.from_date:
			opening += value
			opening_mirror += mvalue
			continue
		holat = row_holat(m, c, how)
		mismatched += holat.startswith("⚠")
		if value > 0:
			total_debit += value
		else:
			total_credit -= value
		sotuv = sotuvlar.get(base.voucher_no) or (sotuvlar.get(c.voucher_no) if c else None)
		komment = izoh.get(base.voucher_no) or (izoh.get(c.voucher_no) if c else None)
		rows.append(
			{
				"posting_date": base.posting_date,
				# kreditor hisobida yo'q bo'lsa - qarzdordagi hujjat turi ko'rinsin (Ҳужжат № bo'sh)
				"voucher_type": base.voucher_type,
				"voucher_no": m.voucher_no if m else None,
				**dc(value),
				"balance": flt(balance, 2),
				"tovarlar": tovarlar.get(base.voucher_no) or (tovarlar.get(c.voucher_no) if c else ""),
				"mirror_type": c.voucher_type if c else None,
				"mirror_no": c.voucher_no if c else None,
				# qarzdor summasi faqat farq bo'lganda (mos bo'lsa takrorlanmaydi)
				"mirror_amount": mvalue if holat.startswith("⚠") and c else None,
				"holat": holat,
				"komment": " · ".join(
					filter(
						None,
						(
							sotuv and _("Сотув {0}").format(sotuv.name),
							sotuv and sotuv.mashina_raqami,
							sotuv and sotuv.izoh,
							komment,
						),
					)
				),
				"currency": currency,
			}
		)

	saldo = flt(sum(r.value for r in main), 2)
	mirror_saldo = flt(sum(r.value for r in mirror), 2)
	farq = flt(saldo - mirror_saldo, 2)
	if abs(saldo) < 0.005 and abs(mirror_saldo) < 0.005:
		title = _("{0} ↔ {1}: қарз йўқ").format(debtor, creditor)
	else:
		title = _("{0} → {1} га қарз").format(debtor, creditor)
	head = [
		{"voucher_type": bold(title), "currency": currency},
		{
			"posting_date": filters.from_date,
			"voucher_type": bold(_("Бошланғич қолдиқ")),
			"balance": flt(opening, 2),
			"mirror_amount": flt(opening_mirror, 2) if abs(opening - opening_mirror) >= 0.01 else None,
			"currency": currency,
		},
	]
	tail = [
		{
			"voucher_type": bold(_("Жами")),
			"debit": flt(total_debit, 2),
			"credit": flt(total_credit, 2),
			"currency": currency,
		},
		{
			"posting_date": filters.to_date,
			"voucher_type": bold(_("Якуний қолдиқ")),
			"balance": saldo,
			"mirror_amount": mirror_saldo,
			"holat": pair_holat(farq, mismatched),
			"currency": currency,
		},
		{},  # guruhlar orasida bo'sh qator
	]
	return [*head, *rows, *tail], {"saldo": saldo, "farq": farq, "mismatched": mismatched}


def pair_holat(farq: float, mismatched: int) -> str:
	if abs(farq) >= 0.01:
		return _("⚠ Фарқ: {0}").format(frappe.format(farq, {"fieldtype": "Currency"}))
	if mismatched:
		return _("⚠ {0} та ҳужжат мос эмас").format(mismatched)
	return _("✓ Икки томон мос")


def get_summary(data, total, farq_total, mismatched):
	if not data:
		return []
	currency = next((r["currency"] for r in data if r.get("currency")), None)
	return [
		{
			"label": _("Жами фирмалараро қарз"),
			"value": total,
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue",
		},
		{
			"label": _("Икки томон ҳисоби фарқи"),
			"value": farq_total,
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green" if farq_total < 0.01 else "Orange",
		},
		{
			"label": _("Мос келмаган ҳужжатлар"),
			"value": mismatched,
			"datatype": "Int",
			"indicator": "Green" if not mismatched else "Orange",
		},
	]
