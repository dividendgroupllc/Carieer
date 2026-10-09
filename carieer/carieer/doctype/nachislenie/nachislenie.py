# Nachislenie ("Начисление карьер"): xizmat bo'yicha qarz, pul harakatisiz.
#   Закуп услуга:   bizga xizmat ko'rsatildi (samosval, ekskavator ...) -> biz qarzdormiz:
#                   Dt Xarajat (modda) / Kt Kreditor (ta'minotchi)
#   Продажа услуга: biz xizmat ko'rsatdik (dostavka, pogruzchik ...) -> mijoz qarzdor:
#                   Dt Debitor (mijoz) / Kt Daromad
# Submit -> Journal Entry. Pul keyin Kassa orqali to'lanadi / olinadi; Akt sverka va P&L da modda bo'yicha chiqadi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from carieer.utils import (
	get_company_currency,
	get_kategoriya_account,
	get_rate,
	reconcile,
	validate_not_internal,
)

PARTY_NAME_FIELD = {"Customer": "customer_name", "Supplier": "supplier_name"}
# install.py -> make_moddalar yaratadi (P&L: "Выручка от реализации услуг")
XIZMAT_DAROMAD_HISOBI = "Выручка от реализации услуг"
# Xizmat nachisleniyasi bu hisoblarga yozilmaydi (tovar tannarxi / ombor)
OMBOR_HISOBLARI = (
	"Cost of Goods Sold",
	"Stock Adjustment",
	"Expenses Included In Valuation",
	"Expenses Included In Asset Valuation",
)


