# Firmalararo To'lov: bir firmamiz ikkinchisiga qarzini to'laydi (pul o'tkazmasi).
# Bitta hujjat ikkala kitobga yoziladi:
#   to'lovchi firmada  Payment Entry "Pay"     -> kassadan chiqim, oluvchi firmaga qarzimiz kamayadi
#   oluvchi firmada    Payment Entry "Receive" -> kassaga kirim, to'lovchi firmaning qarzi kamayadi
# To'lov boshqa valyutada bo'lishi mumkin: 250 USD x kurs = so'm. Qarz so'mda kamayadi, kassadan esa
# kassa valyutasida chiqadi. To'lov eng eski to'lanmagan firmalararo hisob-fakturalarga taqsimlanadi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money

from carieer.permissions import check_company, get_allowed_companies
from carieer.utils import (
	as_admin,
	check_kassa_balance,
	ensure_inter_company_parties,
	get_company_currency,
	get_kassa_info,
	get_rate,
)


class FirmalararoTolov(Document):
	def validate(self):
		if self.tolovchi_firma == self.oluvchi_firma:
			frappe.throw(_("To'lovchi va oluvchi firma bir xil bo'lishi mumkin emas"))
		allowed = get_allowed_companies()
		if allowed and self.tolovchi_firma not in allowed:
			# kassalar alohida: pul qaysi firma kassasidan chiqsa, to'lovni o'sha firma kiritadi.
			# Oluvchi firma faqat ko'radi; to'lanmaguncha qarz «Firmalararo qarzlar» da turadi.
			frappe.throw(
				_(
					"Bu to'lovni <b>{0}</b> kiritadi - pul uning kassasidan chiqadi. "
					"Siz faqat qarzni «Firmalararo qarzlar» hisobotida ko'rasiz."
				).format(self.tolovchi_firma),
				frappe.PermissionError,
			)
		if not self.oluvchi_kassa:
			from carieer.utils import get_zavod

			self.oluvchi_kassa = get_zavod(self.oluvchi_firma).get("kassa")
		self.currency = get_company_currency(self.tolovchi_firma)
		if get_company_currency(self.oluvchi_firma) != self.currency:
			frappe.throw(_("Ikkala firmaning asosiy valyutasi bir xil bo'lishi kerak"))
		if flt(self.summa) <= 0:
			frappe.throw(_("Summa 0 dan katta bo'lishi kerak"))
		self.set_amounts()
		self.set_joriy_qarz()
		self.status = {0: "Draft", 1: "Tasdiqlangan", 2: "Bekor qilingan"}[self.docstatus]

	def set_joriy_qarz(self):
		"""Formada ko'rsatish uchun: to'lovchi firma oluvchidan qancha qarz (oluvchi kitobi bo'yicha)."""
		from carieer.carieer.report.firmalararo_qarzlar.firmalararo_qarzlar import balance

		if self.docstatus != 0:
			return
		qarz = balance(self.oluvchi_firma, self.tolovchi_firma, self.posting_date)
		if abs(qarz) < 0.5:
			self.joriy_qarz = _("Qarz yo'q")
		elif qarz > 0:
			self.joriy_qarz = _("{0} {1} dan {2} qarz").format(
				self.tolovchi_firma, self.oluvchi_firma, fmt_money(qarz, 0, self.currency)
			)
		else:
			self.joriy_qarz = _("{0} {1} dan {2} qarz").format(
				self.oluvchi_firma, self.tolovchi_firma, fmt_money(-qarz, 0, self.currency)
			)

	def set_amounts(self):
		"""To'lov valyutasi -> so'm (qarzdan ayriladi) -> har bir kassaning valyutasi.
		Masalan: 250 USD × 12 000 = 3 000 000 so'm; so'm kassadan 3 000 000 chiqadi, qarz 3 000 000 ga kamayadi."""
		self.valyuta = self.valyuta or self.currency
		if self.valyuta == self.currency:
			self.kurs = 1
		elif flt(self.kurs) <= 0 or flt(self.kurs) == 1:
			self.kurs = get_rate(self.valyuta, self.currency, self.posting_date)
		self.base_summa = flt(flt(self.summa) * flt(self.kurs), 2)
		for side in ("tolovchi", "oluvchi"):
			firma, kassa = self.get(f"{side}_firma"), self.get(f"{side}_kassa")
			info = get_kassa_info(kassa, firma)
			if not info["account"]:
				frappe.throw(
					_("{0} kassasi uchun {1} firmasida hisob ko'rsatilmagan (Mode of Payment)").format(
						kassa, firma
					)
				)
			self.set(f"{side}_valyuta", info["currency"])
			self.set(f"{side}_kassa_summa", self.kassa_amount(info["currency"]))
			if side == "tolovchi":
				# boshqa firmaning kassa qoldig'i ko'rsatilmaydi
				self.tolovchi_qoldiq = info["balance"] if check_company(firma, throw=False) else 0
		if self.docstatus < 2:
			# kassa nazorati: to'lovchi kassada yo'q pulni o'tkazib bo'lmaydi
			check_kassa_balance(
				self.tolovchi_kassa, self.tolovchi_firma, self.tolovchi_kassa_summa, self.posting_date
			)

	def kassa_amount(self, kassa_currency):
		"""Kassadan chiqadigan / kassaga kiradigan summa (kassa valyutasida)."""
		if kassa_currency == self.valyuta:
			return flt(self.summa, 2)
		if kassa_currency == self.currency:
			return flt(self.base_summa, 2)
		return flt(flt(self.base_summa) / get_rate(kassa_currency, self.currency, self.posting_date), 2)

	def on_submit(self):
		with as_admin():
			self.make_documents()

	def make_documents(self):
		# oluvchi = "sotuvchi" (unda to'lovchi firma ichki mijoz), to'lovchi = "xaridor" (unda oluvchi ichki yetkazib beruvchi)
		customer, supplier = ensure_inter_company_parties(self.oluvchi_firma, self.tolovchi_firma)
		pay = self.make_payment_entry("Pay", self.tolovchi_firma, self.tolovchi_kassa, "Supplier", supplier)
		receive = self.make_payment_entry(
			"Receive", self.oluvchi_firma, self.oluvchi_kassa, "Customer", customer
		)
		self.db_set(
			{"tolovchi_payment_entry": pay, "oluvchi_payment_entry": receive, "status": "Tasdiqlangan"}
		)

	def on_cancel(self):
		with as_admin():
			self.cancel_documents()

	def cancel_documents(self):
		self.ignore_linked_doctypes = ("GL Entry", "Payment Ledger Entry", "Payment Entry")
		self.db_set("status", "Bekor qilingan")
		for name in (self.oluvchi_payment_entry, self.tolovchi_payment_entry):
			if name and frappe.db.get_value("Payment Entry", name, "docstatus") == 1:
				pe = frappe.get_doc("Payment Entry", name)
				pe.flags.ignore_permissions = True
				pe.cancel()

	def make_payment_entry(self, payment_type, company, kassa, party_type, party):
		from erpnext.accounts.party import get_party_account

		info = get_kassa_info(kassa, company)
		party_account = get_party_account(party_type, party, company)
		base = flt(self.base_summa)  # qarz (firma valyutasida)
		kassa_summa = self.kassa_amount(info["currency"])
		kassa_rate = base / kassa_summa if kassa_summa else 1  # 1 kassa valyutasi = ? so'm
		pay = payment_type == "Pay"
		pe = frappe.new_doc("Payment Entry")
		pe.update(
			{
				"payment_type": payment_type,
				"company": company,
				"posting_date": self.posting_date,
				"mode_of_payment": kassa,
				"party_type": party_type,
				"party": party,
				"paid_from": info["account"] if pay else party_account,
				"paid_to": party_account if pay else info["account"],
				"paid_from_account_currency": info["currency"] if pay else self.currency,
				"paid_to_account_currency": self.currency if pay else info["currency"],
				"paid_amount": kassa_summa if pay else base,
				"received_amount": base if pay else kassa_summa,
				"source_exchange_rate": kassa_rate if pay else 1,
				"target_exchange_rate": 1 if pay else kassa_rate,
				"reference_no": self.name,
				"reference_date": self.posting_date,
				"remarks": _("Firmalararo to'lov {0}: {1} → {2}, {3}. {4}").format(
					self.name,
					self.tolovchi_firma,
					self.oluvchi_firma,
					fmt_money(self.summa, 2, self.valyuta),
					self.izoh or "",
				),
			}
		)
		allocate(pe, "Purchase Invoice" if pay else "Sales Invoice", party_type, party, company, base)
		pe.flags.ignore_permissions = True
		pe.setup_party_account_field()
		pe.set_missing_values()
		pe.set_amounts()
		pe.insert()
		pe.submit()
		return pe.name


