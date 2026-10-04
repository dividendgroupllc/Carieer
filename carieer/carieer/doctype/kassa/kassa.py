# Kassa ("Касса карьер"): kassaga kirim, kassadan chiqim va kassadan kassaga o'tkazma.
#   Customer / Supplier / Employee   -> Payment Entry (kontragent qarzi kamayadi / ko'payadi)
#   Xarajat / Daromad / Dividend     -> Journal Entry (kassa <-> modda hisobi, kategoriyadan o'zi topiladi)
#   O'tkazma                         -> Payment Entry (Internal Transfer)
# Har bir yozuvda «Kategoriya» bor: DDS va Cash Flow hisobotlari shu bo'yicha yig'iladi (jadvaldagi kabi).
# Cancel -> bog'langan hujjat ham bekor qilinadi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from carieer.utils import (
	cross_rate,
	get_company_currency,
	get_kassa_info,
	get_kategoriya_account,
	get_rate,
	validate_not_internal,
)

PARTY_TYPES = ("Customer", "Supplier", "Employee")
HISOB_ROOT_TYPE = {"Xarajat": "Expense", "Daromad": "Income", "Dividend": "Equity"}
PARTY_NAME_FIELD = {"Customer": "customer_name", "Supplier": "supplier_name", "Employee": "employee_name"}


