"""Umumiy yordamchi funksiyalar (Karer ilovasi)."""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import flt


def get_firma_sozlama(company: str) -> frappe._dict:
	"""Karer Sozlamalari -> Firmalar jadvalidan shu firma qatorini qaytaradi (bo'lmasa bo'sh dict)."""
	row = frappe.db.get_value(
		"Karer Firma Sozlamasi",
		{"parent": "Karer Sozlamalari", "company": company},
		["*"],
		as_dict=True,
	)
	return row or frappe._dict()


def get_company_currency(company: str) -> str:
	return frappe.get_cached_value("Company", company, "default_currency")


def get_rate(from_currency: str, to_currency: str, date=None) -> float:
	if from_currency == to_currency:
		return 1.0
	from erpnext.setup.utils import get_exchange_rate

	rate = flt(get_exchange_rate(from_currency, to_currency, date))
	if not rate:
		frappe.throw(
			_("{0} -> {1} kursi topilmadi. Currency Exchange ga kurs kiriting.").format(from_currency, to_currency)
		)
	return rate


def validate_warehouse_company(warehouse: str, company: str, label: str = "Ombor"):
	if warehouse and frappe.get_cached_value("Warehouse", warehouse, "company") != company:
		frappe.throw(_("{0} ({1}) {2} firmasiga tegishli emas").format(label, warehouse, company))


@contextmanager
def as_admin():
	"""Firmalararo hujjat ikkinchi firma kitobiga ham yozadi (Sales/Purchase Invoice, Payment Entry), xodimning
	esa u firma hisoblarini o'qishga ruxsati yo'q (User Permission). Shu qism tizim nomidan bajariladi."""
	user = frappe.session.user
	if user == "Administrator":
		yield
		return
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(user)


def validate_not_internal(party_type: str | None, party: str | None, tavsiya: str):
	"""O'zimizning ikkinchi firmamiz oddiy Sotuv / Kassa'da tanlanmasin: u faqat bitta firma kitobiga yoziladi
	va ikki kitob orasida farq paydo bo'ladi. Buning uchun Firmalararo Sotuv / To'lov bor (ikkala kitobga yozadi)."""
	field = {"Customer": "is_internal_customer", "Supplier": "is_internal_supplier"}.get(party_type)
	if field and party and frappe.db.get_value(party_type, party, field):
		frappe.throw(
			_("{0} - bu o'zimizning firmamiz. U bilan hisob-kitobni <b>{1}</b> orqali qiling (ikkala firma kitobiga yoziladi).").format(
				party, tavsiya
			),
			title=_("Ichki firma"),
		)


# ------------------------------------------------------------------ Kategoriya -> hisob
@frappe.whitelist()
def get_kategoriya_account(kategoriya: str | None, company: str | None, root_type: str | None = None) -> str | None:
	"""Kassa Kategoriya -> shu firmadagi hisob (modda). Google Sheets'dagi kabi kassir faqat kategoriyani
	tanlaydi, hisob (hisoblar rejasidagi modda) o'zi qo'yiladi. Hisob nomi = Kategoriya.hisob_nomi yoki
	kategoriya nomi. root_type berilsa (Expense / Income) faqat shu turdagi hisob qaytadi."""
	if not kategoriya or not company:
		return None
	hisob_nomi = frappe.db.get_value("Kassa Kategoriya", kategoriya, "hisob_nomi")
	for account_name in dict.fromkeys(filter(None, (hisob_nomi, kategoriya))):
		filters = {"company": company, "account_name": account_name, "is_group": 0, "disabled": 0}
		if root_type:
			filters["root_type"] = root_type
		account = frappe.db.get_value("Account", filters, "name")
		if account:
			return account
	return None


