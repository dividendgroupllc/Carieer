# Sotuv: sotuv posti (AppSheet "Ввод продажи"). Post ikkala firmaga ishlaydi: Тип = Karer yoki Beton.
# Draft -> tovarlar, xizmatlar (Погрузчик, Доставка...), to'lovlar kiritiladi.
# Завершить (Submit) -> Sales Invoice (tovarlar ombordan chiqadi + xizmatlar) + har bir to'lov uchun Payment Entry + SMS.
# Yakunlangandan keyin ham "Оплата" tugmasi bilan to'lov qo'shiladi (tolovlar jadvali allow_on_submit).
# Qarz (Долг) va holat Sales Invoice qoldig'idan hisoblanadi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money, formatdate, nowdate

from carieer.utils import get_company_currency, validate_not_internal, get_item_warehouse, get_rate, send_sms, validate_warehouse_company


def company_for_tip(tip: str) -> str:
	field = "beton_firma" if tip == "Beton" else "karer_firma"
	company = frappe.db.get_single_value("Karer Sozlamalari", field)
	if not company:
		frappe.throw(_("Karer Sozlamalari -> Sotuv posti: {0} firmasini ko'rsating").format(tip))
	return company


@frappe.whitelist()
def get_tip_company(tip: str) -> str:
	"""JS uchun: Тип -> firma (Karer Sozlamalari beton xodimiga ochiq emas, shuning uchun server orqali)."""
	return company_for_tip(tip)


