# Qarzlarimiz: firma KIMGA qancha qarzdor, NIMA olgan va QACHON.
# Ta'minotchilar (o'zimizning ikkinchi firmamiz ham - masalan Karer'dan olingan beton), xodimlar.
# Har bir kreditor ostida - qarzni tashkil qilgan hujjatlar: sana, nima olindi (tovar, miqdor × narx), qancha
# to'landi, qancha qoldi, necha kun bo'ldi. Mijozlardan olingan avans (tovar berishimiz kerak) - alohida kartochka.
# Hisob-kitob «Qarzdorlik» hisoboti bilan bir xil (GL, FIFO).

import frappe
from frappe import _
from frappe.utils import escape_html, flt, fmt_money

from carieer.carieer.report.common import bold, prepare
from carieer.carieer.report.qarzdorlik import qarzdorlik as qz
from carieer.utils import get_internal_company

SECTIONS = (("Supplier", _("Ta'minotchilarga")), ("Employee", _("Xodimlarga")))


def execute(filters=None):
	filters = prepare(filters)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	data, parties = [], []
	for party_type, label in SECTIONS:
		f = frappe._dict(filters, party_type=party_type, ichki_firma=1)
		rows, found = qz.get_data(f, only_debt=True)
		rows = [r for r in rows if r.get("party") or r.get("indent") == 1]  # «ЖАМИ» qatorlari olib tashlanadi
		if not rows:
			continue
		for p in found:
			p.party_type = party_type
			p.ichki = get_internal_company(party_type, p.party)
		ichki = {p.party for p in found if p.ichki}
		for r in rows:
			if r.get("party") in ichki:
				r["izoh"] = _("o'zimizning firma") + (" · " + r["izoh"] if r.get("izoh") else "")
		data.append({"nomi": bold(label), "indent": 0})
		data += [{**r, "indent": (r.get("indent") or 0) + 1} for r in rows]
		parties += found

	totals = {}
	for p in parties:
		t = totals.setdefault(p.currency, {"jami": 0.0, "tolandi": 0.0, "qoldiq": 0.0, "d21": 0.0})
		for k in t:
			t[k] += flt(p.get(k))
	for cur, t in totals.items():
		data.append({"nomi": bold(_("JAMI QARZIMIZ")), "currency": cur, "indent": 0, **t})
	return get_columns(), data, get_message(parties, filters, currency), None, get_summary(parties, filters, currency)


def get_columns():
	cols = qz.get_columns(frappe._dict(party_type="Supplier"))
	labels = {
		"nomi": _("Kimga qarzmiz / nima oldik"),
		"jami": _("Oldik (tovar, xizmat)"),
		"tolandi": _("To'ladik"),
		"qoldiq": _("Qarzimiz"),
	}
	for c in cols:
		if c["fieldname"] in labels:
			c["label"] = labels[c["fieldname"]]
	return cols


def get_summary(parties, filters, currency):
	mine = [p for p in parties if p.currency == currency]

	def card(label, value, indicator):
		return {"label": label, "value": value, "datatype": "Currency", "currency": currency, "indicator": indicator}

	out = [
		card(_("Jami qarzimiz"), sum(p.qoldiq for p in mine), "Red"),
		card(_("O'zimizning firmaga"), sum(p.qoldiq for p in mine if p.ichki), "Orange"),
		card(_("Ta'minotchilarga"), sum(p.qoldiq for p in mine if p.party_type == "Supplier" and not p.ichki), "Orange"),
		card(_("21 kundan eski"), sum(flt(p.d21) for p in mine), "Red"),
	]
	# mijoz oldindan pul bergan, tovar hali berilmagan - bu ham bizning majburiyatimiz
	f = frappe._dict(filters, party_type="Customer")
	_rows, customers = qz.get_data(f)
	avans = -sum(p.qoldiq for p in customers if p.qoldiq < 0 and p.currency == currency)
	if avans:
		out.append(card(_("Mijozlar avansi (tovar berishimiz kerak)"), avans, "Blue"))
	return out


def get_message(parties, filters, currency):
	date = frappe.format(filters.to_date, "Date")
	if not parties:
		return f"<div style='margin:4px 0 12px;color:var(--text-muted)'>{escape_html(_('{0} holatiga hech kimga qarzimiz yo‘q').format(date))}</div>"
	lines = []
	for p in sorted(parties, key=lambda p: -p.qoldiq)[:6]:
		open_docs = [d for d in p.docs if d.left > 0.005]
		oldest = open_docs[0].row.posting_date if open_docs else None
		kim = escape_html(p.nomi) + (f" <span style='color:var(--text-muted)'>({escape_html(_('o‘zimizning firma'))})</span>" if p.ichki else "")
		lines.append(
			_("<b>{0}</b> ga {1} qarzmiz: {2} ta hujjat, eng eskisi {3} ({4} kun)").format(
				kim,
				fmt_money(p.qoldiq, 0, p.currency),
				len(open_docs),
				frappe.format(oldest, "Date") if oldest else "—",
				p.kun,
			)
		)
	total = sum(p.qoldiq for p in parties if p.currency == currency)
	headline = escape_html(_("{0} holatiga jami qarzimiz: {1}").format(date, fmt_money(total, 0, currency)))
	items = "".join(f"<li style='margin:2px 0'>{line}</li>" for line in lines)
	hint = escape_html(_("Har bir kreditor ostida - nima olganimiz, qachon, qancha to'laganimiz va qancha qolgani."))
	return f"""
<div style="margin:4px 0 12px;padding:12px 14px;border:1px solid var(--border-color);border-radius:8px">
	<div style="font-size:15px;font-weight:600;color:var(--red-600, #e03636)">{headline}</div>
	<ul style="margin:6px 0 4px;padding-left:18px;font-size:13px">{items}</ul>
	<div style="color:var(--text-muted);font-size:12px">{hint}</div>
</div>"""
