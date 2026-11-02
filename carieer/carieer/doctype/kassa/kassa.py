# Kassa ("Касса карьер"): jadvaldagi «Тип расчёта»: Приход, Расход, Перемещение (schyotlar orasida), Конвертация.
#   Клиент / Поставщик / Прочие лица / Сотрудник -> Payment Entry (Customer / Supplier / Employee qarzi)
#   Статья расхода / Доход / Дивиденд /
#   Капитал (Инвестиция, Сальдо ...)            -> Journal Entry (kassa <-> modda hisobi, kategoriyadan o'zi topiladi)
#   Перемещение / Конвертация                   -> Payment Entry (Internal Transfer, jami summaga ta'sir qilmaydi)
# «Тип контрагента» kategoriyadan o'zi qo'yiladi (Клиент, Поставщик, xarajat moddasi -> Статья расхода).
# Kontragent ERPNext doctype'i (Customer / Supplier / Employee) yashirin «party_doctype» maydonida.
# Har bir yozuvda «Kategoriya» bor: DDS va Cash Flow hisobotlari shu bo'yicha yig'iladi (jadvaldagi kabi).
# Cancel -> bog'langan hujjat ham bekor qilinadi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from carieer.utils import (
	check_kassa_balance,
	get_company_currency,
	get_kassa_info,
	get_kategoriya_account,
	get_rate,
	kassalar_jami,
	reconcile,
)

PRIXOD, RASXOD, PEREMESHENIE, KONVERTATSIYA = "Приход", "Расход", "Перемещение", "Конвертация"
TRANSFER_TURI = (PEREMESHENIE, KONVERTATSIYA)
XARAJAT, DAROMAD, DIVIDEND, KAPITAL = "Статья расхода", "Доход", "Дивиденд", "Капитал"
# «Тип контрагента» -> ERPNext doctype
PARTY_DOCTYPE = {"Клиент": "Customer", "Поставщик": "Supplier", "Прочие лица": "Supplier", "Сотрудник": "Employee"}
PARTY_TYPES = tuple(PARTY_DOCTYPE)
HISOB_ROOT_TYPE = {XARAJAT: "Expense", DAROMAD: "Income", DIVIDEND: "Equity", KAPITAL: "Equity"}
STATUS = {0: "Черновик", 1: "Проведён", 2: "Отменён"}
# kategoriya nomi o'zi kontragent turini bildiradi (jadvaldagi «Категория 1»: Клиент / Поставщик / Сотрудник ...)
KATEGORIYA_PARTY = {
	"клиент": "Клиент",
	"поставщик": "Поставщик",
	"прочие лица": "Прочие лица",
	"сотрудник": "Сотрудник",
	"дивиденд": DIVIDEND,
}
KAPITAL_GURUH = "Капитал"  # Kassa Kategoriya.guruh_1 shu bo'lsa - kapital moddasi (Инвестиция, Сальдо, Фин займ)
PARTY_NAME_FIELD = {"Customer": "customer_name", "Supplier": "supplier_name", "Employee": "employee_name"}


