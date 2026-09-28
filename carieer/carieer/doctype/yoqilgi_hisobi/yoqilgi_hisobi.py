# Yoqilgi Hisobi: qaysi texnikaga qancha yoqilg'i/moy ketdi.
# "Ombordan" bo'lsa -> Stock Entry (Material Issue) bilan ombordan chiqim qilinadi, narx = tan narx.
# Spidometr bo'yicha yurgan km va 100 km ga sarf avtomatik hisoblanadi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from carieer.carieer.doctype.qazib_olish.qazib_olish import cancel_stock_entry
from carieer.utils import validate_warehouse_company


class YoqilgiHisobi(Document):
	def validate(self):
		if flt(self.qty) <= 0:
			frappe.throw(_("Miqdor 0 dan katta bo'lishi kerak"))
		if self.manba == "Ombordan":
			if not self.item_code or not self.warehouse:
				frappe.throw(_("Ombordan olinganda Tovar va Ombor majburiy"))
			validate_warehouse_company(self.warehouse, self.company)
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
			(self.vehicle, self.name or "", self.posting_date, self.posting_date, self.creation or frappe.utils.now()),
		)
		prev = flt(prev[0][0]) if prev else flt(frappe.db.get_value("Vehicle", self.vehicle, "last_odometer"))
		if prev and flt(self.odometr) < prev:
			frappe.throw(_("Spidometr ({0}) oldingisidan ({1}) kichik").format(self.odometr, prev))
		self.oldingi_odometr = prev
		self.yurgan_km = flt(self.odometr) - prev if prev else 0
		if self.yurgan_km and self.turi in ("Dizel", "Benzin", "Gaz (metan/propan)"):
			self.sarf_100km = flt(flt(self.qty) * 100 / self.yurgan_km, 2)

	def on_submit(self):
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
					"remarks": _("{0}: {1} ga {2} l {3}").format(self.name, self.vehicle, self.qty, self.turi),
				}
			)
			se.append("items", {"item_code": self.item_code, "qty": self.qty, "s_warehouse": self.warehouse})
			se.flags.ignore_permissions = True
			se.insert()
			se.submit()
			rate = flt(se.items[0].valuation_rate or se.items[0].basic_rate)
			self.db_set({"stock_entry": se.name, "rate": rate, "amount": rate * flt(self.qty)})

		if flt(self.odometr) > flt(frappe.db.get_value("Vehicle", self.vehicle, "last_odometer")):
			frappe.db.set_value("Vehicle", self.vehicle, "last_odometer", int(flt(self.odometr)))

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Stock Ledger Entry", "GL Entry")
		cancel_stock_entry(self.stock_entry)
