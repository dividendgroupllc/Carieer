# Qazib Olish: karerdan qazib olingan tovar omborga TAN NARXI 0 bilan kirim qilinadi
# (Stock Entry "Material Receipt", allow_zero_valuation_rate = 1).

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from carieer.utils import get_zavod, validate_warehouse_company


class QazibOlish(Document):
	def validate(self):
		self.warehouse = self.warehouse or get_zavod(self.company).get("asosiy_ombor")
		if not self.warehouse:
			frappe.throw(_("Omborni tanlang (yoki Zavod'da asosiy omborni ko'rsating)"))
		validate_warehouse_company(self.warehouse, self.company)
		for row in self.items:
			if flt(row.qty) <= 0:
				frappe.throw(_("{0}-qator: miqdor 0 dan katta bo'lishi kerak").format(row.idx))
			# Float ustuni decimal(21,9): 10^12 dan kattasi bazaga sig'maydi (MySQL "Out of range" xatosi)
			if flt(row.qty) >= 1e11:
				frappe.throw(
					_("{0}-qator: miqdor juda katta ({1}). Raqamni tekshiring").format(row.idx, row.qty)
				)
			if not frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
				frappe.throw(
					_("{0}-qator: {1} ombor tovari emas (Maintain Stock)").format(row.idx, row.item_code)
				)
		self.total_qty = sum(flt(r.qty) for r in self.items)

	def on_submit(self):
		se = frappe.new_doc("Stock Entry")
		se.update(
			{
				"stock_entry_type": "Material Receipt",
				"purpose": "Material Receipt",
				"company": self.company,
				"posting_date": self.posting_date,
				"posting_time": self.posting_time,
				"set_posting_time": 1,
				"to_warehouse": self.warehouse,
				"remarks": _("Qazib olish {0}").format(self.name),
			}
		)
		for row in self.items:
			se.append(
				"items",
				{
					"item_code": row.item_code,
					"qty": row.qty,
					"t_warehouse": self.warehouse,
					"basic_rate": 0,
					"allow_zero_valuation_rate": 1,
				},
			)
		se.flags.ignore_permissions = True
		se.insert()
		se.submit()
		self.db_set("stock_entry", se.name)

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Stock Ledger Entry", "GL Entry")
		cancel_stock_entry(self.stock_entry)


def cancel_stock_entry(name):
	if name and frappe.db.get_value("Stock Entry", name, "docstatus") == 1:
		se = frappe.get_doc("Stock Entry", name)
		se.flags.ignore_permissions = True
		se.cancel()