class Sotuv(Document):
	# ------------------------------------------------------------ validate
	def validate(self):
		if self.docstatus == 0:
			self.company = company_for_tip(self.tip)
			validate_not_internal("Customer", self.customer, _("Firmalararo Sotuv"))
		self.set_rate()
		self.set_items()
		self.set_xizmatlar()
		self.set_tolovlar()
		self.set_totals()
		if self.docstatus == 0:
			self.status = "Draft"

	def set_rate(self):
		company_currency = get_company_currency(self.company)
		self.currency = self.currency or company_currency
		if self.currency == company_currency:
			self.conversion_rate = 1
		elif flt(self.conversion_rate) <= 1:
			self.conversion_rate = get_rate(self.currency, company_currency, self.posting_date)

	def set_items(self):
		from erpnext.stock.get_item_details import get_conversion_factor

		if not self.items:
			frappe.throw(_("Kamida bitta tovar kiriting"))
		for row in self.items:
			stock_uom, is_stock = frappe.get_cached_value("Item", row.item_code, ["stock_uom", "is_stock_item"])
			if not is_stock:
				frappe.throw(_("{0}-qator: {1} ombor tovari emas. Xizmatlarni Услуги jadvaliga kiriting").format(row.idx, row.item_code))
			if flt(row.qty) <= 0 or flt(row.rate) < 0:
				frappe.throw(_("{0}-qator: miqdor va narxni tekshiring").format(row.idx))
			row.uom = row.uom or frappe.get_cached_value("Item", row.item_code, "sales_uom") or stock_uom
			cf = flt(get_conversion_factor(row.item_code, row.uom).get("conversion_factor"))
			if not cf:
				frappe.throw(_("{0}: {1} -> {2} koeffitsiyenti yo'q (Item > UOM Conversion)").format(row.item_code, row.uom, stock_uom))
			row.conversion_factor = cf
			row.stock_qty = flt(row.qty) * cf
			row.amount = flt(flt(row.qty) * flt(row.rate), 2)
			row.currency = self.currency
			if not row.warehouse or frappe.get_cached_value("Warehouse", row.warehouse, "company") != self.company:
				row.warehouse = get_item_warehouse(row.item_code, self.company)
			if not row.warehouse:
				frappe.throw(_("{0}-qator: {1} uchun ombor topilmadi").format(row.idx, row.item_code))
			validate_warehouse_company(row.warehouse, self.company)

	def set_xizmatlar(self):
		for row in self.xizmatlar:
			if frappe.get_cached_value("Item", row.xizmat, "is_stock_item"):
				frappe.throw(_("Услуги {0}-qator: {1} ombor tovari, uni Товары jadvaliga kiriting").format(row.idx, row.xizmat))
			row.amount = flt(flt(row.qty) * flt(row.rate), 2)
			row.currency = self.currency

	def set_tolovlar(self):
		from carieer.carieer.doctype.kassa.kassa import get_kassa_info

		for row in self.tolovlar:
			info = get_kassa_info(row.mode_of_payment, self.company)
			if not info["account"]:
				frappe.throw(_("{0} to'lov turida {1} firmasi uchun kassa hisobi yo'q").format(row.mode_of_payment, self.company))
			row.valyuta = info["currency"]
			if row.valyuta == self.currency:
				row.kurs = 1
			elif flt(row.kurs) <= 0 or (flt(row.kurs) == 1 and not row.payment_entry):
				row.kurs = get_rate(row.valyuta, self.currency, row.sana or self.posting_date)
			if flt(row.summa) <= 0:
				frappe.throw(_("Оплата {0}-qator: summa 0 dan katta bo'lishi kerak").format(row.idx))
			row.sotuv_summa = flt(flt(row.summa) * flt(row.kurs), 2)
			row.currency = self.currency
			row.sana = row.sana or self.posting_date

	def set_totals(self):
		self.itog = sum(flt(r.amount) for r in self.items)
		self.xizmat_jami = sum(flt(r.amount) for r in self.xizmatlar)
		self.amount = flt(self.itog + self.xizmat_jami, 2)
		self.base_amount = flt(self.amount * flt(self.conversion_rate), 2)
		paid = sum(flt(r.sotuv_summa) for r in self.tolovlar)
		if paid > self.amount + 0.01:
			frappe.throw(_("To'lovlar ({0}) jami summadan ({1}) katta").format(paid, self.amount))
		if self.docstatus == 0:
			self.total_paid = paid
			self.outstanding_amount = flt(self.amount - paid, 2)

	# ------------------------------------------------------------ submit / cancel
	def before_submit(self):
		self.check_stock()

	def check_stock(self):
		if frappe.db.get_single_value("Stock Settings", "allow_negative_stock"):
			return
		from erpnext.stock.utils import get_stock_balance

		need = {}
		for r in self.items:
			need[(r.item_code, r.warehouse)] = need.get((r.item_code, r.warehouse), 0) + flt(r.stock_qty)
		for (item, wh), qty in need.items():
			available = flt(get_stock_balance(item, wh, self.posting_date, self.posting_time))
			if available < qty:
				frappe.throw(
					_("{0} omborida {1} yetarli emas. Bor: {2}, kerak: {3}").format(wh, item, available, qty),
					title=_("Qoldiq yetarli emas"),
				)

	def on_submit(self):
		si = self.make_sales_invoice()
		self.db_set("sales_invoice", si.name)
		self.make_payments()
		self.update_payment_status()
		self.send_notification()

	def on_update_after_submit(self):
		# "Оплата" tugmasi yoki formada qo'shilgan yangi to'lov qatorlari
		self.make_payments()
		self.update_payment_status()

	def before_update_after_submit(self):
		self.set_tolovlar()
		old = {r.name: r for r in (self.get_doc_before_save() or frappe._dict(tolovlar=[])).tolovlar}
		for row in self.tolovlar:
			before = old.get(row.name)
			if before and before.payment_entry and (flt(before.summa) != flt(row.summa) or before.mode_of_payment != row.mode_of_payment):
				frappe.throw(_("Оплата {0}-qator allaqachon o'tkazilgan, uni o'zgartirib bo'lmaydi").format(row.idx))
		removed = [r for name, r in old.items() if r.payment_entry and name not in {x.name for x in self.tolovlar}]
		if removed:
			frappe.throw(_("O'tkazilgan to'lovni o'chirib bo'lmaydi. Payment Entry'ni bekor qiling: {0}").format(removed[0].payment_entry))
		outstanding = flt(frappe.db.get_value("Sotuv", self.name, "outstanding_amount"))
		new_sum = sum(flt(r.sotuv_summa) for r in self.tolovlar if not r.payment_entry)
		if new_sum > outstanding + 0.01:
			frappe.throw(_("To'lov ({0}) qarzdan ({1}) katta").format(new_sum, outstanding))

	def on_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry", "Payment Entry")
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
		si = frappe.new_doc("Sales Invoice")
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
				"ignore_pricing_rule": 1,
				"disable_rounded_total": 1,
				"remarks": _("Sotuv {0}. Mashina: {1}").format(self.name, self.mashina_raqami or "-"),
			}
		)
		for r in self.items:
			si.append(
				"items",
				{
					"item_code": r.item_code,
					"qty": r.qty,
					"uom": r.uom,
					"conversion_factor": r.conversion_factor,
					"rate": r.rate,
					"warehouse": r.warehouse,
					"allow_zero_valuation_rate": 1,  # qazib olingan tovar tan narxi 0
				},
			)
		for r in self.xizmatlar:
			si.append("items", {"item_code": r.xizmat, "qty": r.qty, "rate": r.rate})
		si.flags.ignore_permissions = True
		si.set_missing_values()
		# set_missing_values narxni price list'dan qayta qo'yishi mumkin -> o'zimiznikini qaytaramiz
		rates = [r.rate for r in self.items] + [r.rate for r in self.xizmatlar]
		for row, rate in zip(si.items, rates, strict=True):
			row.rate = rate
			row.price_list_rate = rate
			row.discount_percentage = 0
			row.margin_rate_or_amount = 0
		si.conversion_rate = self.conversion_rate
		si.insert()
		si.submit()
		return si

	def make_payments(self):
		for row in self.tolovlar:
			if row.payment_entry:
				continue
			pe = make_payment_entry(self, row)
			row.db_set("payment_entry", pe.name)

	def update_payment_status(self):
		"""Sales Invoice qoldig'iga qarab to'lov holati va qarz."""
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
		outstanding = max(flt(outstanding, 2), 0)
		total_paid = flt(flt(si.grand_total) - outstanding, 2)
		status = "To'langan" if outstanding <= 0.01 else ("Qisman to'langan" if total_paid > 0 else "To'lanmagan")
		self.db_set({"outstanding_amount": outstanding, "total_paid": total_paid, "status": status})

	def send_notification(self):
		settings = frappe.get_cached_doc("Karer Sozlamalari")
		if not settings.sms_yoqilgan or not self.mobile_no:
			return
		self.reload()
		first = self.items[0]
		tpl = settings.sms_shablon or "{customer}: {item} {qty} {uom} = {amount} {currency}"
		msg = tpl.format(
			customer=self.customer_name or self.customer,
			date=formatdate(self.posting_date),
			item=", ".join(r.item_name or r.item_code for r in self.items),
			qty=first.qty,
			uom=first.uom,
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


def make_payment_entry(doc: "Sotuv", row):
	"""Bitta to'lov qatori -> Sales Invoice'ga qarshi Payment Entry.
	row.summa - kassa valyutasida, row.sotuv_summa - sotuv valyutasida."""
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

	si = frappe.db.get_value(
		"Sales Invoice", doc.sales_invoice, ["currency", "party_account_currency", "conversion_rate"], as_dict=True
	)
	account = get_bank_cash_account(row.mode_of_payment, doc.company)["account"]
	# debitor hisobi valyutasidagi summa
	party_amount = (
		flt(row.sotuv_summa) if si.party_account_currency == si.currency else flt(row.sotuv_summa) * flt(si.conversion_rate)
	)
	pe = get_payment_entry(
		"Sales Invoice",
		doc.sales_invoice,
		party_amount=party_amount,
		bank_account=account,
		bank_amount=flt(row.summa),
	)
	pe.mode_of_payment = row.mode_of_payment
	pe.posting_date = row.sana or nowdate()
	pe.reference_no = doc.name
	pe.reference_date = pe.posting_date
	pe.remarks = " · ".join(filter(None, (_("Sotuv {0}").format(doc.name), row.kim, row.izoh)))
	pe.flags.ignore_permissions = True
	pe.insert()
	pe.submit()
	return pe


@frappe.whitelist()
def tolov_qabul_qilish(name: str, amount: float, mode_of_payment: str, kim: str | None = None, izoh: str | None = None):
	"""Yakunlangan sotuvga to'lov qo'shish ("Оплата" tugmasi). amount - kassa valyutasida."""
	doc = frappe.get_doc("Sotuv", name)
	doc.check_permission("submit")
	if doc.docstatus != 1:
		frappe.throw(_("Avval sotuvni yakunlang (Завершить)"))
	doc.append("tolovlar", {"sana": nowdate(), "mode_of_payment": mode_of_payment, "summa": flt(amount), "kim": kim, "izoh": izoh})
	doc.save()
	return doc.tolovlar[-1].payment_entry


def on_payment_entry_change(pe, method=None):
	"""hooks.py -> Payment Entry on_submit/on_cancel: tashqaridan kiritilgan to'lovlar ham holatni yangilasin."""
	for ref in pe.references:
		if ref.reference_doctype != "Sales Invoice":
			continue
		for name in frappe.get_all("Sotuv", filters={"sales_invoice": ref.reference_name, "docstatus": 1}, pluck="name"):
			frappe.get_doc("Sotuv", name).update_payment_status()
