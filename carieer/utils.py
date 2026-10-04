"""Umumiy yordamchi funksiyalar (server tomoni, JS yo'q)."""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import flt


# ------------------------------------------------------------------ Zavod (Karer / Beton)
def get_zavod(company: str | None) -> frappe._dict:
	"""Firma -> Zavod yozuvi (omborlar, standart kassa). Topilmasa bo'sh dict."""
	if not company:
		return frappe._dict()
	name = frappe.db.get_value("Zavod", {"company": company}, "name")
	return frappe._dict(frappe.get_cached_doc("Zavod", name).as_dict()) if name else frappe._dict()


def company_for_tip(tip: str | None) -> str:
	company = frappe.db.get_value("Zavod", tip, "company") if tip else None
	if not company:
		frappe.throw(
			_("Zavod '{0}' uchun firma ko'rsatilmagan (Karer -> Sozlamalar -> Zavod)").format(tip or "")
		)
	return company


def get_company_currency(company: str) -> str:
	return frappe.get_cached_value("Company", company, "default_currency")


# ------------------------------------------------------------------ Valyuta kursi
def get_rate(from_currency: str, to_currency: str, date=None) -> float:
	"""Currency Exchange'dagi kurs. Topilmasa tushunarli xato."""
	if not from_currency or not to_currency or from_currency == to_currency:
		return 1.0
	from erpnext.setup.utils import get_exchange_rate

	rate = flt(get_exchange_rate(from_currency, to_currency, date))
	if not rate:
		frappe.throw(
			_("{0} -> {1} kursi topilmadi. Valyuta kursi (Currency Exchange) ga kurs kiriting.").format(
				from_currency, to_currency
			),
			title=_("Kurs yo'q"),
		)
	return rate


def cross_rate(from_currency: str, to_currency: str, company: str, date=None) -> float:
	"""Ikki valyuta orasidagi kurs firma valyutasi orqali (Currency Exchange'da faqat USD -> UZS bo'lishi kifoya)."""
	if from_currency == to_currency:
		return 1.0
	base = get_company_currency(company)
	return get_rate(from_currency, base, date) / get_rate(to_currency, base, date)


# ------------------------------------------------------------------ Tekshiruvlar
def validate_warehouse_company(warehouse: str | None, company: str, label: str | None = None):
	if warehouse and frappe.get_cached_value("Warehouse", warehouse, "company") != company:
		frappe.throw(
			_("{0} ({1}) {2} firmasiga tegishli emas").format(label or _("Ombor"), warehouse, company)
		)


def get_internal_company(party_type: str | None, party: str | None) -> str | None:
	"""Kontragent o'zimizning boshqa firmamiz bo'lsa - o'sha firma nomi (ichki mijoz / ichki ta'minotchi)."""
	field = {"Customer": "is_internal_customer", "Supplier": "is_internal_supplier"}.get(party_type)
	if not field or not party:
		return None
	values = frappe.db.get_value(party_type, party, [field, "represents_company"], as_dict=True)
	return values.represents_company if values and values.get(field) else None


def validate_not_internal(party_type: str | None, party: str | None, tavsiya: str):
	"""Ichki firma faqat bitta kitobga yozilsa, ikki firma qarzi bir-biriga mos kelmay qoladi."""
	if get_internal_company(party_type, party):
		frappe.throw(
			_(
				"{0} - o'zimizning firmamiz. U bilan hisob-kitobni <b>{1}</b> orqali qiling (ikkala firma kitobiga yoziladi)."
			).format(party, tavsiya),
			title=_("Ichki firma"),
		)


@contextmanager
def as_admin():
	"""Firmalararo hujjat ikkinchi firma kitobiga ham yozadi, xodimda esa u firmaga ruxsat yo'q (User Permission).
	Faqat shu ichki qism tizim nomidan bajariladi."""
	user = frappe.session.user
	if user == "Administrator":
		yield
		return
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(user)


# ------------------------------------------------------------------ Kassa
def get_kassa_info(mode_of_payment: str | None, company: str | None) -> frappe._dict:
	"""To'lov turi (kassa) -> shu firmadagi hisob, valyutasi va qoldig'i (hisob valyutasida)."""
	out = frappe._dict(account=None, currency=None, balance=0)
	if not mode_of_payment or not company:
		return out
	out.account = frappe.db.get_value(
		"Mode of Payment Account", {"parent": mode_of_payment, "company": company}, "default_account"
	)
	if not out.account:
		return out
	out.currency = frappe.get_cached_value("Account", out.account, "account_currency")
	out.balance = flt(
		frappe.db.sql(
			"""select sum(debit_in_account_currency) - sum(credit_in_account_currency)
			from `tabGL Entry` where account = %s and is_cancelled = 0""",
			out.account,
		)[0][0]
	)
	return out


def get_kategoriya_account(
	kategoriya: str | None, company: str | None, root_type: str | None = None
) -> str | None:
	"""Kassa Kategoriya -> shu firmadagi hisob (modda): Kategoriya.hisob_nomi yoki kategoriya nomi bilan."""
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


# ------------------------------------------------------------------ Ombor
def get_item_warehouse(item_code: str, company: str) -> str | None:
	"""Sotuv uchun ombor: Zavod'dagi asosiy ombor (qoldiq bo'lsa), keyin xomashyo ombori, keyin qoldig'i bor
	boshqa ombor, oxiri Item'ning standart ombori."""
	zavod = get_zavod(company)
	preferred = [w for w in (zavod.get("asosiy_ombor"), zavod.get("xomashyo_ombori")) if w]
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
		next((w for w in preferred if w in bins), None)
		or (bins[0] if bins else None)
		or (preferred[0] if preferred else None)
		or frappe.db.get_value("Item Default", {"parent": item_code, "company": company}, "default_warehouse")
	)


# ------------------------------------------------------------------ Firmalararo
def ensure_inter_company_parties(seller: str, buyer: str) -> tuple[str, str]:
	"""Sotuvchi kitobida ichki mijoz (= xaridor firma), xaridor kitobida ichki ta'minotchi (= sotuvchi firma).
	Bo'lmasa yaratiladi. ERPNext'ning inter-company mexanizmi shu kontragentlar orqali ishlaydi."""

	def ensure(doctype, flag, represents, allowed_company, name_field, type_field):
		name = frappe.db.get_value(doctype, {flag: 1, "represents_company": represents}, "name")
		if name:
			doc = frappe.get_doc(doctype, name)
			if not any(r.company == allowed_company for r in doc.companies):
				doc.append("companies", {"company": allowed_company})
				doc.flags.ignore_permissions = True
				doc.save()
			return name
		doc = frappe.new_doc(doctype)
		doc.set(name_field, represents)
		doc.set(type_field, "Company")
		doc.set(flag, 1)
		doc.represents_company = represents
		doc.append("companies", {"company": allowed_company})
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc.name

	customer = ensure("Customer", "is_internal_customer", buyer, seller, "customer_name", "customer_type")
	supplier = ensure("Supplier", "is_internal_supplier", seller, buyer, "supplier_name", "supplier_type")
	return customer, supplier


def make_inter_company_purchase_invoice(sales_invoice: str):
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_inter_company_purchase_invoice as fn

	return fn(sales_invoice)


# ------------------------------------------------------------------ SMS
def send_sms(numbers: list[str], message: str):
	"""Frappe SMS Settings yoki Eskiz.uz orqali SMS (background job ichida chaqiriladi)."""
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
