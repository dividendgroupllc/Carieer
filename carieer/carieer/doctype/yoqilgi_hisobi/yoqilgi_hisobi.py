# Yoqilgi Hisobi: qaysi texnikaga qancha yoqilg'i / moy ketdi.
#   Ombordan    -> Stock Entry (Material Issue): ombordan chiqim, narx = tan narx, xarajat = «Топливо и ГСМ» moddasi
#   Zapravkadan -> zapravka (Supplier) ko'rsatilsa Journal Entry: Dt «Топливо и ГСМ» / Kt zapravka (biz qarzdormiz),
#                  pul keyin Kassa orqali to'lanadi
# Spidometr bo'yicha yurgan km va 100 km ga sarf avtomatik hisoblanadi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from carieer.carieer.doctype.qazib_olish.qazib_olish import cancel_stock_entry
from carieer.utils import get_kategoriya_account, get_zavod, validate_warehouse_company

# Yoqilg'i turi -> xarajat moddasi (Kassa Kategoriya / hisoblar rejasi)
MODDA = {
	"Dizel (солярка)": "Топливо и ГСМ",
	"Benzin": "Топливо и ГСМ",
	"Gaz (metan/propan)": "Пропан",
	"Motor moyi": "Масло для техники",
	"Gidravlik moy": "Масло для техники",
	"Boshqa": "Топливо и ГСМ",
}


class YoqilgiHisobi(Document):
	def validate(self):
		if flt(self.qty) <= 0:
			frappe.throw(_("Miqdor 0 dan katta bo'lishi kerak"))
		if self.manba == "Ombordan":
			self.warehouse = self.warehouse or get_zavod(self.company).get("yoqilgi_ombori")
			if not self.item_code or not self.warehouse:
				frappe.throw(
					_("Ombordan olinganda Tovar va Ombor majburiy (Zavod'da yoqilg'i omborini ko'rsating)")
				)
			validate_warehouse_company(self.warehouse, self.company)
			self.supplier = None
		else:
			self.item_code = self.warehouse = None
		self.amount = flt(self.qty) * flt(self.rate)
		self.set_probeg()

	def set_probeg(self):
		self.oldingi_odometr = self.yurgan_km = self.sarf_100km = 0
		if not flt(self.odometr):
			return
		prev = frappe.db.sql(
			"""select odometr from `tabYoqilgi Hisobi`
			where vehicle=%s and docstatus=1 and name!=%s and odometr>0
			  and (posting_date < %s or (posting_date = %s and creation < %s))
			order by posting_date desc, creation desc limit 1""",
			(
				self.vehicle,
				self.name or "",
				self.posting_date,
				self.posting_date,
				self.creation or frappe.utils.now(),
			),
		)
		if prev:
			prev = flt(prev[0][0])
			if flt(self.odometr) < prev:
				frappe.throw(_("Spidometr ({0}) oldingisidan ({1}) kichik").format(self.odometr, prev))
		else:
			# Vehicle.last_odometer GPS orqali doim yangilanadi (hozirgi qiymat) -> faqat undan kichik bo'lmasa
			# boshlang'ich nuqta sifatida olinadi, aks holda tekshiruv/xato yo'q
			prev = flt(frappe.db.get_value("Vehicle", self.vehicle, "last_odometer"))
			if prev > flt(self.odometr):
				prev = 0
		self.oldingi_odometr = prev
		self.yurgan_km = flt(self.odometr) - prev if prev else 0
		if self.yurgan_km and self.turi in ("Dizel (солярка)", "Benzin", "Gaz (metan/propan)"):
			self.sarf_100km = flt(flt(self.qty) * 100 / self.yurgan_km, 2)

	def expense_account(self):
		# standart xarajat hisobi (Cost of Goods Sold) ga tushmasin: P&L da yoqilg'i tannarx bo'lib ko'rinadi
		modda = MODDA.get(self.turi)
		account = get_kategoriya_account(modda, self.company, "Expense")
		if not account:
			frappe.throw(
				_("«{0}» xarajat moddasi {1} hisoblar rejasida yo'q. Administrator: install.make_moddalar").format(
					modda, self.company
				),
				title=_("Xarajat hisobi yo'q"),
			)
		return account

	def on_submit(self):
		if self.manba == "Zapravkadan" and self.supplier and flt(self.amount) > 0:
			self.make_journal_entry()
		if self.manba == "Ombordan":
			se = frappe.new_doc("Stock Entry")
			se.update(
				{
					"stock_entry_type": "Material Issue",
					"purpose": "Material Issue",
					"company": self.company,
					"posting_date": self.posting_date,
					"set_posting_time": 1,
					"from_warehouse": self.warehouse,
					"remarks": _("{0}: {1} ga {2} l {3}").format(
						self.name, self.vehicle, self.qty, self.turi
					),
				}
			)
			se.append(
				"items",
				{
					"item_code": self.item_code,
					"qty": self.qty,
					"s_warehouse": self.warehouse,
					"expense_account": self.expense_account(),
				},
			)
			se.flags.ignore_permissions = True
			se.insert()
			se.submit()
			rate = flt(se.items[0].valuation_rate or se.items[0].basic_rate)
			self.db_set({"stock_entry": se.name, "rate": rate, "amount": rate * flt(self.qty)})

		if flt(self.odometr) > flt(frappe.db.get_value("Vehicle", self.vehicle, "last_odometer")):
			frappe.db.set_value("Vehicle", self.vehicle, "last_odometer", int(flt(self.odometr)))

	def make_journal_entry(self):
		from erpnext.accounts.party import get_party_account

		party_account = get_party_account("Supplier", self.supplier, self.company)
		cost_center = frappe.get_cached_value("Company", self.company, "cost_center")
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.company
		je.posting_date = self.posting_date
		je.cheque_no = self.name
		je.cheque_date = self.posting_date
		je.user_remark = _("{0}: {1} ga {2} l {3} (zapravka)").format(
			self.name, self.vehicle, self.qty, self.turi
		)
		amount = flt(self.amount, 2)
		je.append(
			"accounts",
			{
				"account": self.expense_account(),
				"debit_in_account_currency": amount,
				"debit": amount,
				"cost_center": cost_center,
			},
		)
		je.append(
			"accounts",
			{
				"account": party_account,
				"party_type": "Supplier",
				"party": self.supplier,
				"credit_in_account_currency": amount,
				"credit": amount,
				"cost_center": cost_center,
			},
		)
		je.flags.ignore_permissions = True
		je.insert()
		je.submit()
		self.db_set("journal_entry", je.name)

	def on_cancel(self):
		self.ignore_linked_doctypes = (
			"Stock Ledger Entry",
			"GL Entry",
			"Journal Entry",
			"Payment Ledger Entry",
		)
		cancel_stock_entry(self.stock_entry)
		if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			je.flags.ignore_permissions = True
			je.cancel()
