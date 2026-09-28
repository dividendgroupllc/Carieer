# Karer Sotuv: karer postidagi sotuv.
# Save -> Draft; Submit ("Yakunlash") -> Sales Invoice (update_stock=1) + (bo'lsa) Payment Entry + SMS.
# Keyingi to'lovlar "To'lov qabul qilish" tugmasi orqali (Payment Entry) qo'shiladi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money, formatdate

from carieer.utils import (
	get_company_currency,
	get_rate,
	send_sms,
	validate_warehouse_company,
)


class KarerSotuv(Document):
	# ------------------------------------------------------------ validate
	def validate(self):
		validate_warehouse_company(self.warehouse, self.company)
		self.set_qty_from_weighing()
		self.set_conversion_factor()
		self.set_amounts()
		self.validate_payment()
		self.status = "Draft"

	def set_qty_from_weighing(self):
		if flt(self.brutto) and flt(self.tara):
			if flt(self.tara) >= flt(self.brutto):
				frappe.throw(_("Tara brutto dan katta yoki teng bo'lishi mumkin emas"))
			self.qty = flt(self.brutto) - flt(self.tara)
		if flt(self.qty) <= 0:
			frappe.throw(_("Miqdor 0 dan katta bo'lishi kerak"))

	def set_conversion_factor(self):
		from erpnext.stock.get_item_details import get_conversion_factor

		stock_uom = frappe.get_cached_value("Item", self.item_code, "stock_uom")
		if not self.uom:
			self.uom = stock_uom
		cf = flt(get_conversion_factor(self.item_code, self.uom).get("conversion_factor"))
		if not cf:
			frappe.throw(
				_("{0} tovarida {1} -> {2} koeffitsiyenti yo'q. Item > UOM Conversion jadvaliga qo'shing.").format(
					self.item_code, self.uom, stock_uom
				)
			)
		self.conversion_factor = cf
		self.stock_qty = flt(self.qty) * cf

	def set_amounts(self):
		company_currency = get_company_currency(self.company)
		if self.currency == company_currency:
			self.conversion_rate = 1
		elif not flt(self.conversion_rate) or flt(self.conversion_rate) == 1:
			self.conversion_rate = get_rate(self.currency, company_currency, self.posting_date)
		self.amount = flt(flt(self.qty) * flt(self.rate), self.precision("amount"))
		self.base_amount = flt(self.amount * flt(self.conversion_rate), self.precision("base_amount"))

	def validate_payment(self):
		if flt(self.paid_amount) < 0:
			frappe.throw(_("To'lov summasi manfiy bo'lishi mumkin emas"))
		if flt(self.paid_amount) > flt(self.amount) + 0.01:
			frappe.throw(_("To'lov summasi jami summadan ({0}) katta").format(self.amount))
		if flt(self.paid_amount) and not self.mode_of_payment:
			frappe.throw(_("To'lov turini (kassani) tanlang"))
		self.total_paid = 0
		self.outstanding_amount = self.amount

	# ------------------------------------------------------------ submit / cancel
	def before_submit(self):
		self.check_stock()

	def check_stock(self):
		if frappe.db.get_single_value("Stock Settings", "allow_negative_stock"):
			return
		from erpnext.stock.utils import get_stock_balance

		available = flt(get_stock_balance(self.item_code, self.warehouse, self.posting_date, self.posting_time))
		if available < flt(self.stock_qty):
			frappe.throw(
				_("{0} omborida {1} yetarli emas. Bor: {2}, kerak: {3}").format(
					self.warehouse, self.item_code, available, self.stock_qty
				),
				title=_("Qoldiq yetarli emas"),
			)

	def on_submit(self):
		si = self.make_sales_invoice()
		self.db_set("sales_invoice", si.name)
		if flt(self.paid_amount):
			make_payment_entry(self, flt(self.paid_amount), self.mode_of_payment)
		self.update_payment_status()
		self.send_notification()

	def on_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry")
		if self.sales_invoice:
			for pe in get_payment_entries(self.sales_invoice):
				pe_doc = frappe.get_doc("Payment Entry", pe)
				pe_doc.flags.ignore_permissions = True
				pe_doc.cancel()
			si = frappe.get_doc("Sales Invoice", self.sales_invoice)
			if si.docstatus == 1:
				si.flags.ignore_permissions = True
				si.cancel()
		self.db_set("status", "Cancelled")

	# ------------------------------------------------------------ helpers
	def make_sales_invoice(self):
		si =frappe.new_doc("Sales Invoice")
		si.update(
			{
				"company": self.company,
				"customer": self.customer,
				"posting_date": self.posting_date,
				"posting_time": self.posting_time,
				"set_posting_time": 1,
				"due_date": self.posting_date,
				"currency": self.currency,
				"conversion_rate": self.conversion_rate,
				"update_stock": 1,
				"set_warehouse": self.warehouse,
				"ignore_pricing_rule": 1,
				"disable_rounded_total": 1,
				"remarks": _("Karer Sotuv {0}. Mashina: {1}").format(self.name, self.mashina_raqami),
			}
		)
		si.append(
			"items",
			{
				"item_code": self.item_code,
				"qty": self.qty,
				"uom": self.uom,
				"conversion_factor": self.conversion_factor,
				"rate": self.rate,
				"warehouse": self.warehouse,
				"allow_zero_valuation_rate": 1,  # qazib olingan tovar tan narxi 0
			},
		)
		si.flags.ignore_permissions = True
		si.set_missing_values()
		# set_missing_values narxni price list'dan qayta qo'yishi mumkin -> o'zimiznikini qaytaramiz
		for row in si.items:
			row.rate = self.rate
			row.price_list_rate = self.rate
			row.discount_percentage = 0
			row.margin_rate_or_amount = 0
		si.conversion_rate = self.conversion_rate
		si.insert()
		si.submit()
		return si

	def update_payment_status(self):
		"""Sales Invoice qoldig'iga qarab to'lov holatini yangilaydi."""
		if not self.sales_invoice:
			return
		si = frappe.db.get_value(
			"Sales Invoice",
			self.sales_invoice,
			["outstanding_amount", "grand_total", "currency", "party_account_currency", "conversion_rate", "docstatus"],
			as_dict=True,
		)
		if si.docstatus == 2:
			return
		outstanding = flt(si.outstanding_amount)
		if si.party_account_currency != si.currency:
			outstanding = outstanding / flt(si.conversion_rate or 1)
		outstanding = max(flt(outstanding, self.precision("outstanding_amount")), 0)
		total_paid = flt(flt(si.grand_total) - outstanding, self.precision("total_paid"))

		if outstanding <= 0.01:
			status = "To'langan"
		elif total_paid > 0:
			status = "Qisman to'langan"
		else:
			status = "To'lanmagan"
		self.db_set({"outstanding_amount": outstanding, "total_paid": total_paid, "status": status})

	def send_notification(self):
		settings = frappe.get_cached_doc("Karer Sozlamalari")
		if not settings.sms_yoqilgan or not self.mobile_no:
			return
		self.reload()
		tpl = settings.sms_shablon or "{customer}: {item} {qty} {uom} = {amount} {currency}"
		msg = tpl.format(
			customer=self.customer_name or self.customer,
			date=formatdate(self.posting_date),
			item=self.item_name or self.item_code,
			qty=self.qty,
			uom=self.uom,
			amount=fmt_money(self.amount, currency=None),
			currency=self.currency,
			paid=fmt_money(self.total_paid, currency=None),
			outstanding=fmt_money(self.outstanding_amount, currency=None),
			vehicle=self.mashina_raqami,
			name=self.name,
		)
		frappe.enqueue(send_sms, numbers=[self.mobile_no], message=msg, enqueue_after_commit=True)


