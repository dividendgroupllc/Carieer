# Kassa Operatsiya: kassadan chiqim (xarajat), boshqa kirim va kassalar orasida o'tkazma.
# Submit -> Journal Entry yaratiladi, kassa qoldig'i shu zahoti o'zgaradi va DDS hisobotida modda bo'lib chiqadi.
#   Chiqim:    Dt xarajat moddasi  / Kt kassa
#   Kirim:     Dt kassa            / Kt daromad moddasi
#   O'tkazma:  Dt qabul qiluvchi kassa / Kt beruvchi kassa

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from carieer.utils import get_company_currency, get_rate

CHIQIM = "Chiqim (xarajat)"
KIRIM = "Kirim (boshqa tushum)"
OTKAZMA = "Kassalar orasida o'tkazma"


def get_kassa_account(mode_of_payment: str, company: str) -> str:
	account = frappe.db.get_value(
		"Mode of Payment Account", {"parent": mode_of_payment, "company": company}, "default_account"
	)
	if not account:
		frappe.throw(
			_("{0} to'lov turida {1} firmasi uchun kassa hisobi ko'rsatilmagan").format(mode_of_payment, company)
		)
	return account


@frappe.whitelist()
def get_kassa_info(mode_of_payment: str, company: str, date: str | None = None) -> dict:
	"""Forma uchun: kassa hisobi, valyutasi va qoldig'i."""
	from erpnext.accounts.utils import get_balance_on

	account = get_kassa_account(mode_of_payment, company)
	return {
		"account": account,
		"currency": frappe.get_cached_value("Account", account, "account_currency"),
		"balance": flt(get_balance_on(account, date, in_account_currency=True, ignore_account_permission=True)),
	}


class KassaOperatsiya(Document):
	def validate(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Summa 0 dan katta bo'lishi kerak"))
		info = get_kassa_info(self.mode_of_payment, self.company, self.posting_date)
		self.kassa_hisobi = info["account"]
		self.currency = info["currency"]
		self.kassa_qoldigi = info["balance"]

		if self.turi == OTKAZMA:
			self.modda = None
			if not self.qabul_kassa:
				frappe.throw(_("Qabul qiluvchi kassani tanlang"))
			if self.qabul_kassa == self.mode_of_payment:
				frappe.throw(_("Beruvchi va qabul qiluvchi kassa bir xil bo'lishi mumkin emas"))
		else:
			self.qabul_kassa = None
			self.qabul_summa = 0
			if not self.modda:
				frappe.throw(_("Moddani (xarajat yoki daromad hisobini) tanlang"))
			acc = frappe.db.get_value("Account", self.modda, ["company", "is_group", "root_type"], as_dict=True)
			if acc.company != self.company or acc.is_group:
				frappe.throw(_("{0} moddasi {1} firmasiga tegishli emas yoki guruh hisob").format(self.modda, self.company))
			kerak = "Expense" if self.turi == CHIQIM else "Income"
			if acc.root_type != kerak:
				frappe.throw(
					_("{0} uchun {1} turidagi modda tanlang (tanlangan: {2})").format(self.turi, kerak, acc.root_type)
				)

	def before_submit(self):
		if self.turi in (CHIQIM, OTKAZMA) and flt(self.amount) > flt(self.kassa_qoldigi) + 0.01:
			frappe.throw(
				_("Kassada mablag' yetarli emas. Qoldiq: {0} {2}, kerak: {1} {2}").format(
					self.kassa_qoldigi, self.amount, self.currency
				),
				title=_("Kassa qoldig'i yetarli emas"),
			)

	def on_submit(self):
		company_currency = get_company_currency(self.company)
		cost_center = frappe.get_cached_value("Company", self.company, "cost_center")
		kassa_rate = get_rate(self.currency, company_currency, self.posting_date)
		base = flt(self.amount) * kassa_rate

		def kassa_row(side, account, currency, amount, rate):
			return {"account": account, f"{side}_in_account_currency": amount, "exchange_rate": rate, "account_currency": currency}

		def modda_row(side):
			return {
				"account": self.modda,
				f"{side}_in_account_currency": base,
				"exchange_rate": 1,
				"cost_center": cost_center,
			}

		multi = self.currency != company_currency
		if self.turi == CHIQIM:
			rows = [modda_row("debit"), kassa_row("credit", self.kassa_hisobi, self.currency, self.amount, kassa_rate)]
		elif self.turi == KIRIM:
			rows = [kassa_row("debit", self.kassa_hisobi, self.currency, self.amount, kassa_rate), modda_row("credit")]
		else:
			target = get_kassa_account(self.qabul_kassa, self.company)
			target_currency = frappe.get_cached_value("Account", target, "account_currency")
			if target_currency == self.currency:
				target_amount, target_rate = flt(self.amount), kassa_rate
			else:
				target_amount = flt(self.qabul_summa)
				if target_amount <= 0:
					frappe.throw(_("Valyuta har xil: qabul qilingan summani kiriting"))
				if target_currency == company_currency:
					# so'mga almashtirildi: haqiqiy kurs = qabul_summa / amount
					kassa_rate = target_amount / flt(self.amount)
					target_rate = 1
				else:
					target_rate = base / target_amount
			multi = multi or target_currency != company_currency
			rows = [
				kassa_row("debit", target, target_currency, target_amount, target_rate),
				kassa_row("credit", self.kassa_hisobi, self.currency, self.amount, kassa_rate),
			]

		je = frappe.new_doc("Journal Entry")
		je.update(
			{
				"voucher_type": "Contra Entry" if self.turi == OTKAZMA else "Journal Entry",
				"company": self.company,
				"posting_date": self.posting_date,
				"multi_currency": 1 if multi else 0,
				"user_remark": " | ".join(
					x for x in (f"{self.name}: {self.turi}", self.kimga, self.vehicle, self.izoh) if x
				),
			}
		)
		for row in rows:
			je.append("accounts", row)
		je.flags.ignore_permissions = True
		je.insert()
		je.submit()
		self.db_set("journal_entry", je.name)

	def on_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Payment Ledger Entry")
		if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			je.flags.ignore_permissions = True
			je.cancel()