class Kassa(Document):
	def _validate_links(self):
		# Frappe Dynamic Link («Контрагент») ni validate()dan OLDIN tekshiradi: kontragent turi shu yerda kategoriyadan qo'yiladi
		self.set_party_type()
		super()._validate_links()

	def validate(self):
		self.set_kassa_details()
		self.set_party_type()
		self.validate_by_turi()
		self.validate_kategoriya()
		if flt(self.amount) <= 0:
			frappe.throw(_("Summa 0 dan katta bo'lishi kerak"))
		self.set_summa()
		if self.turi in (RASXOD, *TRANSFER_TURI):
			# kassada pul yetmasa bloklanmaydi: kassa minusga tushadi va ogohlantiriladi (kassani o'zi tanlaydi)
			check_kassa_balance(self.mode_of_payment, self.company, self.amount, self.sana)
		self.status = STATUS[self.docstatus]

	def set_kassa_details(self):
		info = get_kassa_info(self.mode_of_payment, self.company)
		if not info.account:
			frappe.throw(
				_("У счёта «{0}» нет бухгалтерского счёта для фирмы {1} (Mode of Payment → Accounts)").format(
					self.mode_of_payment, self.company
				)
			)
		self.kassa_hisobi, self.kassa_valyutasi, self.qoldiq = info.account, info.currency, info.balance

		if self.turi in TRANSFER_TURI:
			to = get_kassa_info(self.mode_of_payment_to, self.company)
			if not to.account:
				frappe.throw(
					_("У счёта «{0}» нет бухгалтерского счёта для фирмы {1}").format(
						self.mode_of_payment_to or "-", self.company
					)
				)
			self.kassa_hisobi_to, self.kassa_valyutasi_to, self.qoldiq_to = (
				to.account,
				to.currency,
				to.balance,
			)
		else:
			self.mode_of_payment_to = self.kassa_hisobi_to = self.kassa_valyutasi_to = None
			self.qoldiq_to = 0

	def set_party_type(self):
		"""Kategoriyadan kontragent turi (jadvaldagidek: faqat «Категория 1» + «Контрагент» tanlanadi) va uning doctype'i."""
		if self.turi not in TRANSFER_TURI and not self.party_type:
			self.party_type = derive_party_type(self.kategoriya)
		self.party_doctype = PARTY_DOCTYPE.get(self.party_type)

	def set_summa(self):
		"""«Сумма со знаком в сум»: Приход +, Расход -, Перемещение / Конвертация 0 (kurs - Currency Exchange'dan)."""
		base = get_company_currency(self.company)
		rate = 1 if self.kassa_valyutasi == base else self.rate_to_company(self.kassa_valyutasi)
		sign = {PRIXOD: 1, RASXOD: -1}.get(self.turi, 0)
		self.summa_sum = flt(sign * flt(self.amount) * rate, 2)
		self.taqsimot = (
			frappe.db.get_value("Kassa Kategoriya", self.kategoriya, "taqsimot") if self.kategoriya else None
		)

	def validate_by_turi(self):
		if self.turi in TRANSFER_TURI:
			if self.kassa_hisobi == self.kassa_hisobi_to:
				frappe.throw(_("Счёт «откуда» и «куда» не может быть одним и тем же"))
			self.party_type = self.party_doctype = self.party = self.hisob = self.cost_center = None
			self.party_name = _("{0} -> {1}").format(self.mode_of_payment, self.mode_of_payment_to)
			return

		if self.party_type in PARTY_TYPES:
			if not self.party:
				frappe.throw(_("Выберите контрагента"))
			self.party_name = (
				frappe.db.get_value(self.party_doctype, self.party, PARTY_NAME_FIELD[self.party_doctype])
				or self.party
			)
			self.hisob = self.cost_center = None
			return

		if self.party_type not in HISOB_ROOT_TYPE:
			frappe.throw(_("Выберите «Категория 1» или укажите тип контрагента"))
		if self.party_type == DIVIDEND and self.turi == PRIXOD:
			frappe.throw(_("Дивиденд может быть только расходом"))
		if self.party_type == DAROMAD and self.turi == RASXOD:
			frappe.throw(_("Доход (прочие поступления) может быть только приходом"))
		root_type = HISOB_ROOT_TYPE[self.party_type]
		if not self.hisob and self.party_type == DIVIDEND:
			self.hisob = frappe.db.get_value(
				"Account", {"company": self.company, "account_name": "Dividends Paid", "is_group": 0}, "name"
			)
		if self.hisob and self.kategoriya:
			# qo'lda tanlangan hisob turga mos kelmasa (masalan kassaning o'z hisobi) - kategoriyadan topiladi
			if frappe.get_cached_value("Account", self.hisob, "root_type") != root_type:
				self.hisob = None
		if not self.hisob and self.kategoriya:
			self.hisob = get_kategoriya_account(self.kategoriya, self.company, root_type)
		if not self.hisob:
			frappe.throw(
				_(
					"Для «{0}» не найден бухгалтерский счёт: выберите категорию (в плане счетов должен быть счёт с таким "
					"названием) или укажите «Статья (бухгалтерский счёт)» вручную"
				).format(self.kategoriya or self.party_type)
			)
		acc = frappe.get_cached_value(
			"Account", self.hisob, ["company", "is_group", "root_type", "account_name"], as_dict=True
		)
		if not acc or acc.company != self.company:
			frappe.throw(_("Счёт {0} не принадлежит фирме {1}").format(self.hisob, self.company))
		if acc.is_group:
			frappe.throw(_("{0} — групповой счёт. Выберите счёт нижнего уровня").format(self.hisob))
		if acc.root_type != root_type:
			frappe.throw(
				_(
					"Неверная «Статья (бухгалтерский счёт)»: для «{0}» нужен счёт типа {1}, а {2} — {3}. "
					"Оставьте поле пустым — счёт определится по категории"
				).format(self.party_type, root_type, self.hisob, acc.root_type)
			)
		self.party = None
		self.party_name = acc.account_name
		if self.party_type in (XARAJAT, DAROMAD) and not self.cost_center:
			self.cost_center = frappe.get_cached_value("Company", self.company, "cost_center")

	def validate_kategoriya(self):
		if not self.kategoriya or self.turi in TRANSFER_TURI:
			return
		# Yo'nalish (Приход / Расход) har qanday kategoriya bilan mumkin: jadvalda «Клиент» ga Расход (qaytarish),
		# «Доставка» ga Приход ham bor
		kat = frappe.db.get_value("Kassa Kategoriya", self.kategoriya, ["turi", "guruh_1"], as_dict=True) or {}
		# Xato: xarajat (ijara, yoqilg'i ...) mijoz nomiga yozilsa - mijoz bizga qarzdor bo'lib qoladi
		if self.party_doctype == "Customer" and self.turi == RASXOD and kat.get("guruh_1"):
			frappe.throw(
				_(
					"«{0}» — статья расхода. При расходе на клиента деньги попадут не в расходы, а в долг клиента. "
					"Выберите тип контрагента <b>Статья расхода</b> (если оказана услуга — <b>Поставщик</b>)."
				).format(self.kategoriya),
				title=_("Неверный тип контрагента"),
			)

	# ------------------------------------------------------------------ submit / cancel
	def on_submit(self):
		if self.turi in TRANSFER_TURI:
			doc = self.make_transfer()
		elif self.party_type in PARTY_TYPES:
			doc = self.make_payment_entry()
		else:
			doc = self.make_journal_entry()
		self.db_set({"linked_doctype": doc.doctype, "linked_entry": doc.name, "status": STATUS[1]})

	def on_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Payment Ledger Entry", "Payment Entry", "Journal Entry")
		if self.linked_doctype and self.linked_entry:
			doc = frappe.get_doc(self.linked_doctype, self.linked_entry)
			if doc.docstatus == 1:
				doc.flags.ignore_permissions = True
				doc.cancel()
		self.db_set("status", STATUS[2])

	# ------------------------------------------------------------------ hujjatlar
	def rate_to_company(self, currency):
		"""Valyuta -> firma valyutasi: kun kursi Currency Exchange'dan."""
		base = get_company_currency(self.company)
		if currency == base:
			return 1.0
		return get_rate(currency, base, self.sana)

	def cross(self, from_currency, to_currency):
		return self.rate_to_company(from_currency) / self.rate_to_company(to_currency)

	def make_payment_entry(self):
		from erpnext.accounts.party import get_party_account

		party_account = get_party_account(self.party_doctype, self.party, self.company)
		party_currency = frappe.get_cached_value("Account", party_account, "account_currency")
		cash_currency = self.kassa_valyutasi
		party_amount = flt(flt(self.amount) * self.cross(cash_currency, party_currency), 2)

		pe = frappe.new_doc("Payment Entry")
		pe.payment_type = "Receive" if self.turi == PRIXOD else "Pay"
		pe.company = self.company
		pe.posting_date = self.sana
		pe.mode_of_payment = self.mode_of_payment
		pe.party_type = self.party_doctype
		pe.party = self.party
		pe.party_name = self.party_name
		if pe.payment_type == "Receive":
			pe.paid_from, pe.paid_from_account_currency, pe.paid_amount = (
				party_account,
				party_currency,
				party_amount,
			)
			pe.paid_to, pe.paid_to_account_currency, pe.received_amount = (
				self.kassa_hisobi,
				cash_currency,
				flt(self.amount),
			)
		else:
			pe.paid_from, pe.paid_from_account_currency, pe.paid_amount = (
				self.kassa_hisobi,
				cash_currency,
				flt(self.amount),
			)
			pe.paid_to, pe.paid_to_account_currency, pe.received_amount = (
				party_account,
				party_currency,
				party_amount,
			)
		pe.source_exchange_rate = self.rate_to_company(pe.paid_from_account_currency)
		pe.target_exchange_rate = self.rate_to_company(pe.paid_to_account_currency)
		allocate_to_invoices(pe)
		self.insert_submit(pe)
		if flt(pe.unallocated_amount) > 0.005:
			# hisob-fakturaga tushmagan qismi Начисление (Journal Entry) yoki avansga bog'lanadi -
			# aks holda ERPNext'ning Accounts Payable / Receivable hisobotida ikkalasi alohida osilib turadi
			reconcile(self.company, self.party_doctype, self.party, party_account, voucher=pe.name)
		return pe

	def make_transfer(self):
		pe = frappe.new_doc("Payment Entry")
		pe.payment_type = "Internal Transfer"
		pe.company = self.company
		pe.posting_date = self.sana
		pe.mode_of_payment = self.mode_of_payment
		pe.paid_from, pe.paid_from_account_currency, pe.paid_amount = (
			self.kassa_hisobi,
			self.kassa_valyutasi,
			flt(self.amount),
		)
		pe.paid_to, pe.paid_to_account_currency = self.kassa_hisobi_to, self.kassa_valyutasi_to
		base = get_company_currency(self.company)
		src_rate = self.rate_to_company(self.kassa_valyutasi)
		tgt_rate = self.rate_to_company(self.kassa_valyutasi_to)
		received = flt(flt(self.amount) * src_rate / tgt_rate, 2)
		if self.turi == KONVERTATSIYA and flt(self.qabul_summa) > 0:
			# haqiqiy olingan summa berilgan: farq kurs farqi bo'lib qolmasligi uchun tashqi valyuta tomoni kursi moslanadi
			received = flt(self.qabul_summa)
			if self.kassa_valyutasi_to == base:
				src_rate = flt(received / flt(self.amount), 9)
			else:
				tgt_rate = flt(flt(self.amount) * src_rate / received, 9)
		pe.received_amount = received
		pe.source_exchange_rate = src_rate
		pe.target_exchange_rate = tgt_rate
		return self.insert_submit(pe)

	def make_journal_entry(self):
		"""Статья расхода, Доход, Дивиденд yoki Капитал: kassa <-> modda hisobi (firma valyutasida)."""
		rate = self.rate_to_company(self.kassa_valyutasi)
		base = flt(flt(self.amount) * rate, 2)
		dr, cr = ("debit", "credit") if self.turi == PRIXOD else ("credit", "debit")

		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Cash Entry"
		je.company = self.company
		je.posting_date = self.sana
		je.cheque_no = self.name
		je.cheque_date = self.sana
		je.multi_currency = 1 if self.kassa_valyutasi != get_company_currency(self.company) else 0
		je.user_remark = self.izoh or _("Kassa {0}: {1}").format(self.name, self.party_name)
		je.append(
			"accounts",
			{
				"account": self.kassa_hisobi,
				"exchange_rate": rate,
				f"{dr}_in_account_currency": flt(self.amount),
				dr: base,
			},
		)
		je.append(
			"accounts",
			{
				"account": self.hisob,
				"exchange_rate": 1,
				f"{cr}_in_account_currency": base,
				cr: base,
				"cost_center": self.cost_center,
			},
		)
		return self.insert_submit(je)

	def insert_submit(self, doc):
		if doc.doctype == "Payment Entry":
			doc.reference_no = self.name
			doc.reference_date = self.sana
			doc.remarks = self.izoh or _("Kassa {0}").format(self.name)
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		return doc


