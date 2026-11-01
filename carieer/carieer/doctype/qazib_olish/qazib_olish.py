# Qazib Olish (Google Sheets «Производство»): karerdan qazib olingan tovar - Дата, Наименование, Единица,
# Кол-во, Цех, Сотрудник. Tasdiqlanganda tovar omborga kirim bo'ladi: Stock Entry «Material Receipt»,
# tan narxi 0 (tosh yerdan qazib olinadi, sotib olinmaydi - jadvaldagi «Сырьевая себестоимость» ham 0).
# Beton zavodida bu hujjat yo'q: beton Sotuv'da retsept (BOM) bo'yicha o'zi ishlab chiqariladi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from carieer.carieer.doctype.sotuv.helpers import allow_negative_stock
from carieer.carieer.report.common import fmt_qty
from carieer.permissions import check_company
from carieer.utils import get_zavod, validate_warehouse_company

# Forma: tovar ro'yxatida faqat karer mahsulotlari (Клинец, Шебень, Қум, Тош ...)
TOVAR_GURUHLARI = ("Полуфабрикат", "Готовый продукт")
# Stock Entry Type (patches/qazib_olish_stock_entry_type)
QAZIB_TURI = "Qazib olish"


class QazibOlish(Document):
	def validate(self):
		self.company = self.company or get_defaults().get("company")
		zavod = get_zavod(self.company)
		if not zavod:
			frappe.throw(
				_("{0} uchun Zavod yozuvi yo'q (Karer -> Справочники -> Zavod)").format(self.company),
				title=_("Zavod topilmadi"),
			)
		if zavod.ishlab_chiqarish:
			frappe.throw(
				_(
					"Qazib olish faqat karerda bo'ladi. {0} - ishlab chiqarish zavodi: mahsulot u yerda "
					"Sotuv'da retsept bo'yicha o'zi chiqariladi."
				).format(self.company),
				title=_("Noto'g'ri firma"),
			)
		self.warehouse = self.warehouse or zavod.asosiy_ombor
		if not self.warehouse:
			frappe.throw(_("Omborni tanlang (yoki Zavod'da asosiy omborni ko'rsating)"))
		validate_warehouse_company(self.warehouse, self.company)
		if frappe.get_cached_value("Warehouse", self.warehouse, "is_group"):
			frappe.throw(_("{0} - omborlar guruhi. Aniq omborni tanlang").format(self.warehouse))
		self.validate_items()
		self.total_qty = flt(sum(flt(r.qty) for r in self.items), 3)
		self.title = items_title(self.items)

	def validate_items(self):
		if not self.items:
			frappe.throw(_("Kamida bitta tovar kiriting"))
		for row in self.items:
			if flt(row.qty) <= 0:
				frappe.throw(_("{0}-qator: miqdor 0 dan katta bo'lishi kerak").format(row.idx))
			# Float ustuni decimal(21,9): 10^12 dan kattasi bazaga sig'maydi (MySQL «Out of range» xatosi)
			if flt(row.qty) >= 1e11:
				frappe.throw(
					_("{0}-qator: miqdor juda katta ({1}). Raqamni tekshiring").format(row.idx, row.qty)
				)
			item = frappe.get_cached_value(
				"Item",
				row.item_code,
				["item_name", "stock_uom", "is_stock_item", "default_bom"],
				as_dict=True,
			)
			if not item.is_stock_item:
				frappe.throw(
					_("{0}-qator: {1} ombor tovari emas (Maintain Stock)").format(row.idx, row.item_code)
				)
			if item.default_bom:
				frappe.throw(
					_("{0}-qator: {1} retsept bo'yicha ishlab chiqariladi (Beton), qazib olinmaydi").format(
						row.idx, row.item_code
					)
				)
			row.item_name = item.item_name
			row.uom = item.stock_uom
			row.tsex = row.tsex or default_tsex(row.item_name)

	def on_submit(self):
		se = frappe.new_doc("Stock Entry")
		se.update(
			{
				# o'z turi (purpose - Material Receipt): ro'yxat va hisobotlarda «Qazib olish» deb ajraladi
				"stock_entry_type": (
					QAZIB_TURI if frappe.db.exists("Stock Entry Type", QAZIB_TURI) else "Material Receipt"
				),
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
					"uom": row.uom,
					"stock_uom": row.uom,
					"conversion_factor": 1,
					"t_warehouse": self.warehouse,
					"basic_rate": 0,
					"allow_zero_valuation_rate": 1,
				},
			)
		# hujjat tizim nomidan: operatorga Stock Entry'ni qo'lda yaratish ruxsati shart emas
		se.flags.ignore_permissions = True
		se.insert()
		se.submit()
		self.db_set("stock_entry", se.name)

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Stock Ledger Entry", "GL Entry")
		if self.stock_entry and frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus") == 1:
			se = frappe.get_doc("Stock Entry", self.stock_entry)
			se.flags.ignore_permissions = True
			# tovar allaqachon sotilgan bo'lsa ham bekor qilinadi (Sotuv kabi qoldiq minusga tushishi mumkin)
			with allow_negative_stock():
				se.cancel()


def items_title(items) -> str:
	"""Ro'yxat va havolalarda ko'rinadigan nom: «Шебень 120 Куб, Клинец 80 Куб»."""
	return ", ".join(
		f"{r.item_name or r.item_code} {fmt_qty(r.qty)} {r.uom or ''}".strip() for r in items
	)[:140]


def default_tsex(item_name: str | None) -> str | None:
	"""Tovar nomidan цех: «Шебень» -> «Шебень цех» (jadvaldagi ro'yxatda bo'lsa)."""
	options = (frappe.get_meta("Qazib Olish Tovar").get_field("tsex").options or "").split("\n")
	tsex = f"{item_name} цех" if item_name else None
	return tsex if tsex in options else None


@frappe.whitelist()
def get_defaults(company: str | None = None) -> dict:
	"""Yangi hujjat: karer firmasi (ishlab chiqarishi yo'q zavod), uning asosiy ombori va tanlash mumkin
	bo'lgan firmalar."""
	frappe.has_permission("Qazib Olish", "read", throw=True)
	companies = [
		c
		for c in frappe.get_all(
			"Zavod",
			filters={"ishlab_chiqarish": 0, "company": ["is", "set"]},
			pluck="company",
			order_by="creation asc",
		)
		if check_company(c, throw=False)
	]
	if company not in companies:
		company = companies[0] if companies else None
	return {
		"company": company,
		"warehouse": get_zavod(company).get("asosiy_ombor") if company else None,
		"companies": companies,
		"tovar_guruhlari": TOVAR_GURUHLARI,
	}
