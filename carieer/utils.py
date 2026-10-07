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


def find_zavod(bolim: str | None) -> str | None:
	"""Bo'lim («Karer» / «Beton») -> Zavod nomi. Zavod boshqacha nomlangan bo'lsa ham topiladi
	(masalan «Beton Zavod»): avval aniq nom, keyin nomida, keyin firmasi nomida shu so'z bo'lgan zavod."""
	if not bolim:
		return None
	if frappe.db.exists("Zavod", bolim):
		return bolim
	for filters in ({"name": ["like", f"%{bolim}%"]}, {"company": ["like", f"%{bolim}%"]}):
		name = frappe.db.get_value("Zavod", filters, "name", order_by="creation asc")
		if name:
			return name
	return None


def company_for_bolim(bolim: str | None) -> str | None:
	"""Bo'lim -> firma (dashboard uchun). Zavod yozuvi bo'lmasa - nomida shu so'z bo'lgan firma."""
	zavod = find_zavod(bolim)
	if zavod:
		return frappe.db.get_value("Zavod", zavod, "company")
	if not bolim:
		return None
	companies = frappe.get_all("Company", filters={"name": ["like", f"%{bolim}%"]}, pluck="name")
	return companies[0] if len(companies) == 1 else None


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
	if frappe.session.user == "Administrator":
		yield
		return
	# frappe.set_user() sessiya obyektining o'zini o'zgartiradi (sid = user, data = {} -> csrf_token, user yo'qoladi)
	# va so'rov oxirida buzilgan sessiya keshga yoziladi. Shuning uchun nusxada almashtiramiz, keyin asl obyektni qaytaramiz.
	saved_session, saved_form_dict = frappe.local.session, frappe.local.form_dict
	frappe.local.session = frappe._dict(saved_session)
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.local.session = saved_session
		frappe.local.form_dict = saved_form_dict
		frappe.local.cache = {}
		frappe.local.role_permissions = {}
		frappe.local.new_doc_templates = {}
		frappe.local.user_perms = None


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
	out.balance = account_balance(out.account)
	return out


def account_balance(account: str, upto=None) -> float:
	"""Kassa hisobidagi qoldiq (hisob valyutasida); upto berilsa - shu sana oxiriga."""
	cond = " and posting_date <= %(upto)s" if upto else ""
	return flt(
		frappe.db.sql(
			f"""select sum(debit_in_account_currency) - sum(credit_in_account_currency)
			from `tabGL Entry` where account = %(account)s and is_cancelled = 0{cond}""",
			{"account": account, "upto": upto},
		)[0][0]
	)


def check_kassa_balance(mode_of_payment: str, company: str, amount: float, sana=None):
	"""Kassa nazorati: kassadagidan ko'p pul chiqarilsa.
	Karer Sozlamalari -> «Kassada minus qoldiqqa ruxsat» yoqiq (standart): to'lov o'tadi, kassa minusga (qarzga)
	kiradi va ogohlantiriladi; o'chirilsa - bloklanadi.
	Orqa sana bilan kiritilsa ham tekshiriladi: o'sha kundagi va bugungi qoldiqdan kichigi olinadi."""
	info = get_kassa_info(mode_of_payment, company)
	if not info.account or flt(amount) <= 0:
		return
	available = min(account_balance(info.account, sana), info.balance) if sana else info.balance
	if flt(amount) <= flt(available) + 0.005:
		return
	from carieer.permissions import check_company

	def money(value):
		return frappe.format_value(value, {"fieldtype": "Currency", "options": info.currency})

	minus_ok = frappe.db.get_single_value("Karer Sozlamalari", "kassa_minus_ruxsat")
	if not check_company(company, throw=False):
		# boshqa firmaning kassa qoldig'i ko'rsatilmaydi
		msg = _("{0} kassasida pul yetarli emas - kassa minusga (qarzga) kiradi.").format(f"<b>{mode_of_payment}</b>")
	elif minus_ok:
		msg = _(
			"{0} kassasida {1} bor, {2} chiqarilmoqda. Kassa minusga kiradi: qoldiq {3} bo'ladi - "
			"bu kassa qarzi, keyingi kirimlar (sotuv) bilan yopiladi."
		).format(f"<b>{mode_of_payment}</b>", money(available), money(amount), money(flt(available) - flt(amount)))
	else:
		msg = _("{0} kassasida {1} bor, {2} chiqarilmoqda. Avval kassaga kirim qiling.").format(
			f"<b>{mode_of_payment}</b>", money(available), money(amount)
		)
	if minus_ok:
		# kassa minusga kirishi mumkin (Karer Sozlamalari): to'lov o'tadi, faqat ogohlantiriladi
		frappe.msgprint(msg, indicator="orange", alert=True)
	else:
		frappe.throw(msg, title=_("Kassada pul yetarli emas"))


