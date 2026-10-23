"""Umumiy yordamchi funksiyalar (server tomoni, JS yo'q)."""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import flt


# ------------------------------------------------------------------ Zavod (Karer)
def get_zavod(company: str | None) -> frappe._dict:
	"""Firma -> Zavod yozuvi (omborlar, standart kassa). Topilmasa bo'sh dict."""
	if not company:
		return frappe._dict()
	name = frappe.db.get_value("Zavod", {"company": company}, "name")
	return frappe._dict(frappe.get_cached_doc("Zavod", name).as_dict()) if name else frappe._dict()


def find_zavod(bolim: str | None) -> str | None:
	"""Bo'lim («Karer») -> Zavod nomi. Zavod boshqacha nomlangan bo'lsa ham topiladi:
	avval aniq nom, keyin nomida, keyin firmasi nomida shu so'z bo'lgan zavod."""
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


@contextmanager
def as_admin():
	"""Xodimda ruxsati yo'q ichki amallar (masalan avansni hisob-fakturaga o'tkazish) tizim nomidan bajariladi."""
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


def kassalar_jami(company: str, upto=None) -> float:
	"""Barcha kassalar (yoqilgan Mode of Payment hisoblari) qoldig'i firma valyutasida: USD kassalar kun kursi bilan so'mga
	o'tkaziladi (jadvaldagi «Сумма в Сум» / Cash Flow «Денег на конец месяца»)."""
	base = get_company_currency(company)
	total = 0
	for (account,) in frappe.db.sql(
		"""select distinct a.default_account from `tabMode of Payment Account` a
		join `tabMode of Payment` m on m.name = a.parent
		where a.company = %s and m.enabled = 1 and ifnull(a.default_account, '') != ''""",
		company,
	):
		currency = frappe.get_cached_value("Account", account, "account_currency")
		balance = account_balance(account, upto)
		total += balance if currency == base else balance * get_rate(currency, base, upto)
	return flt(total, 2)


def kassa_qarzlari(company: str, to_date=None) -> list[frappe._dict]:
	"""Minusga kirgan kassalar (kassadan bor puldan ko'p chiqarilgan): [{kassa, qarz}] firma valyutasida.
	Bu ham firmaning qarzi - keyingi kirimlar (sotuv) bilan yopiladi."""
	cond = " and gl.posting_date <= %(to_date)s" if to_date else ""
	rows = frappe.db.sql(
		f"""select gl.account, sum(gl.debit) - sum(gl.credit) bal
		from `tabGL Entry` gl join `tabAccount` a on a.name = gl.account
		where gl.company = %(company)s and gl.is_cancelled = 0 and a.account_type in ('Cash', 'Bank'){cond}
		group by gl.account having sum(gl.debit) - sum(gl.credit) < -0.005""",
		{"company": company, "to_date": to_date},
		as_dict=True,
	)
	names = dict(
		frappe.db.sql(
			"""select a.default_account, a.parent from `tabMode of Payment Account` a
			join `tabMode of Payment` m on m.name = a.parent where a.company = %s order by m.enabled""",
			company,
		)
	)
	return [frappe._dict(kassa=names.get(r.account, r.account), account=r.account, qarz=-flt(r.bal, 2)) for r in rows]


def check_kassa_balance(mode_of_payment: str, company: str, amount: float, sana=None):
	"""Kassa nazorati: kassadagidan ko'p pul chiqarilsa BLOKLANMAYDI - kassa minusga tushadi (qarzga kirdi) va
	operator ogohlantiriladi. Kassani operator o'zi tanlaydi (hech qanday kassadan o'zi pul olinmaydi).
	Orqa sana bilan kiritilsa ham tekshiriladi: o'sha kundagi va bugungi qoldiqdan kichigi olinadi."""
	info = get_kassa_info(mode_of_payment, company)
	if not info.account or flt(amount) <= 0:
		return
	available = min(account_balance(info.account, sana), info.balance) if sana else info.balance
	if flt(amount) <= flt(available) + 0.005:
		return

	def money(value):
		return frappe.format_value(value, {"fieldtype": "Currency", "options": info.currency})

	frappe.msgprint(
		_(
			"Kassada pul yetarli emas: <b>{0}</b> da {1} bor, to'lanmoqda {2}. "
			"Kassa minusga tushadi (qarzga kirdi): <b>-{3}</b>. Keyingi kirimlar bilan yopiladi."
		).format(mode_of_payment, money(max(available, 0)), money(amount), money(flt(amount) - max(flt(available), 0))),
		title=_("Kassa minusga (qarzga) kiradi"),
		indicator="orange",
		alert=True,
	)