# ------------------------------------------------------------------ SMS
def send_sms(numbers: list[str], message: str):
	"""Sozlamaga qarab Frappe SMS Settings yoki Eskiz.uz orqali SMS yuboradi (background job ichida chaqiring)."""
	settings = frappe.get_cached_doc("Karer Sozlamalari")
	numbers = [normalize_phone(n) for n in numbers if n]
	if not numbers:
		return
	try:
		if settings.sms_provayder == "Eskiz.uz":
			_send_eskiz(settings, numbers, message)
		else:
			from frappe.core.doctype.sms_settings.sms_settings import _send_sms

			_send_sms(numbers, message, success_msg=False)
	except Exception:
		frappe.log_error(title="Karer SMS yuborilmadi")


def normalize_phone(phone: str) -> str:
	digits = "".join(ch for ch in (phone or "") if ch.isdigit())
	if len(digits) == 9:  # 901234567 -> 998901234567
		digits = "998" + digits
	return digits


def _send_eskiz(settings, numbers, message):
	import requests

	base = "https://notify.eskiz.uz/api"
	token = frappe.cache.get_value("karer_eskiz_token")
	if not token:
		r = requests.post(
			f"{base}/auth/login",
			data={"email": settings.eskiz_email, "password": settings.get_password("eskiz_password")},
			timeout=15,
		)
		r.raise_for_status()
		token = r.json()["data"]["token"]
		frappe.cache.set_value("karer_eskiz_token", token, expires_in_sec=25 * 24 * 3600)

	for number in numbers:
		r = requests.post(
			f"{base}/message/sms/send",
			headers={"Authorization": f"Bearer {token}"},
			data={"mobile_phone": number, "message": message, "from": settings.eskiz_from or "4546"},
			timeout=15,
		)
		if r.status_code == 401:
			frappe.cache.delete_value("karer_eskiz_token")
		r.raise_for_status()


@frappe.whitelist()
def get_firma_defaults(company: str) -> dict:
	"""JS formalar uchun: firma bo'yicha standart omborlar va kassa."""
	row = get_firma_sozlama(company)
	return {
		"company_currency": get_company_currency(company),
		"sotuv_ombori": row.get("sotuv_ombori"),
		"qazish_ombori": row.get("qazish_ombori"),
		"beton_xomashyo_ombori": row.get("beton_xomashyo_ombori"),
		"beton_ombori": row.get("beton_ombori"),
		"yoqilgi_ombori": row.get("yoqilgi_ombori"),
		"mode_of_payment": row.get("mode_of_payment"),
	}


@frappe.whitelist()
def get_item_warehouse(item_code: str, company: str) -> str | None:
	"""Sotuv uchun: tovar qaysi omborda bor bo'lsa o'sha ombor (Beton -> Beton ombori, Shag'al -> Karer ombori).
	Avval Karer Sozlamalari'dagi firma omborlari, keyin qoldig'i eng ko'p ombor, bo'lmasa Item'ning standart ombori."""
	row = get_firma_sozlama(company)
	# BOM bilan ishlab chiqariladigan tovar (beton) avval Beton omboridan, qolganlari Karer omboridan
	is_produced = frappe.db.exists("BOM", {"item": item_code, "company": company, "is_active": 1, "docstatus": 1})
	order = ("beton_ombori", "sotuv_ombori") if is_produced else ("sotuv_ombori", "qazish_ombori", "beton_ombori")
	preferred = [row.get(f) for f in order if row.get(f)]
	bins = [
		b.warehouse
		for b in frappe.get_all(
			"Bin",
			filters={"item_code": item_code, "actual_qty": [">", 0]},
			fields=["warehouse"],
			order_by="actual_qty desc",
		)
		if frappe.get_cached_value("Warehouse", b.warehouse, "company") == company
	]
	return (
		next((wh for wh in preferred if wh in bins), None)
		or (bins[0] if bins else None)
		or frappe.db.get_value("Item Default", {"parent": item_code, "company": company}, "default_warehouse")
	)


@frappe.whitelist()
def get_exchange_rate_for(from_currency: str, to_currency: str, date: str | None = None) -> float:
	return get_rate(from_currency, to_currency, date)


