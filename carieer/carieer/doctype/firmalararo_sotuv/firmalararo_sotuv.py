# Firmalararo Sotuv: 2 firma orasida oldi-sotdi.
# Sotuvchi firmada Sales Invoice (update_stock=1, ichki mijoz) -> xaridor firmada Purchase Invoice
# (update_stock=1, ichki yetkazib beruvchi). ERPNext inter-company mexanizmi ishlatiladi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from carieer.utils import get_company_currency, validate_warehouse_company


class FirmalararoSotuv(Document):
	def validate(self):
		if self.sotuvchi_firma == self.xaridor_firma:
			frappe.throw(_("Sotuvchi va xaridor firma bir xil bo'lishi mumkin emas"))
		if get_company_currency(self.sotuvchi_firma) != get_company_currency(self.xaridor_firma):
			frappe.throw(_("Ikkala firmaning asosiy valyutasi bir xil bo'lishi kerak"))
		validate_warehouse_company(self.chiqish_ombori, self.sotuvchi_firma, _("Chiqish ombori"))
		validate_warehouse_company(self.kirish_ombori, self.xaridor_firma, _("Kirish ombori"))
		for row in self.items:
			if flt(row.qty) <= 0:
				frappe.throw(_("{0}-qator: miqdor 0 dan katta bo'lishi kerak").format(row.idx))
			row.amount = flt(row.qty) * flt(row.rate)
		self.total_amount = sum(flt(r.amount) for r in self.items)

	def on_submit(self):
		customer, supplier = ensure_inter_company_parties(self.sotuvchi_firma, self.xaridor_firma)
		price_list = get_inter_company_price_list(get_company_currency(self.sotuvchi_firma))

		si = frappe.new_doc("Sales Invoice")
		si.update(
			{
				"company": self.sotuvchi_firma,
				"customer": customer,
				"posting_date": self.posting_date,
				"set_posting_time": 1,
				"due_date": self.posting_date,
				"currency": get_company_currency(self.sotuvchi_firma),
				"selling_price_list": price_list,
				"ignore_pricing_rule": 1,
				"update_stock": 1,
				"set_warehouse": self.chiqish_ombori,
				"disable_rounded_total": 1,
				"remarks": _("Firmalararo sotuv {0}").format(self.name),
			}
		)
		for row in self.items:
			si.append(
				"items",
				{
					"item_code": row.item_code,
					"qty": row.qty,
					"rate": row.rate,
					"warehouse": self.chiqish_ombori,
					"allow_zero_valuation_rate": 1,  # qazib olingan tovar tan narxi 0
				},
			)
		si.flags.ignore_permissions = True
		si.set_missing_values()
		for i, row in enumerate(si.items):
			row.rate = self.items[i].rate
			row.price_list_rate = self.items[i].rate
		si.insert()
		si.submit()

		pi = make_inter_company_purchase_invoice(si.name)
		pi.posting_date = self.posting_date
		pi.set_posting_time = 1
		pi.bill_no = si.name
		pi.bill_date = self.posting_date
		pi.update_stock = 1
		pi.set_warehouse = self.kirish_ombori
		pi.buying_price_list = price_list
		for row in pi.items:
			row.warehouse = self.kirish_ombori
		pi.flags.ignore_permissions = True
		pi.insert()
		pi.submit()

		self.db_set({"sales_invoice": si.name, "purchase_invoice": pi.name})

	def on_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry")
		for dt, name in (("Purchase Invoice", self.purchase_invoice), ("Sales Invoice", self.sales_invoice)):
			if name and frappe.db.get_value(dt, name, "docstatus") == 1:
				doc = frappe.get_doc(dt, name)
				doc.flags.ignore_permissions = True
				doc.cancel()


def make_inter_company_purchase_invoice(sales_invoice: str):
	"""ERPNext v16 va develop (v17) da funksiya turli joyda turadi."""
	try:
		from erpnext.accounts.doctype.sales_invoice.mapper import make_inter_company_purchase_invoice as fn
	except ImportError:
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_inter_company_purchase_invoice as fn
	return fn(sales_invoice)


def ensure_inter_company_parties(seller: str, buyer: str) -> tuple[str, str]:
	"""Kerakli ichki mijoz (xaridor firma) va ichki yetkazib beruvchi (sotuvchi firma) bo'lmasa yaratadi."""
	customer = frappe.db.get_value("Customer", {"is_internal_customer": 1, "represents_company": buyer}, "name")
	if not customer:
		c = frappe.new_doc("Customer")
		c.customer_name = buyer
		c.customer_type = "Company"
		c.is_internal_customer = 1
		c.represents_company = buyer
		c.append("companies", {"company": seller})
		c.flags.ignore_permissions = True
		c.insert()
		customer = c.name
	elif not frappe.db.exists("Allowed To Transact With", {"parent": customer, "parenttype": "Customer", "company": seller}):
		c = frappe.get_doc("Customer", customer)
		c.append("companies", {"company": seller})
		c.flags.ignore_permissions = True
		c.save()

	supplier = frappe.db.get_value("Supplier", {"is_internal_supplier": 1, "represents_company": seller}, "name")
	if not supplier:
		s = frappe.new_doc("Supplier")
		s.supplier_name = seller
		s.supplier_type = "Company"
		s.is_internal_supplier = 1
		s.represents_company = seller
		s.append("companies", {"company": buyer})
		s.flags.ignore_permissions = True
		s.insert()
		supplier = s.name
	elif not frappe.db.exists("Allowed To Transact With", {"parent": supplier, "parenttype": "Supplier", "company": buyer}):
		s = frappe.get_doc("Supplier", supplier)
		s.append("companies", {"company": buyer})
		s.flags.ignore_permissions = True
		s.save()
	return customer, supplier


def get_inter_company_price_list(currency: str) -> str:
	name = frappe.db.get_single_value("Karer Sozlamalari", "firmalararo_narx_varaqasi")
	if name:
		return name
	name = "Firmalararo narx"
	if not frappe.db.exists("Price List", name):
		pl = frappe.new_doc("Price List")
		pl.price_list_name = name
		pl.currency = currency
		pl.buying = 1
		pl.selling = 1
		pl.enabled = 1
		pl.flags.ignore_permissions = True
		pl.insert()
	return name