def apply_advances(company: str, party_type: str, party: str, invoice_type: str, invoice_name: str) -> float:
	"""Kontragentning ishlatilmagan avanslari (oldindan to'langan Payment Entry) shu hisob-fakturaga o'tkaziladi
	(ERPNext Payment Reconciliation). Masalan: mijoz 6 mln avans bergan, keyin 1,96 mln tovar oldi ->
	tovar avansdan yopiladi, Sotuv «To'langan» bo'ladi. Qaytaradi: o'tkazilgan summa."""
	if flt(frappe.db.get_value(invoice_type, invoice_name, "outstanding_amount")) <= 0:
		return 0
	account = frappe.db.get_value(
		invoice_type, invoice_name, "debit_to" if invoice_type == "Sales Invoice" else "credit_to"
	)
	return reconcile(company, party_type, party, account, voucher=invoice_name, only_payment_entries=True)


def reconcile(
	company: str,
	party_type: str,
	party: str,
	account: str | None = None,
	voucher: str | None = None,
	only_payment_entries: bool = False,
) -> float:
	"""ERPNext Payment Reconciliation («Allocate» + «Reconcile»): kontragentning ochiq hujjatlari (hisob-faktura,
	Начисление, qaytarilgan pul) ishlatilmagan to'lovlariga (avans) FIFO bilan bog'lanadi - buxgalter qo'lda
	qiladigan ishni o'zi qiladi. voucher berilsa - faqat shu hujjat bog'lanadi (u ochiq hujjat yoki to'lov bo'lishi
	mumkin). Bog'lanmasa GL qoldig'i to'g'ri bo'ladi, lekin ERPNext'ning Accounts Receivable / Payable
	hisobotlarida hujjat va to'lov alohida «osilib» turadi. Qaytaradi: bog'langan summa."""
	if party_type not in ("Customer", "Supplier") or not party:
		return 0
	if not account:
		from erpnext.accounts.party import get_party_account

		account = get_party_account(party_type, party, company)
	pr = frappe.new_doc("Payment Reconciliation")
	pr.company = company
	pr.party_type = party_type
	pr.party = party
	pr.receivable_payable_account = account
	pr.get_unreconciled_entries()
	invoices = [i.as_dict() for i in pr.invoices]
	payments = [p.as_dict() for p in pr.payments if not only_payment_entries or p.reference_type == "Payment Entry"]
	if voucher:
		mine = [i for i in invoices if i.invoice_number == voucher]
		if mine:
			invoices = mine
		else:
			payments = [p for p in payments if p.reference_name == voucher]
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


def validate_payment_kassa(doc, method=None):
	"""hooks.py: Payment Entry -> validate. Hisob-fakturadan «To'lov» (Create -> Payment) yoki qo'lda kiritilgan har qanday
	chiqim ham kassa nazoratidan o'tadi: kassada pul yo'q bo'lsa bloklanmaydi, kassa minusga tushadi va ogohlantiriladi."""
	if doc.payment_type not in ("Pay", "Internal Transfer") or flt(doc.paid_amount) <= 0 or not doc.paid_from:
		return
	if frappe.get_cached_value("Account", doc.paid_from, "account_type") not in ("Cash", "Bank"):
		return
	if doc.payment_type == "Pay" and not doc.mode_of_payment:
		# kassa o'zi tanlanmaydi (standart «Cash» hisobidan pul olinmasin): operator kassani tanlasin
		frappe.throw(
			_("Qaysi kassadan to'lanishini tanlang (Mode of Payment). Kassa o'zi tanlanmaydi."),
			title=_("Kassa tanlanmagan"),
		)
	kassa = frappe.db.get_value(
		"Mode of Payment Account", {"company": doc.company, "default_account": doc.paid_from}, "parent"
	)
	if kassa:
		check_kassa_balance(kassa, doc.company, doc.paid_amount, doc.posting_date)


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
	"""Kassa nomidan valyuta: «naqd USD», «Наличные $» -> USD."""
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
