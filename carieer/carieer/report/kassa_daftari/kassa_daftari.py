# Kassa daftari ("Kassa kirim-chiqim (hammasi)"): firmaning BARCHA pul harakatlari bitta ro'yxatda -
# Kassa hujjatlari, Sotuv to'lovlari, Firmalararo to'lovlar, xaridga to'lovlar.
# Har qatorda: qaysi kassa, kirim / chiqim, kimga / kimdan, NIMA UCHUN (qaysi mahsulot / sotuv / izoh) va qoldiq.
# Manba DDS bilan bir xil (kassa hisoblaridagi GL), shuning uchun summalar doim mos keladi.

import frappe
from frappe import _
from frappe.utils import escape_html, flt

from carieer.carieer.report.common import bold, prepare
from carieer.carieer.report.dds.dds import get_data as get_dds_data
from carieer.carieer.report.firmalararo_qarzlar.firmalararo_qarzlar import items_text
from carieer.utils import get_kassa_info


def execute(filters=None):
	filters = prepare(filters, period="month")
	rows, _expense, opening, closing = get_dds_data(filters)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	if filters.get("mode_of_payment"):
		currency = get_kassa_info(filters.mode_of_payment, filters.company).currency or currency
	kassa_of = kassa_names(filters.company)
	purpose = get_purposes(rows)

	data = [{"posting_date": filters.from_date, "nima": bold(_("Davr boshidagi qoldiq")), "qoldiq": opening, "currency": currency}]
	balance = flt(opening)
	kirim = chiqim = 0.0
	for r in rows:
		k, c = flt(r["kirim"]), flt(r["chiqim"])
		balance += k - c
		kirim += k
		chiqim += c
		data.append(
			{
				"posting_date": r["posting_date"],
				"kassa": kassa_of.get(r["account"], r["account"]),
				"kirim": k or None,
				"chiqim": c or None,
				"qoldiq": balance,
				"kim": who(r),
				"nima": escape_html(purpose.get((r["voucher_type"], r["voucher_no"])) or r.get("kategoriya") or r.get("remarks") or ""),
				"hujjat_turi": r["voucher_type"],
				"hujjat": r["voucher_no"],
				"currency": currency,
			}
		)
	data.append(
		{
			"nima": bold(_("Davr oxiridagi qoldiq")),
			"kirim": kirim,
			"chiqim": chiqim,
			"qoldiq": balance,
			"currency": currency,
		}
	)
	summary = [
		{"label": _("Boshida"), "value": opening, "datatype": "Currency", "currency": currency, "indicator": "Blue"},
		{"label": _("Kirim"), "value": kirim, "datatype": "Currency", "currency": currency, "indicator": "Green"},
		{"label": _("Chiqim"), "value": chiqim, "datatype": "Currency", "currency": currency, "indicator": "Red"},
		{
			"label": _("Oxirida") if balance >= 0 else _("Kassa qarzi"),
			"value": abs(balance),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue" if balance >= 0 else "Red",
		},
	]
	return get_columns(), data, None, None, summary


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency", "width": 135}
	return [
		{"label": _("Sana"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Kassa"), "fieldname": "kassa", "fieldtype": "Data", "width": 140},
		{"label": _("Kirim"), "fieldname": "kirim", **cur},
		{"label": _("Chiqim"), "fieldname": "chiqim", **cur},
		{"label": _("Qoldiq"), "fieldname": "qoldiq", **cur, "width": 145},
		{"label": _("Kimdan / kimga"), "fieldname": "kim", "fieldtype": "Data", "width": 190},
		{"label": _("Nima uchun"), "fieldname": "nima", "fieldtype": "Data", "width": 360},
		{"label": "", "fieldname": "hujjat_turi", "fieldtype": "Data", "hidden": 1},
		{"label": _("Hujjat"), "fieldname": "hujjat", "fieldtype": "Dynamic Link", "options": "hujjat_turi", "width": 150},
		{"label": _("Valyuta"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def kassa_names(company) -> dict:
	out = {}
	for m in frappe.db.sql(
		"""select a.default_account, a.parent from `tabMode of Payment Account` a
		join `tabMode of Payment` m on m.name = a.parent where a.company = %s order by m.enabled desc""",
		company,
		as_dict=True,
	):
		out.setdefault(m.default_account, m.parent)
	return out


def who(r) -> str:
	text = r.get("description") or ""
	for suffix in (" (Приход)", " (Расход)"):
		text = text.replace(suffix, "")
	if r.get("category") == "transfer":
		return _("Kassadan kassaga")
	return text


def get_purposes(rows) -> dict:
	"""Har bir pul harakati nima uchun: Sotuv / xarid tovarlari, Firmalararo to'lov izohi, Kassa kategoriyasi."""
	out = {}
	pe = list({r["voucher_no"] for r in rows if r["voucher_type"] == "Payment Entry"})
	je = list({r["voucher_no"] for r in rows if r["voucher_type"] == "Journal Entry"})
	if pe:
		refs = frappe.get_all(
			"Payment Entry Reference",
			filters={"parent": ["in", pe], "reference_doctype": ["in", ["Sales Invoice", "Purchase Invoice"]]},
			fields=["parent", "reference_doctype", "reference_name", "allocated_amount"],
		)
		texts = {}
		for dt in ("Sales Invoice", "Purchase Invoice"):
			names = [r.reference_name for r in refs if r.reference_doctype == dt]
			texts.update(items_text(dt, names))
			field = "sales_invoice" if dt == "Sales Invoice" else "purchase_invoice"
			for s in frappe.get_all("Sotuv", {field: ["in", names or [""]], "docstatus": 1}, ["name", field]):
				texts[s[field]] = f"{s.name}: {texts.get(s[field], '')}"
		by_pe = {}
		for r in refs:
			by_pe.setdefault(r.parent, []).append(texts.get(r.reference_name) or r.reference_name)
		info = {
			p.name: p
			for p in frappe.get_all("Payment Entry", {"name": ["in", pe]}, ["name", "reference_no", "payment_type", "mode_of_payment"])
		}
		ft = {
			f.name: f
			for f in frappe.get_all(
				"Firmalararo Tolov",
				{"name": ["in", [p.reference_no for p in info.values() if p.reference_no] or [""]]},
				["name", "izoh", "tolovchi_firma", "oluvchi_firma"],
			)
		}
		for name, p in info.items():
			parts = []
			f = ft.get(p.reference_no)
			if f:
				parts.append(_("Firmalararo to'lov {0} → {1}").format(f.tolovchi_firma, f.oluvchi_firma))
			if by_pe.get(name):
				parts.append(_("tovar uchun: {0}").format("; ".join(by_pe[name])))
			elif f:
				parts.append(_("avans (tovar hali olinmagan)"))
			if f and f.izoh:
				parts.append(f.izoh)
			if parts:
				out[("Payment Entry", name)] = " · ".join(parts)
	for linked in (pe, je):
		if not linked:
			continue
		for k in frappe.get_all(
			"Kassa",
			{"docstatus": 1, "linked_entry": ["in", linked]},
			["linked_doctype", "linked_entry", "kategoriya", "izoh", "party_name"],
		):
			key = (k.linked_doctype, k.linked_entry)
			parts = dict.fromkeys(filter(None, (k.kategoriya, k.izoh, out.get(key))))
			out[key] = " · ".join(parts)
	return out