# ---------------------------------------------------------------- module level
def get_payment_entries(sales_invoice: str) -> list[str]:
	return frappe.get_all(
		"Payment Entry Reference",
		filters={"reference_doctype": "Sales Invoice", "reference_name": sales_invoice, "docstatus": 1},
		pluck="parent",
		distinct=True,
	)


def make_payment_entry(doc: "KarerSotuv", amount: float, mode_of_payment: str):
	"""Sales Invoice ga qarshi Payment Entry yaratadi. amount - Karer Sotuv valyutasida."""
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

	si = frappe.db.get_value(
		"Sales Invoice",
		doc.sales_invoice,
		["currency", "party_account_currency", "conversion_rate", "company"],
		as_dict=True,
	)
	account = get_bank_cash_account(mode_of_payment, doc.company)["account"]
	account_currency = frappe.get_cached_value("Account", account, "account_currency")
	company_currency = get_company_currency(doc.company)

	# party (debitor) hisobi valyutasidagi summa
	party_amount = amount if si.party_account_currency == si.currency else amount * flt(si.conversion_rate)
	# kassa hisobiga tushadigan summa
	if account_currency == si.currency:
		bank_amount = amount
	elif account_currency == company_currency:
		bank_amount = amount * flt(si.conversion_rate)
	else:
		bank_amount = amount * get_rate(si.currency, account_currency, doc.posting_date)

	pe = get_payment_entry(
		"Sales Invoice",
		doc.sales_invoice,
		party_amount=party_amount,
		bank_account=account,
		bank_amount=bank_amount,
	)
	pe.mode_of_payment = mode_of_payment
	pe.posting_date = frappe.utils.nowdate()
	pe.reference_no = doc.name
	pe.reference_date = pe.posting_date
	pe.remarks = _("Karer Sotuv {0} uchun to'lov").format(doc.name)
	pe.flags.ignore_permissions = True
	pe.insert()
	pe.submit()
	return pe


@frappe.whitelist()
def tolov_qabul_qilish(name: str, amount: float, mode_of_payment: str):
	"""Submit qilingan Karer Sotuv uchun qo'shimcha to'lov (kassir)."""
	doc = frappe.get_doc("Karer Sotuv", name)
	doc.check_permission("submit")
	amount = flt(amount)
	if doc.docstatus != 1:
		frappe.throw(_("Avval hujjatni yakunlang (Submit)"))
	if amount <= 0:
		frappe.throw(_("Summa 0 dan katta bo'lishi kerak"))
	if amount > flt(doc.outstanding_amount) + 0.01:
		frappe.throw(_("Summa qarzdan ({0}) katta").format(doc.outstanding_amount))
	pe = make_payment_entry(doc, amount, mode_of_payment)
	doc.update_payment_status()
	return pe.name


def on_payment_entry_change(pe, method=None):
	"""hooks.py -> Payment Entry on_submit/on_cancel: tashqaridan kiritilgan to'lovlar ham statusni yangilasin."""
	for ref in pe.references:
		if ref.reference_doctype != "Sales Invoice":
			continue
		for name in frappe.get_all(
			"Karer Sotuv", filters={"sales_invoice": ref.reference_name, "docstatus": 1}, pluck="name"
		):
			frappe.get_doc("Karer Sotuv", name).update_payment_status()