def apply_advances(company: str, party_type: str, party: str, invoice_type: str, invoice_name: str) -> float:
	"""Kontragentning ishlatilmagan avanslari (oldindan to'langan Payment Entry) shu hisob-fakturaga o'tkaziladi
	(ERPNext Payment Reconciliation). Masalan: Beton Karer'ga 6 mln avans bergan, keyin 1,96 mln tovar oldi ->
	tovar avansdan yopiladi, Sotuv «To'langan» bo'ladi. Qaytaradi: o'tkazilgan summa."""
	if flt(frappe.db.get_value(invoice_type, invoice_name, "outstanding_amount")) <= 0:
		return 0
	pr = frappe.new_doc("Payment Reconciliation")
	pr.company = company
	pr.party_type = party_type
	pr.party = party
	pr.receivable_payable_account = frappe.db.get_value(
		invoice_type, invoice_name, "debit_to" if invoice_type == "Sales Invoice" else "credit_to"
	)
	pr.get_unreconciled_entries()
	invoices = [i.as_dict() for i in pr.invoices if i.invoice_number == invoice_name]
	payments = [p.as_dict() for p in pr.payments if p.reference_type == "Payment Entry"]
	if not invoices or not payments:
		return 0
	pr.allocate_entries(frappe._dict(invoices=invoices, payments=payments))
	if not pr.allocation:
		return 0
	mute = frappe.flags.mute_messages
	frappe.flags.mute_messages = True  # «Successfully Reconciled» xabari operatorga chiqmasin
	try:
		pr.reconcile()
	finally:
		frappe.flags.mute_messages = mute
	return sum(flt(a.allocated_amount) for a in pr.allocation)


def validate_internal_payment(doc, method=None):
	"""hooks.py: Payment Entry -> validate. O'zimizning ikkinchi firmamizga to'lov faqat «Firmalararo To'lov» orqali:
	oddiy Payment Entry faqat bitta firma kitobiga yoziladi va ikki firma qarzi bir-biriga mos kelmay qoladi."""
	if not (doc.is_new() or doc.docstatus == 0) or doc.flags.get("firmalararo"):
		return
	if not get_internal_company(doc.party_type, doc.party):
		return
	if doc.reference_no and frappe.db.exists("Firmalararo Tolov", doc.reference_no):
		return
	frappe.throw(
		_(
			"{0} - o'zimizning firmamiz. Unga to'lov <b>Firmalararo To'lov</b> orqali kiritiladi "
			"(ikkala firma kitobiga birdan yoziladi). Oldindan berilgan avans bo'lsa - u tovarga avtomatik o'tadi."
		).format(doc.party),
		title=_("Ichki firma"),
	)


def validate_mode_of_payment(doc, method=None):
	"""hooks.py: Mode of Payment -> validate. Kassa nazorati:
	- har bir kassaning o'z hisobi bo'lsin (ikki kassa bitta hisobga ulansa qoldiqlari aralashib ketadi);
	- nomida USD / $ bo'lgan kassa dollar hisobiga ulansin (aks holda 100$ = 100 so'm bo'lib yoziladi)."""
	companies = {a.company for a in doc.accounts if a.company}
	if doc.meta.has_field("firma"):
		# kassa egasi: bitta firmaniki bo'lsa - o'sha firma (kassa ro'yxatlari shu bo'yicha filtrlanadi)
		doc.firma = companies.pop() if len(companies) == 1 else None
	if not doc.enabled:
		return
	for row in doc.accounts:
		if doc.flags.get("skip_kassa_check"):
			break
		if not row.default_account:
			continue
		other = frappe.db.sql(
			"""select a.parent from `tabMode of Payment Account` a join `tabMode of Payment` m on m.name = a.parent
			where a.default_account = %s and a.company = %s and a.parent != %s and m.enabled = 1 limit 1""",
			(row.default_account, row.company, doc.name),
		)
		if other:
			frappe.throw(
				_(
					"{0} hisobi «{1}» kassasiga ulangan. Har bir kassaning o'z hisobi bo'lishi kerak, "
					"aks holda kassalar qoldig'i aralashib ketadi."
				).format(row.default_account, other[0][0]),
				title=_("Kassa hisobi band"),
			)
		want = kassa_currency_hint(doc.name)
		have = frappe.get_cached_value("Account", row.default_account, "account_currency")
		if want and have != want:
			frappe.throw(
				_("«{0}» kassasi {1} da, lekin {2} hisobi {3} da. {1} hisobini tanlang.").format(
					doc.name, want, row.default_account, have
				),
				title=_("Kassa valyutasi"),
			)


def kassa_currency_hint(name: str) -> str | None:
	"""Kassa nomidan valyuta: «Karer naqd USD», «Наличные $» -> USD."""
	low = (name or "").lower()
	if "usd" in low or "$" in low or "dollar" in low:
		return "USD"
	if "eur" in low or "€" in low:
		return "EUR"
	if "rub" in low or "₽" in low:
		return "RUB"
	return None


def validate_currency_exchange(doc, method=None):
	"""hooks.py: Currency Exchange -> validate. Teskari kurs nazorati: «UZS -> USD = 11 900» xato
	(1 so'm 11 900 dollar bo'lib qoladi), to'g'risi «USD -> UZS = 11 900»."""
	company_currencies = set(frappe.get_all("Company", pluck="default_currency"))
	if (
		doc.from_currency in company_currencies
		and doc.to_currency not in company_currencies
		and flt(doc.exchange_rate) > 1
	):
		frappe.throw(
			_("Kurs teskari kiritilgan. To'g'risi: «{0} → {1} = {2}» (1 {0} necha {1} turadi).").format(
				doc.to_currency, doc.from_currency, frappe.format_value(doc.exchange_rate, {"fieldtype": "Float"})
			),
			title=_("Valyuta kursi"),
		)


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
