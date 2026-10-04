"""Hisobotlar uchun umumiy yordamchilar (filtr standart qiymatlari, kontragent, firma ruxsati).

Hisobot filtrlari JS'da emas, hisobot JSON'ida (Report -> Filters) turadi. JS'dagi kabi "yil boshi" yoki
"joriy firma" ni JSON'da yozib bo'lmaydi, shuning uchun bo'sh qolgan filtrlar shu yerda to'ldiriladi.
"""

import frappe
from frappe import _
from frappe.utils import escape_html, get_first_day, get_year_start, getdate, today

from carieer.permissions import check_report_company

PARTY_FILTERS = (("customer", "Customer"), ("supplier", "Supplier"), ("employee", "Employee"))
PARTY_LABELS = {
	"Customer": _("Mijoz"),
	"Supplier": _("Ta'minotchi"),
	"Employee": _("Xodim"),
	"Shareholder": _("Ta'sischi"),
}


def prepare(filters, period: str = "month", need_company: bool = True) -> frappe._dict:
	"""filters: firma (ruxsat tekshiriladi), from_date (oy yoki yil boshi), to_date (bugun)."""
	filters = frappe._dict(filters or {})
	filters.to_date = getdate(filters.get("to_date") or today())
	if not filters.get("from_date"):
		filters.from_date = (
			get_year_start(filters.to_date) if period == "year" else get_first_day(filters.to_date)
		)
	filters.from_date = getdate(filters.from_date)
	if filters.from_date > filters.to_date:
		frappe.throw(_("«Dan» sanasi «Gacha» sanasidan katta"))
	if need_company:
		check_report_company(filters)
	return filters


def resolve_party(filters) -> bool:
	"""Mijoz / Ta'minotchi / Xodim filtrlaridan bittasi -> party_type, party."""
	chosen = [(dt, filters.get(f)) for f, dt in PARTY_FILTERS if filters.get(f)]
	if len(chosen) > 1:
		frappe.throw(_("Faqat bitta kontragentni tanlang (Mijoz, Ta'minotchi yoki Xodim)"))
	if chosen:
		filters.party_type, filters.party = chosen[0]
		return True
	return False


def bold(text) -> str:
	return f"<b>{escape_html(str(text or ''))}</b>"


def blank_zeros(rows: list[dict], fields) -> list[dict]:
	"""Bo'sh / nol raqamli kataklar bo'sh ko'rinsin (Frappe None'ni bo'sh, yo'q kalitni 0 deb chiqaradi)."""
	for r in rows:
		for f in fields:
			v = r.get(f)
			if v is None or (isinstance(v, int | float) and abs(v) < 0.005):
				r[f] = None
	return rows