def get_allowed_companies() -> list[str]:
	"""Xodim faqat qaysi firma(lar)ni ko'ra oladi (User Permission -> Company). Bo'sh ro'yxat = cheklov yo'q."""
	from frappe.core.doctype.user_permission.user_permission import get_permitted_documents

	return get_permitted_documents("Company")


def check_report_company(filters: frappe._dict):
	"""Hisobotlar SQL bilan yozilgan (ruxsatlar avtomatik qo'llanmaydi): firmaga bog'langan xodim
	firmani bo'sh qoldirsa - o'z firmasi qo'yiladi, boshqa firmani tanlasa - xato."""
	allowed = get_allowed_companies()
	if not allowed:
		return
	if not filters.get("company"):
		filters.company = allowed[0]
	elif filters.company not in allowed:
		frappe.throw(_("{0} firmasi ma'lumotlarini ko'rishga ruxsatingiz yo'q").format(filters.company), frappe.PermissionError)


def hide_foreign_balance(company: str | None) -> bool:
	"""Kassa qoldig'i brauzerdan to'g'ridan-to'g'ri so'ralganda (get_kassa_info) faqat o'z firmasiniki ko'rsatiladi.
	Ichki chaqiruvlar (Firmalararo To'lov, Sotuv) ikkinchi firma kassasi bilan ishlaydi - ularga ta'sir qilmaydi."""
	allowed = get_allowed_companies()
	if not allowed or company in allowed:
		return False
	return str(frappe.form_dict.get("cmd") or "").endswith("get_kassa_info")


KARER_ROLES = {"Karer Operator", "Karer Kassir", "Karer Menejer", "Karer xodimi"}
BETON_ROLES = {"Beton Operator", "Beton Kassir", "Beton Menejer", "Beton zavod xodimi"}


def get_user_firma(user: str | None = None) -> str | None:
	"""Xodim qaysi zavodniki: "Karer" / "Beton". Admin yoki ikkala zavod xodimi bo'lsa None."""
	roles = set(frappe.get_roles(user))
	if "System Manager" in roles:
		return None
	karer, beton = bool(roles & KARER_ROLES), bool(roles & BETON_ROLES)
	if karer == beton:
		return None
	return "Karer" if karer else "Beton"


def has_app_permission() -> bool:
	"""Bosh sahifadagi ilova ikonkasi: ikkala firma xodimlari va System Manager."""
	return bool((KARER_ROLES | BETON_ROLES | {"System Manager"}) & set(frappe.get_roles()))


FIRMA_KORINISHI = {
	"Karer": ("Karer", "/assets/carieer/karer-logo.svg"),
	"Beton": ("Beton Zavod", "/assets/carieer/beton-logo.svg"),
}


def boot_session(bootinfo):
	"""Beton xodimi ilova nomini va sidebar sarlavhasini "Beton Zavod", karer xodimi "Karer" deb ko'radi
	(ilova va modul nomi "Carieer" bo'lsa ham)."""
	firma = get_user_firma()
	bootinfo.carieer_firma = firma
	# Dashboard kartochka va grafiklari firma bo'yicha filtrlanadi (dynamic_filters_json shu qiymatni o'qiydi)
	bootinfo.carieer_firmalar = {
		"Karer": frappe.db.get_single_value("Karer Sozlamalari", "karer_firma") or "",
		"Beton": frappe.db.get_single_value("Karer Sozlamalari", "beton_firma") or "",
	}
	# Post operatori ikkala firmaga sotadi (Karer Operator + Beton Operator): bosh sahifa -> Sotuv operator
	roles = set(frappe.get_roles())
	bootinfo.carieer_post = not firma and {"Karer Operator", "Beton Operator"} <= roles and "System Manager" not in roles
	if not firma:
		return
	title, logo = FIRMA_KORINISHI[firma]
	for app in bootinfo.get("app_data") or []:
		if app.get("app_name") == "carieer":
			app["app_title"] = title
			app["app_logo_url"] = logo
	sidebar = (bootinfo.get("module_sidebars") or {}).get("Carieer")
	if sidebar:
		sidebar["label"] = title