def derive_party_type(kategoriya: str | None) -> str | None:
	"""Kategoriya -> «Тип контрагента»: Клиент, Поставщик, Прочие лица, Сотрудник, xarajat moddasi -> Статья расхода,
	kapital moddasi (Инвестиция, Сальдо) -> Капитал, boshqa tushum -> Доход."""
	if not kategoriya:
		return None
	party_type = KATEGORIYA_PARTY.get(kategoriya.lower())
	if party_type:
		return party_type
	kat = frappe.db.get_value("Kassa Kategoriya", kategoriya, ["guruh_1", "hisob_nomi"], as_dict=True) or {}
	if kat.get("guruh_1") == KAPITAL_GURUH:
		return KAPITAL
	if kat.get("guruh_1"):
		return XARAJAT
	if kat.get("hisob_nomi"):
		return DAROMAD
	return None


def allocate_to_invoices(pe):
	"""Mijozdan kirim / ta'minotchiga chiqim eng eski to'lanmagan hisob-fakturalarga taqsimlanadi (FIFO).
	Shunda Sotuv'dagi «Долг» va holat ham yangilanadi; ortib qolgan summa avans bo'lib qoladi."""
	if pe.party_type == "Customer" and pe.payment_type == "Receive":
		doctype, party_field, amount = "Sales Invoice", "customer", flt(pe.paid_amount)
	elif pe.party_type == "Supplier" and pe.payment_type == "Pay":
		doctype, party_field, amount = "Purchase Invoice", "supplier", flt(pe.received_amount)
	else:
		return
	account = pe.paid_from if pe.payment_type == "Receive" else pe.paid_to
	invoices = frappe.get_all(
		doctype,
		filters={
			party_field: pe.party,
			"company": pe.company,
			"docstatus": 1,
			"outstanding_amount": [">", 0],
			"debit_to" if doctype == "Sales Invoice" else "credit_to": account,
		},
		fields=["name", "outstanding_amount"],
		order_by="posting_date asc, creation asc",
	)
	for inv in invoices:
		if amount <= 0:
			break
		allocated = min(amount, flt(inv.outstanding_amount))
		pe.append(
			"references",
			{"reference_doctype": doctype, "reference_name": inv.name, "allocated_amount": allocated},
		)
		amount = flt(amount - allocated, 2)


@frappe.whitelist()
def kassa_holati(company: str, kassa: str, summa: float, turi: str = PRIXOD) -> dict:
	"""Forma uchun: kassada hozir qancha pul bor va shu yozuvdan keyin qancha bo'ladi (kassa valyutasida)."""
	from carieer.utils import get_kassa_info

	info = get_kassa_info(kassa, company)
	if not info.account:
		return {}
	balance = flt(info.balance, 2)
	summa = flt(summa)
	after = balance + summa if turi == PRIXOD else balance - summa
	base = get_company_currency(company)
	rate = 1 if info.currency == base else get_rate(info.currency, base)
	jami = kassalar_jami(company)
	# Перемещение / Конвертация barcha kassalar yig'indisini o'zgartirmaydi
	delta = (summa * rate) * {PRIXOD: 1, RASXOD: -1}.get(turi, 0)
	return {
		"balance": balance,
		"after": flt(after, 2),
		"currency": info.currency,
		"jami": jami,
		"jami_after": flt(jami + delta, 2),
		"base_currency": base,
	}
