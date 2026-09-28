# Beton Ishlab Chiqarish: BOM (retsept) bo'yicha xomashyo (qum, shag'al, sement, ximikat...) sarflanib,
# beton ishlab chiqariladi. Stock Entry "Manufacture" -> tan narx avtomatik (xomashyo qiymati yig'indisi).
# Qazib olingan qum/shag'al tan narxi 0 bo'lgani uchun beton tan narxiga faqat sotib olingan xomashyo kiradi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from carieer.carieer.doctype.qazib_olish.qazib_olish import cancel_stock_entry
from carieer.utils import validate_warehouse_company


class BetonIshlabChiqarish(Document):
	def validate(self):
		if flt(self.qty) <= 0:
			frappe.throw(_("Miqdor 0 dan katta bo'lishi kerak"))
		bom = frappe.db.get_value("BOM", self.bom, ["item", "is_active", "docstatus", "company", "uom"], as_dict=True)
		if not bom or bom.docstatus != 1 or not bom.is_active:
			frappe.throw(_("BOM {0} faol va submit qilingan bo'lishi kerak").format(self.bom))
		if bom.company != self.company:
			frappe.throw(_("BOM {0} {1} firmasiga tegishli emas").format(self.bom, self.company))
		self.item_code = bom.item
		self.uom = bom.uom
		validate_warehouse_company(self.xomashyo_ombori, self.company, _("Xomashyo ombori"))
		validate_warehouse_company(self.tayyor_ombori, self.company, _("Tayyor mahsulot ombori"))
		self.set_xomashyolar()

	def set_xomashyolar(self):
		from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict
		from erpnext.stock.utils import get_stock_balance

		self.set("xomashyolar", [])
		items = get_bom_items_as_dict(self.bom, self.company, qty=flt(self.qty), fetch_exploded=1)
		for it in items.values():
			self.append(
				"xomashyolar",
				{
					"item_code": it.item_code,
					"item_name": it.item_name,
					"required_qty": flt(it.qty, 3),
					"uom": it.stock_uom,
					"available_qty": flt(
						get_stock_balance(it.item_code, self.xomashyo_ombori, self.posting_date, self.posting_time)
					),
				},
			)

	def before_submit(self):
		kam = [
			f"{r.item_code}: {_('kerak')} {r.required_qty} {r.uom}, {_('bor')} {r.available_qty}"
			for r in self.xomashyolar
			if flt(r.available_qty) < flt(r.required_qty)
		]
		if kam and not frappe.db.get_single_value("Stock Settings", "allow_negative_stock"):
			frappe.throw("<br>".join(kam), title=_("Xomashyo yetarli emas"))

	def on_submit(self):
		se = frappe.new_doc("Stock Entry")
		se.update(
			{
				"stock_entry_type": "Manufacture",
				"purpose": "Manufacture",
				"company": self.company,
				"posting_date": self.posting_date,
				"posting_time": self.posting_time,
				"set_posting_time": 1,
				"from_bom": 1,
				"use_multi_level_bom": 1,
				"bom_no": self.bom,
				"fg_completed_qty": self.qty,
				"from_warehouse": self.xomashyo_ombori,
				"to_warehouse": self.tayyor_ombori,
				"remarks": _("Beton ishlab chiqarish {0}").format(self.name),
			}
		)
		se.get_items()
		self.ensure_finished_good(se)
		se.flags.ignore_permissions = True
		try:
			se.insert()
		except Exception:
			rows = "; ".join(
				f"{d.item_code} qty={d.qty} s={d.s_warehouse} t={d.t_warehouse} fg={d.is_finished_item}" for d in se.items
			)
			frappe.log_error(title="Beton Stock Entry xatosi", message=rows)
			raise
		se.submit()

		fg = [d for d in se.items if d.is_finished_item]
		jami = sum(flt(d.amount) for d in fg)
		self.db_set(
			{
				"stock_entry": se.name,
				"jami_xarajat": jami,
				"birlik_tan_narx": flt(jami / flt(self.qty)) if flt(self.qty) else 0,
			}
		)

	def ensure_finished_good(self, se):
		"""ERPNext versiyalari orasida farq bo'lsa ham tayyor mahsulot qatori aniq bo'lsin."""
		fg_rows = [d for d in se.items if d.item_code == self.item_code and d.t_warehouse and not d.s_warehouse]
		if not fg_rows:
			se.append(
				"items",
				{
					"item_code": self.item_code,
					"qty": self.qty,
					"t_warehouse": self.tayyor_ombori,
					"is_finished_item": 1,
					"bom_no": self.bom,
				},
			)
		for d in se.items:
			if d.item_code == self.item_code and d.t_warehouse and not d.s_warehouse:
				d.is_finished_item = 1
				d.bom_no = self.bom
			elif d.s_warehouse:
				d.is_finished_item = 0

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Stock Ledger Entry", "GL Entry")
		cancel_stock_entry(self.stock_entry)