class Nachislenie(Document):
	def validate(self):
		# turi -> kontragent turi o'zi qo'yiladi (operator xato tanlay olmaydi)
		expected = "Customer" if self.turi == "Продажа услуга" else "Supplier"
		if self.party_type != expected:
			if self.party and not frappe.db.exists(expected, self.party):
				frappe.throw(
					_("«{0}» uchun kontragent {1} bo'lishi kerak: {2} topilmadi").format(
						self.turi, _(expected), self.party
					)
				)
			self.party_type = expected
		self.validate_kategoriya()
		validate_not_internal(self.party_type, self.party, _("Sotuv (ichki firma)"))
		company_currency = get_company_currency(self.company)
		self.currency = self.currency or company_currency
		if self.currency == company_currency:
			self.kurs = 1
		elif flt(self.kurs) <= 0 or flt(self.kurs) == 1:
			self.kurs = get_rate(self.currency, company_currency, self.sana)
		if flt(self.qty) <= 0 or flt(self.rate) <= 0:
			frappe.throw(_("Miqdor va narx 0 dan katta bo'lishi kerak"))
		self.amount = flt(flt(self.qty) * flt(self.rate), 2)
		self.base_amount = flt(self.amount * flt(self.kurs), 2)
		self.party_name = (
			frappe.db.get_value(self.party_type, self.party, PARTY_NAME_FIELD[self.party_type]) or self.party
		)
		need = "Income" if self.turi == "Продажа услуга" else "Expense"
		before = self.get_doc_before_save()
		if (
			not self.hisob
			or (before and (before.kategoriya != self.kategoriya or before.turi != self.turi))
			or (before and before.company != self.company)
		):
			# kategoriya / turi / firma o'zgarsa hisob qaytadan topiladi (eski modda qolib ketmasin)
			self.hisob = get_default_account(self.company, self.turi, self.kategoriya)
		if not self.hisob:
			frappe.throw(
				_(
					"«{0}» uchun xarajat hisobi topilmadi. Modda (kategoriya) tanlang yoki hisobni qo'lda ko'rsating."
				).format(self.kategoriya or self.turi),
				title=_("Hisob yo'q"),
			)
		root = frappe.get_cached_value(
			"Account", self.hisob, ["root_type", "company", "is_group", "account_type"], as_dict=True
		)
		if not root or root.company != self.company:
			frappe.throw(_("{0} hisobi {1} firmasiga tegishli emas").format(self.hisob, self.company))
		if root.is_group:
			frappe.throw(_("{0} guruh hisob. Oxirgi darajadagi hisobni tanlang").format(self.hisob))
		if root.root_type != need:
			frappe.throw(_("{0} uchun {1} turidagi hisob tanlang").format(self.turi, need))
		if root.account_type in OMBOR_HISOBLARI:
			frappe.throw(
				_(
					"{0} - tovar tannarxi / ombor hisobi. Xizmat xarajati uchun xarajat moddasini tanlang "
					"(aks holda P&L da tannarx bo'lib chiqadi)."
				).format(self.hisob)
			)
		self.cost_center = self.cost_center or frappe.get_cached_value("Company", self.company, "cost_center")
		if self.docstatus == 0:
			self.warn_duplicate()
		self.status = {0: "Draft", 1: "Tasdiqlangan", 2: "Bekor qilingan"}[self.docstatus]

	def validate_kategoriya(self):
		"""Закуп -> xarajat (Chiqim) moddasi, Продажа -> daromad (Kirim) moddasi."""
		if not self.kategoriya:
			return
		turi = frappe.db.get_value("Kassa Kategoriya", self.kategoriya, "turi")
		need = "Kirim" if self.turi == "Продажа услуга" else "Chiqim"
		if turi not in ("Ikkalasi", None, "", need):
			frappe.throw(
				_("«{0}» - {1} moddasi, «{2}» uchun {3} moddasini tanlang").format(
					self.kategoriya, turi, self.turi, need
				)
			)

	def warn_duplicate(self):
		"""Bir xil nachislenie ikki marta kiritilmasin: shu kun, shu kontragent, shu summa."""
		dup = frappe.db.get_value(
			"Nachislenie",
			{
				"name": ["!=", self.name or ""],
				"docstatus": 1,
				"company": self.company,
				"party": self.party,
				"sana": self.sana,
				"turi": self.turi,
				"amount": self.amount,
			},
			"name",
		)
		if dup:
			frappe.msgprint(
				_("Diqqat: xuddi shunday nachislenie bor - {0} (shu kun, shu kontragent, shu summa)").format(
					frappe.utils.get_link_to_form("Nachislenie", dup)
				),
				indicator="orange",
				title=_("Takror bo'lishi mumkin"),
			)

	def on_submit(self):
		from erpnext.accounts.party import get_party_account

		party_account = get_party_account(self.party_type, self.party, self.company)
		party_currency = frappe.get_cached_value("Account", party_account, "account_currency")
		company_currency = get_company_currency(self.company)
		party_rate = (
			1 if party_currency == company_currency else get_rate(party_currency, company_currency, self.sana)
		)
		party_amount = flt(self.base_amount / party_rate, 2)

		sale = self.turi == "Продажа услуга"
		party_side, other_side = ("debit", "credit") if sale else ("credit", "debit")
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.company
		je.posting_date = self.sana
		je.cheque_no = self.name
		je.cheque_date = self.sana
		je.multi_currency = 1 if party_currency != company_currency else 0
		je.user_remark = self.izoh or f"{self.turi}: {self.kategoriya or ''} ({self.name})"
		je.append(
			"accounts",
			{
				"account": party_account,
				"party_type": self.party_type,
				"party": self.party,
				"exchange_rate": party_rate,
				f"{party_side}_in_account_currency": party_amount,
				party_side: self.base_amount,
				"cost_center": self.cost_center,
			},
		)
		je.append(
			"accounts",
			{
				"account": self.hisob,
				"exchange_rate": 1,
				f"{other_side}_in_account_currency": self.base_amount,
				other_side: self.base_amount,
				"cost_center": self.cost_center,
			},
		)
		je.flags.ignore_permissions = True
		je.insert()
		je.submit()
		self.db_set({"journal_entry": je.name, "status": "Tasdiqlangan"})
		# pul oldindan (Kassa orqali) to'langan / olingan bo'lsa - Начисление shu avansdan yopiladi
		reconcile(self.company, self.party_type, self.party, party_account, voucher=je.name)

	def on_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Payment Ledger Entry", "Journal Entry")
		if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			je.flags.ignore_permissions = True
			je.cancel()
		self.db_set("status", "Bekor qilingan")


def get_default_account(company: str, turi: str, kategoriya: str | None = None) -> str | None:
	"""Kategoriya tanlangan bo'lsa - shu kategoriya hisobi (masalan "Самосвал услуга" -> shu nomli xarajat moddasi,
	P&L da alohida qator bo'lib chiqadi). Bo'lmasa: Продажа -> xizmatlardan tushum hisobi yoki firmaning standart
	daromad hisobi, Закуп -> standart xarajat hisobi."""
	sale = turi == "Продажа услуга"
	account = get_kategoriya_account(kategoriya, company, "Income" if sale else "Expense")
	if not account and sale:
		account = frappe.db.get_value(
			"Account",
			{"company": company, "account_name": XIZMAT_DAROMAD_HISOBI, "is_group": 0, "disabled": 0},
			"name",
		)
	if not account and sale:
		account = frappe.get_cached_value("Company", company, "default_income_account")
	# Закуп: standart xarajat hisobi (Cost of Goods Sold) ishlatilmaydi - modda tanlanishi shart
	return account
