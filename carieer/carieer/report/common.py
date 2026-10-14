"""Hisobotlar uchun umumiy yordamchilar (filtr standart qiymatlari, kontragent, firma ruxsati).

Hisobot filtrlari JS'da emas, hisobot JSON'ida (Report -> Filters) turadi. JS'dagi kabi "yil boshi" yoki
"joriy firma" ni JSON'da yozib bo'lmaydi, shuning uchun bo'sh qolgan filtrlar shu yerda to'ldiriladi.
"""

import frappe
from frappe import _
from frappe.utils import escape_html, flt, get_first_day, get_year_start, getdate, today

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


def kontragent_turi(party_type: str, party: str) -> str:
	"""Jadvaldagi «Тип Контрагента»: Клиент, Поставщик, Сотрудник, Прочие лица, Налог.
	Прочие лица / Налог - kontragent guruhidan (setup_karer -> KONTRAGENT_GURUHLARI)."""
	group_field = {"Customer": "customer_group", "Supplier": "supplier_group"}.get(party_type)
	group = None
	if group_field:
		cache = frappe.flags.setdefault("carieer_party_group", {})
		if (party_type, party) not in cache:
			cache[(party_type, party)] = frappe.db.get_value(party_type, party, group_field)
		group = cache[(party_type, party)]
	if group in ("Прочие лица", "Налог"):
		return group
	return {"Customer": "Клиент", "Supplier": "Поставщик", "Employee": "Сотрудник"}.get(party_type, party_type)


# Jadvaldagi kontragent turlari («Диспетчер!S»). Filtr: bo'sh yoki «Все» - hammasi.
TURI_OPTIONS = "\nВсе\nКлиент\nПоставщик\nПрочие лица\nНалог\nСотрудник"
_LEGACY_TURI = {
	"Customer": "Клиент",
	"Mijozlar": "Клиент",
	"Supplier": "Поставщик",
	"Ta'minotchilar": "Поставщик",
	"Employee": "Сотрудник",
	"Xodimlar": "Сотрудник",
}


def normalize_turi(value) -> str:
	"""Filtr qiymati -> jadvaldagi tur ('' = hammasi). Eski qiymatlar (Customer, Mijozlar ...) ham qabul qilinadi."""
	value = _LEGACY_TURI.get(value, value) or ""
	return "" if value == "Все" else value


def party_types_for_turi(turi: str) -> tuple:
	"""Kontragent turi qaysi ERPNext party_type'larda bo'lishi mumkin."""
	return {
		"Клиент": ("Customer",),
		"Поставщик": ("Supplier",),
		"Сотрудник": ("Employee",),
		"Прочие лица": ("Customer", "Supplier"),
		"Налог": ("Customer", "Supplier"),
	}.get(turi, ("Customer", "Supplier", "Employee"))


def turi_ok(turi: str, party_type: str, party: str) -> bool:
	return not turi or kontragent_turi(party_type, party) == turi


def usd_rate(company: str, date, cache: dict) -> float:
	"""Kun bo'yicha USD kursi (Currency Exchange) - jadvaldagi «Курс» / «Сумма $» ustunlari uchun. Yo'q bo'lsa 0."""
	from erpnext.setup.utils import get_exchange_rate

	currency = frappe.get_cached_value("Company", company, "default_currency")
	if currency == "USD":
		return 1.0
	if date not in cache:
		cache[date] = flt(get_exchange_rate("USD", currency, date)) if frappe.db.exists("Currency", "USD") else 0
	return cache[date]


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


def party_condition(parties):
	"""[(party_type, party), ...] -> GL Entry uchun SQL sharti va qiymatlari."""
	if not parties:
		return "1=0", {}
	cond, values = [], {}
	for i, (pt, p) in enumerate(parties):
		cond.append(f"(party_type=%(pt{i})s and party=%(p{i})s)")
		values[f"pt{i}"], values[f"p{i}"] = pt, p
	return "(" + " or ".join(cond) + ")", values


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