class Kassa(Document):
	def validate(self):
		self.set_kassa_details()
		self.validate_by_turi()
		self.validate_kategoriya()
		if flt(self.amount) <= 0:
			frappe.throw(_("Summa 0 dan katta bo'lishi kerak"))
		if (
			self.docstatus == 0
			and self.turi in ("Chiqim", "O'tkazma")
			and flt(self.amount) > flt(self.qoldiq)
		):
			frappe.msgprint(
				_("Diqqat: summa ({0}) kassadagi qoldiqdan ({1}) katta").format(
					frappe.format_value(
						self.amount, {"fieldtype": "Currency", "options": self.kassa_valyutasi}
					),
					frappe.format_value(
						self.qoldiq, {"fieldtype": "Currency", "options": self.kassa_valyutasi}
					),
				),
				indicator="orange",
				alert=True,
			)
		self.status = {0: "Draft", 1: "Tasdiqlangan", 2: "Bekor qilingan"}[self.docstatus]

	def set_kassa_details(self):
		info = get_kassa_info(self.mode_of_payment, self.company)
		if not info.account:
			frappe.throw(
				_("{0} kassasida {1} firmasi uchun hisob yo'q (Mode of Payment -> Accounts)").format(
					self.mode_of_payment, self.company
				)
			)
		self.kassa_hisobi, self.kassa_valyutasi, self.qoldiq = info.account, info.currency, info.balance

		if self.turi == "O'tkazma":
			to = get_kassa_info(self.mode_of_payment_to, self.company)
			if not to.account:
				frappe.throw(
					_("{0} kassasida {1} firmasi uchun hisob yo'q").format(
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

	def validate_by_turi(self):
		if self.turi == "O'tkazma":
			if self.kassa_hisobi == self.kassa_hisobi_to:
				frappe.throw(_("Kassalar bir xil bo'lishi mumkin emas"))
			self.party_type = self.party = self.hisob = self.cost_center = None
			self.party_name = _("{0} -> {1}").format(self.mode_of_payment, self.mode_of_payment_to)
			return

		if self.party_type in PARTY_TYPES:
			if not self.party:
				frappe.throw(_("Kontragentni tanlang"))
			validate_not_internal(self.party_type, self.party, _("Firmalararo To'lov"))
			self.party_name = (
				frappe.db.get_value(self.party_type, self.party, PARTY_NAME_FIELD[self.party_type])
				or self.party
			)
			self.hisob = self.cost_center = None
			return

		if self.party_type not in HISOB_ROOT_TYPE:
			frappe.throw(_("Kontragent turini tanlang"))
		if self.party_type == "Dividend" and self.turi == "Kirim":
			frappe.throw(_("Dividend faqat Chiqim bo'ladi"))
		if self.party_type == "Daromad" and self.turi == "Chiqim":
			frappe.throw(_("Daromad (boshqa tushum) faqat Kirim bo'ladi"))
		root_type = HISOB_ROOT_TYPE[self.party_type]
		if not self.hisob and self.party_type == "Dividend":
			self.hisob = frappe.db.get_value(
				"Account", {"company": self.company, "account_name": "Dividends Paid", "is_group": 0}, "name"
			)
		if not self.hisob and self.kategoriya:
			self.hisob = get_kategoriya_account(self.kategoriya, self.company, root_type)
		if not self.hisob:
			frappe.throw(
				_(
					"{0} uchun hisob topilmadi: kategoriyani tanlang (hisoblar rejasida shu nomli hisob bo'lsin) yoki "
					"«Hisob (modda)» ni qo'lda tanlang"
				).format(self.kategoriya or self.party_type)
			)
		acc = frappe.get_cached_value(
			"Account", self.hisob, ["company", "is_group", "root_type", "account_name"], as_dict=True
		)
		if not acc or acc.company != self.company:
			frappe.throw(_("{0} hisobi {1} firmasiga tegishli emas").format(self.hisob, self.company))
		if acc.is_group:
			frappe.throw(_("{0} guruh hisob. Oxirgi darajadagi hisobni tanlang").format(self.hisob))
		if acc.root_type != root_type:
			frappe.throw(
				_("{0} uchun {1} turidagi hisob kerak (tanlangan: {2})").format(
					self.party_type, root_type, acc.root_type
				)
			)
		self.party = None
		self.party_name = acc.account_name
		if self.party_type in ("Xarajat", "Daromad") and not self.cost_center:
			self.cost_center = frappe.get_cached_value("Company", self.company, "cost_center")

	def validate_kategoriya(self):
		if not self.kategoriya or self.turi == "O'tkazma":
			return
		turi = frappe.db.get_value("Kassa Kategoriya", self.kategoriya, "turi")
		if turi not in ("Ikkalasi", None, "", self.turi):
			frappe.throw(_("{0} kategoriyasi faqat {1} uchun").format(self.kategoriya, turi))

	# ------------------------------------------------------------------ submit / cancel
	def on_submit(self):
		if self.turi == "O'tkazma":
			doc = self.make_transfer()
		elif self.party_type in PARTY_TYPES:
			doc = self.make_payment_entry()
		else:
			doc = self.make_journal_entry()
		self.db_set({"linked_doctype": doc.doctype, "linked_entry": doc.name, "status": "Tasdiqlangan"})

	def on_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Payment Ledger Entry", "Payment Entry", "Journal Entry")
		if self.linked_doctype and self.linked_entry:
			doc = frappe.get_doc(self.linked_doctype, self.linked_entry)
			if doc.docstatus == 1:
				doc.flags.ignore_permissions = True
				doc.cancel()
		self.db_set("status", "Bekor qilingan")

	# ------------------------------------------------------------------ hujjatlar
	def rate_to_company(self, currency):
		return get_rate(currency, get_company_currency(self.company), self.sana)

	def make_payment_entry(self):
		from erpnext.accounts.party import get_party_account

		party_account = get_party_account(self.party_type, self.party, self.company)
		party_currency = frappe.get_cached_value("Account", party_account, "account_currency")
		cash_currency = self.kassa_valyutasi
		party_amount = flt(
			flt(self.amount) * cross_rate(cash_currency, party_currency, self.company, self.sana), 2
		)

		pe = frappe.new_doc("Payment Entry")
		pe.payment_type = "Receive" if self.turi == "Kirim" else "Pay"
		pe.company = self.company
		pe.posting_date = self.sana
		pe.mode_of_payment = self.mode_of_payment
		pe.party_type = self.party_type
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
		return self.insert_submit(pe)

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
		pe.received_amount = flt(
			flt(self.amount)
			* cross_rate(self.kassa_valyutasi, self.kassa_valyutasi_to, self.company, self.sana),
			2,
		)
		pe.source_exchange_rate = self.rate_to_company(self.kassa_valyutasi)
		pe.target_exchange_rate = self.rate_to_company(self.kassa_valyutasi_to)
		return self.insert_submit(pe)

	def make_journal_entry(self):
		"""Xarajat, Daromad yoki Dividend: kassa <-> modda hisobi (firma valyutasida)."""
		rate = self.rate_to_company(self.kassa_valyutasi)
		base = flt(flt(self.amount) * rate, 2)
		dr, cr = ("debit", "credit") if self.turi == "Kirim" else ("credit", "debit")

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