def allocate(pe, voucher_type, party_type, party, company, amount):
	"""To'lovni eng eski to'lanmagan hisob-fakturalarga taqsimlaydi (qolgani avans bo'lib qoladi)."""
	party_field = "supplier" if party_type == "Supplier" else "customer"
	left = flt(amount)
	for inv in frappe.get_all(
		voucher_type,
		{"company": company, party_field: party, "docstatus": 1, "outstanding_amount": [">", 0]},
		["name", "grand_total", "outstanding_amount", "due_date"],
		order_by="posting_date asc, creation asc",
	):
		if left <= 0:
			break
		alloc = min(left, flt(inv.outstanding_amount))
		pe.append(
			"references",
			{
				"reference_doctype": voucher_type,
				"reference_name": inv.name,
				"due_date": inv.due_date,
				"total_amount": inv.grand_total,
				"outstanding_amount": inv.outstanding_amount,
				"allocated_amount": alloc,
			},
		)
		left -= alloc


# ------------------------------------------------------------------ Ruxsat: ikkala firma ham ko'radi
# Firma maydonlarida User Permission o'chirilgan (ignore_user_permissions), cheklov shu yerda.
def get_permission_query_conditions(user=None):
	allowed = get_allowed_companies(user)
	if not allowed:
		return ""
	values = ", ".join(frappe.db.escape(c) for c in allowed)
	return f"(`tabFirmalararo Tolov`.tolovchi_firma in ({values}) or `tabFirmalararo Tolov`.oluvchi_firma in ({values}))"


def has_permission(doc, ptype=None, user=None):
	allowed = get_allowed_companies(user)
	if not allowed or not (doc.tolovchi_firma or doc.oluvchi_firma):
		return True
	return doc.tolovchi_firma in allowed or doc.oluvchi_firma in allowed
