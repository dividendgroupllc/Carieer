"""Umumiy yordamchi funksiyalar (Karer ilovasi)."""

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
def get_exchange_rate_for(from_currency: str, to_currency: str, date: str | None = None) -> float:
	return get_rate(from_currency, to_currency, date)


KARER_ROLES = {"Karer Operator", "Karer Kassir", "Karer Menejer", "System Manager"}


def has_app_permission() -> bool:
	"""Desktop'dagi Karer ikonkasi faqat Karer rollariga ko'rinadi."""
	return bool(KARER_ROLES & set(frappe.get_roles()))
