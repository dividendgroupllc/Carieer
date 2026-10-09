# Prixod OS ("Приход ОС"): asosiy vositalar (texnika, uskuna, bino, yer, litsenziya...) kirimi.
# Google Sheets'dagi "Приход ОС" varag'i: sana, nomi, kol-vo, narx, valyuta, summa, поставщик, kurs, summa (so'mda).
# Submit -> Journal Entry:
#   Yetkazib beruvchidan olingan bo'lsa:  Dt Asosiy vosita hisobi / Kt Kreditor (yetkazib beruvchi)  -> to'lov Kassa orqali
#   Ta'sischi kiritgan mulk bo'lsa:        Dt Asosiy vosita hisobi / Kt Ustav kapitali
# Balansda "Оборудование" qatori shu hujjatlar yig'indisi bo'ladi. (Amortizatsiya hisoblanmaydi - jadvalda ham yo'q.)

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from carieer.utils import get_company_currency, get_rate, validate_not_internal


class PrixodOS(Document):
	def validate(self):
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

		defaults = get_default_accounts(self.company)
		self.hisob = self.hisob or defaults["hisob"]
		if not self.hisob:
			frappe.throw(_("Asosiy vosita hisobini tanlang"))
		self.check_account(self.hisob, ("Asset",))
		if self.supplier:
			# ichki firmadan qarz faqat shu kitobga yozilardi - ikkinchi firma bilmay qoladi
			validate_not_internal("Supplier", self.supplier, _("Sotuv (sotuvchi firma bo'limida)"))
			self.kredit_hisob = None
		else:
			self.kredit_hisob = self.kredit_hisob or defaults["kredit_hisob"]
			if not self.kredit_hisob:
				frappe.throw(_("Yetkazib beruvchini yoki manba hisobini (ustav kapitali) tanlang"))
			self.check_account(self.kredit_hisob, ("Equity", "Liability"))
		self.status = {0: "Draft", 1: "Tasdiqlangan", 2: "Bekor qilingan"}[self.docstatus]

	def check_account(self, account, root_types):
		acc = frappe.get_cached_value("Account", account, ["company", "is_group", "root_type"], as_dict=True)
		if not acc or acc.company != self.company:
			frappe.throw(_("{0} hisobi {1} firmasiga tegishli emas").format(account, self.company))
		if acc.is_group:
			frappe.throw(_("{0} guruh hisob. Oxirgi darajadagi hisobni tanlang").format(account))
		if acc.root_type not in root_types:
			frappe.throw(
				_("{0} hisobi turi {1} bo'lishi kerak (hozir: {2})").format(
					account, " / ".join(root_types), acc.root_type
				)
			)

	def on_submit(self):
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.company
		je.posting_date = self.sana
		je.cheque_no = self.name
		je.cheque_date = self.sana
		je.user_remark = " | ".join(x for x in (f"Приход ОС {self.name}: {self.nomi}", self.izoh) if x)
		je.append(
			"accounts",
			{
				"account": self.hisob,
				"exchange_rate": 1,
				"debit_in_account_currency": self.base_amount,
				"debit": self.base_amount,
			},
		)
		if self.supplier:
			from erpnext.accounts.party import get_party_account

			company_currency = get_company_currency(self.company)
			party_account = get_party_account("Supplier", self.supplier, self.company)
			party_currency = frappe.get_cached_value("Account", party_account, "account_currency")
			party_rate = (
				1
				if party_currency == company_currency
				else get_rate(party_currency, company_currency, self.sana)
			)
			je.multi_currency = 1 if party_currency != company_currency else 0
			je.append(
				"accounts",
				{
					"account": party_account,
					"party_type": "Supplier",
					"party": self.supplier,
					"exchange_rate": party_rate,
					"credit_in_account_currency": flt(self.base_amount / party_rate, 2),
					"credit": self.base_amount,
				},
			)
		else:
			je.append(
				"accounts",
				{
					"account": self.kredit_hisob,
					"exchange_rate": 1,
					"credit_in_account_currency": self.base_amount,
					"credit": self.base_amount,
				},
			)
		je.flags.ignore_permissions = True
		je.insert()
		je.submit()
		self.db_set({"journal_entry": je.name, "status": "Tasdiqlangan"})

	def on_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Payment Ledger Entry", "Journal Entry")
		if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			je.flags.ignore_permissions = True
			je.cancel()
		self.db_set("status", "Bekor qilingan")


def get_default_accounts(company: str) -> dict:
	"""Standart hisoblar: «Оборудование» (Capital Equipment) yoki birinchi Fixed Asset hisobi va ustav kapitali."""
	hisob = None
	for account_name in ("Capital Equipment", "Plants and Machineries", "Оборудование"):
		hisob = frappe.db.get_value(
			"Account",
			{"company": company, "account_name": account_name, "is_group": 0, "disabled": 0},
			"name",
		)
		if hisob:
			break
	hisob = hisob or frappe.db.get_value(
		"Account",
		{"company": company, "account_type": "Fixed Asset", "is_group": 0, "disabled": 0},
		"name",
		order_by="lft asc",
	)
	kredit = frappe.db.get_value(
		"Account", {"company": company, "account_name": "Capital Stock", "is_group": 0}, "name"
	) or frappe.db.get_value(
		"Account",
		{"company": company, "account_type": "Equity", "is_group": 0, "disabled": 0},
		"name",
		order_by="lft asc",
	)
	return {"hisob": hisob, "kredit_hisob": kredit}
