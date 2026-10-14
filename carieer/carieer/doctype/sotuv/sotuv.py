# Sotuv - karer sotuv posti.
#
#   Saqlash (Save)     -> summalar, ombor, kurs, qarz hisoblanadi (hammasi serverda)
#   Tasdiqlash (Submit) -> Sales Invoice (tovar ombordan chiqadi, mijozga qarz) + har bir to'lov qatori uchun
#                         Payment Entry (kassaga kirim) + SMS
#   Keyinroq to'lov    -> «Оплаты» jadvaliga qator qo'shib «Update» bosiladi -> yangi Payment Entry

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money, formatdate, nowdate

from carieer.carieer.doctype.sotuv.helpers import allow_negative_stock, get_adjustment_account, get_usd_rate
from carieer.permissions import check_company
from carieer.utils import (
	apply_advances,
	as_admin,
	company_for_tip,
	get_company_currency,
	get_item_warehouse,
	get_kassa_info,
	get_rate,
	send_sms,
	validate_warehouse_company,
)

def get_selling_price(item_code: str, uom: str | None, currency: str) -> float:
	"""Narx kiritilmagan bo'lsa - sotuv narxlar ro'yxatidan (Selling Settings -> standart, odatda «Standard Selling»)."""
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"
	prices = frappe.get_all(
		"Item Price",
		filters={"item_code": item_code, "price_list": price_list, "currency": currency, "selling": 1},
		fields=["price_list_rate", "uom"],
		order_by="valid_from desc",
	)
	for p in prices:
		if p.uom in (uom, None, ""):
			return flt(p.price_list_rate)
	return 0


class Sotuv(Document):
	# ------------------------------------------------------------ validate
	def validate(self):
		if self.docstatus == 0:
			self.company = company_for_tip(self.tip)
			check_company(self.company)
		self.set_rate()
		if self.korrektirovka:
			self.set_korrektirovka()
		else:
			self.set_items()
			self.set_xizmatlar()
			self.set_tolovlar()
			self.set_totals()
		self.set_summa_usd()
		if self.docstatus == 0:
			self.status = "Draft"

	def set_rate(self):
		company_currency = get_company_currency(self.company)
		self.currency = self.currency or company_currency
		if self.korrektirovka:
			self.currency = company_currency  # korrektirovka firma valyutasida (so'm)
		if self.currency == company_currency:
			self.conversion_rate = 1
		elif self.docstatus == 0 or not flt(self.conversion_rate):
			self.conversion_rate = get_rate(self.currency, company_currency, self.posting_date)

	def set_korrektirovka(self):
		"""Корректировка: tovarsiz tuzatish (jadvalda «Наименование» bo'sh, Цена +/-). Faqat mijoz va summa."""
		if not flt(self.korrektirovka_summa):
			frappe.throw(_("Korrektirovka summasini kiriting (musbat yoki manfiy)"))
		if self.items or self.xizmatlar or self.tolovlar:
			frappe.throw(_("Korrektirovkada tovar, xizmat va to'lov bo'lmaydi: ularni olib tashlang"))
		self.itog = self.xizmat_jami = 0
		self.amount = flt(self.korrektirovka_summa, 2)
		self.base_amount = self.amount
		self.total_paid = 0
		self.outstanding_amount = 0
		self.tovarlar = _("Корректировка")

	def set_summa_usd(self):
		"""«Сумма $»: so'mdagi summa / shu kungi USD kursi (kurs yo'q bo'lsa bo'sh)."""
		if self.currency == "USD":
			self.summa_usd = flt(self.amount, 2)
			return
		rate = get_usd_rate(self.posting_date, get_company_currency(self.company))
		self.summa_usd = flt(flt(self.base_amount) / rate, 2) if rate else 0

	def set_items(self):
		from erpnext.stock.get_item_details import get_conversion_factor

		if not self.items:
			frappe.throw(_("Kamida bitta tovar kiriting"))
		for row in self.items:
			stock_uom, sales_uom, is_stock = frappe.get_cached_value(
				"Item", row.item_code, ["stock_uom", "sales_uom", "is_stock_item"]
			)
			if not is_stock:
				frappe.throw(
					_(
						"Товары {0}-qator: {1} ombor tovari emas. Xizmatlarni «Услуги» jadvaliga kiriting"
					).format(row.idx, row.item_code)
				)
			if flt(row.qty) <= 0 or flt(row.rate) < 0:
				frappe.throw(_("Товары {0}-qator: miqdor va narxni tekshiring").format(row.idx))
			row.uom = row.uom or sales_uom or stock_uom
			cf = flt(get_conversion_factor(row.item_code, row.uom).get("conversion_factor"))
			if not cf:
				frappe.throw(
					_("{0}: {1} -> {2} koeffitsiyenti yo'q (Item -> UOM Conversion)").format(
						row.item_code, row.uom, stock_uom
					)
				)
			row.conversion_factor = cf
			row.stock_qty = flt(row.qty) * cf
			if not flt(row.rate) and self.docstatus == 0:
				# narx ro'yxatda yo'q bo'lsa 0 qoladi (jadvaldagidek: bepul yetkazma, tuzatish qatorlari)
				row.rate = get_selling_price(row.item_code, row.uom, self.currency)
			row.amount = flt(flt(row.qty) * flt(row.rate), 2)
			row.currency = self.currency
			if (
				not row.warehouse
				or frappe.get_cached_value("Warehouse", row.warehouse, "company") != self.company
			):
				row.warehouse = get_item_warehouse(row.item_code, self.company)
			if not row.warehouse:
				frappe.throw(
					_("Товары {0}-qator: {1} uchun ombor topilmadi (Zavod -> Asosiy ombor)").format(
						row.idx, row.item_code
					)
				)
			validate_warehouse_company(row.warehouse, self.company)

	def set_xizmatlar(self):
		for row in self.xizmatlar:
			if frappe.get_cached_value("Item", row.xizmat, "is_stock_item"):
				frappe.throw(
					_("Услуги {0}-qator: {1} ombor tovari, uni «Товары» jadvaliga kiriting").format(
						row.idx, row.xizmat
					)
				)
			row.qty = flt(row.qty) or 1
			row.amount = flt(flt(row.qty) * flt(row.rate), 2)
			row.currency = self.currency

	def set_tolovlar(self):
		for row in self.tolovlar:
			if row.payment_entry:
				continue  # o'tkazilgan qator o'zgarmaydi
			info = get_kassa_info(row.mode_of_payment, self.company)
			if not info.account:
				frappe.throw(
					_(
						"Оплаты {0}-qator: {1} kassasida {2} firmasi uchun hisob yo'q (Mode of Payment -> Accounts)"
					).format(row.idx, row.mode_of_payment, self.company)
				)
			row.valyuta = info.currency
			row.sana = row.sana or nowdate()
			if row.valyuta == self.currency:
				row.kurs = 1
			elif flt(row.kurs) <= 0 or flt(row.kurs) == 1:
				base = get_company_currency(self.company)
				row.kurs = get_rate(row.valyuta, base, row.sana) / get_rate(self.currency, base, row.sana)
			if flt(row.summa) <= 0:
				frappe.throw(_("Оплаты {0}-qator: summa 0 dan katta bo'lishi kerak").format(row.idx))
			row.sotuv_summa = flt(flt(row.summa) * flt(row.kurs), 2)
			row.currency = self.currency

	def set_totals(self):
		self.itog = flt(sum(flt(r.amount) for r in self.items), 2)
		self.xizmat_jami = flt(sum(flt(r.amount) for r in self.xizmatlar), 2)
		self.amount = flt(self.itog + self.xizmat_jami, 2)
		self.tovarlar = ", ".join(
			f"{r.item_name or r.item_code} {flt(r.qty):g} {r.uom or ''} × {flt(r.rate):,.0f}".replace(",", " ")
			for r in self.items
		)[:140]
		self.base_amount = flt(self.amount * flt(self.conversion_rate or 1), 2)
		if self.docstatus == 0:
			paid = flt(sum(flt(r.sotuv_summa) for r in self.tolovlar), 2)
			if paid > self.amount + 0.01:
				frappe.throw(_("To'lovlar ({0}) jami summadan ({1}) katta").format(paid, self.amount))
			self.total_paid = paid
			self.outstanding_amount = flt(self.amount - paid, 2)

	# ------------------------------------------------------------ submit / cancel
	def before_submit(self):
		if not self.korrektirovka:
			self.check_stock()

	def check_stock(self):
		"""Jadvalda qoldiq tekshiruvi yo'q: sotuv bloklanmaydi, qoldiq yetmasa ogohlantirish chiqadi."""
		from erpnext.stock.utils import get_stock_balance

		need = {}
		for r in self.items:
			need[(r.item_code, r.warehouse)] = need.get((r.item_code, r.warehouse), 0) + flt(r.stock_qty)
		for (item, wh), qty in need.items():
			available = flt(get_stock_balance(item, wh, self.posting_date, self.posting_time))
			if available + 1e-6 < qty:
				uom = frappe.get_cached_value("Item", item, "stock_uom")
				frappe.msgprint(
					_("<b>{0}</b> omborida <b>{1}</b> yetarli emas: bor {2} {4}, kerak {3} {4}. Qoldiq minusga tushadi.").format(
						wh, item, flt(available), qty, uom
					),
					title=_("Qoldiq yetarli emas"),
					indicator="orange",
					alert=True,
				)

	def on_submit(self):
		if self.korrektirovka:
			je = self.make_korrektirovka_entry()
			self.db_set({"journal_entry": je.name, "status": "Korrektirovka"})
			return
		with allow_negative_stock():
			si = self.make_sales_invoice()
		self.db_set("sales_invoice", si.name)
		self.set_cost_columns(si)
		self.make_payments()
		# mijoz oldindan (Kassa orqali) avans bergan bo'lsa - qolgan qarz avansdan yopiladi
		with as_admin():
			apply_advances(self.company, "Customer", self.customer, "Sales Invoice", si.name)
		self.update_payment_status()
		self.send_notification()

	def before_update_after_submit(self):
		old = {r.name: r for r in (self.get_doc_before_save() or frappe._dict(tolovlar=[])).tolovlar}
		for row in self.tolovlar:
			before = old.get(row.name)
			changed = before and (
				flt(before.summa) != flt(row.summa) or before.mode_of_payment != row.mode_of_payment
			)
			if not (changed and before.payment_entry):
				continue
			if is_posted(before.payment_entry):
				frappe.throw(
					_("Оплаты {0}-qator allaqachon o'tkazilgan, uni o'zgartirib bo'lmaydi").format(row.idx)
				)
			# Payment Entry o'z formasidan bekor qilingan: qator tuzatiladi va qaytadan o'tkaziladi
			row.payment_entry = None
		self.set_tolovlar()
		current = {r.name for r in self.tolovlar}
		removed = [r for name, r in old.items() if is_posted(r.payment_entry) and name not in current]
		if removed:
			frappe.throw(
				_(
					"O'tkazilgan to'lovni o'chirib bo'lmaydi. Kerak bo'lsa Payment Entry'ni bekor qiling: {0}"
				).format(removed[0].payment_entry)
			)
		outstanding = flt(frappe.db.get_value("Sotuv", self.name, "outstanding_amount"))
		new_sum = sum(flt(r.sotuv_summa) for r in self.tolovlar if not r.payment_entry)
		if new_sum > outstanding + 0.01:
			frappe.throw(_("Yangi to'lov ({0}) qarzdan ({1}) katta").format(new_sum, outstanding))

	def on_update_after_submit(self):
		self.make_payments()
		self.update_payment_status()

	def on_cancel(self):
		self.ignore_linked_doctypes = (
			"GL Entry",
			"Stock Ledger Entry",
			"Payment Ledger Entry",
			"Payment Entry",
			"Journal Entry",
		)
		if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			je.flags.ignore_permissions = True
			je.cancel()
		# Faqat shu Sotuv'ning o'z to'lovlari bekor qilinadi. Kassa orqali kiritilgan to'lovlar bekor qilinmaydi -
		# Sales Invoice bekor bo'lganda ulardan uziladi va mijozning avansi bo'lib qoladi
		# (Accounts Settings -> Unlink Payment on Cancellation of Invoice, setup_karer yoqadi).
		for row in self.tolovlar:
			if (
				row.payment_entry
				and frappe.db.get_value("Payment Entry", row.payment_entry, "docstatus") == 1
			):
				pe_doc = frappe.get_doc("Payment Entry", row.payment_entry)
				pe_doc.flags.ignore_permissions = True
				pe_doc.cancel()
		if self.sales_invoice:
			si = frappe.get_doc("Sales Invoice", self.sales_invoice)
			if si.docstatus == 1:
				si.flags.ignore_permissions = True
				with allow_negative_stock():
					si.cancel()
		self.db_set("status", "Cancelled")

	# ------------------------------------------------------------ hujjatlar
	def set_cost_columns(self, si):
		"""«Цена СС» / «Сумма СС»: tasdiqlangandan keyin ombor tan narxi (Sales Invoice qatoridagi incoming_rate)."""
		si.reload()
		for row, si_row in zip(self.items, si.items[: len(self.items)], strict=True):
			narx = flt(si_row.incoming_rate) * flt(row.conversion_factor or 1)
			row.db_set({"narx_ss": narx, "summa_ss": flt(narx * flt(row.qty), 2)})

	def make_korrektirovka_entry(self):
		"""Mijoz qarzini tovarsiz tuzatish: Journal Entry (Dt mijoz / Kt korrektirovka hisobi; manfiy bo'lsa teskari).
		Akt sverka, Оборотка va Qarzdorlik'da ko'rinadi, foyda-zarar (P&L) ga kirmaydi."""
		from erpnext.accounts.party import get_party_account

		amount = flt(self.amount, 2)
		party_account = get_party_account("Customer", self.customer, self.company)
		adjustment = get_adjustment_account(self.company)
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.company
		je.posting_date = self.posting_date
		je.cheque_no = self.name
		je.cheque_date = self.posting_date
		je.user_remark = " | ".join(x for x in (_("Корректировка {0}").format(self.name), self.izoh) if x)
		je.append(
			"accounts",
			{
				"account": party_account,
				"party_type": "Customer",
				"party": self.customer,
				"debit_in_account_currency": amount if amount > 0 else 0,
				"credit_in_account_currency": -amount if amount < 0 else 0,
			},
		)
		je.append(
			"accounts",
			{
				"account": adjustment,
				"debit_in_account_currency": -amount if amount < 0 else 0,
				"credit_in_account_currency": amount if amount > 0 else 0,
			},
		)
		je.flags.ignore_permissions = True
		je.insert()
		je.submit()
		return je

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
		# set_missing_values narxni Price List'dan qayta qo'yishi mumkin -> sotuv narxi qaytariladi
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
		"""Sales Invoice qoldig'iga qarab to'lov holati va qarz (tashqaridan kiritilgan to'lovlar ham hisobga olinadi)."""
		if not self.sales_invoice:
			return
		si = frappe.db.get_value(
			"Sales Invoice",
			self.sales_invoice,
			[
				"outstanding_amount",
				"grand_total",
				"currency",
				"party_account_currency",
				"conversion_rate",
				"docstatus",
			],
			as_dict=True,
		)
		if not si or si.docstatus != 1:
			return
		outstanding = flt(si.outstanding_amount)
		if si.party_account_currency != si.currency:
			outstanding = outstanding / flt(si.conversion_rate or 1)
		outstanding = max(flt(outstanding, 2), 0)
		total_paid = flt(flt(si.grand_total) - outstanding, 2)
		status = (
			"To'langan" if outstanding <= 0.01 else ("Qisman to'langan" if total_paid > 0 else "To'lanmagan")
		)
		self.db_set({"outstanding_amount": outstanding, "total_paid": total_paid, "status": status})

	def send_notification(self):
		settings = frappe.get_cached_doc("Karer Sozlamalari")
		if not settings.sms_yoqilgan or not self.mobile_no:
			return
		self.reload()
		first = self.items[0]
		tpl = settings.sms_shablon or "{customer}: {item} = {amount} {currency}"
		try:
			msg = tpl.format(
				customer=self.customer_name or self.customer,
				date=formatdate(self.posting_date),
				item=", ".join(f"{r.item_name or r.item_code} {r.qty} {r.uom}" for r in self.items),
				qty=first.qty,
				uom=first.uom,
				amount=fmt_money(self.amount, currency=None),
				currency=self.currency,
				paid=fmt_money(self.total_paid, currency=None),
				outstanding=fmt_money(self.outstanding_amount, currency=None),
				vehicle=self.mashina_raqami or "",
				name=self.name,
			)
		except (KeyError, IndexError, ValueError):
			frappe.log_error(title="Karer SMS shabloni noto'g'ri")
			return
		frappe.enqueue(send_sms, numbers=[self.mobile_no], message=msg, enqueue_after_commit=True)


# ---------------------------------------------------------------- forma (sotuv.js)
@frappe.whitelist()
def get_item_defaults(item_code: str, tip: str, currency: str | None = None) -> dict:
	"""Forma: tovar tanlanganda birlik, narx (Item Price) va sotuvchi firma ombori o'zi to'ldiriladi."""
	frappe.has_permission("Sotuv", "read", throw=True)
	company = company_for_tip(tip)
	stock_uom, sales_uom, item_name = frappe.get_cached_value(
		"Item", item_code, ["stock_uom", "sales_uom", "item_name"]
	)
	uom = sales_uom or stock_uom
	currency = currency or get_company_currency(company)
	return {
		"item_name": item_name,
		"uom": uom,
		"rate": get_selling_price(item_code, uom, currency),
		"warehouse": get_item_warehouse(item_code, company),
	}


# ---------------------------------------------------------------- module level
def is_posted(payment_entry: str | None) -> bool:
	"""To'lov qatori haqiqatan o'tkazilganmi (Payment Entry tasdiqlangan, bekor qilinmagan)."""
	return bool(payment_entry) and frappe.db.get_value("Payment Entry", payment_entry, "docstatus") == 1


def make_payment_entry(doc: "Sotuv", row):
	"""Bitta to'lov qatori -> Sales Invoice'ga qarshi Payment Entry.
	row.summa - kassa valyutasida, row.sotuv_summa - sotuv valyutasida."""
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

	si = frappe.db.get_value(
		"Sales Invoice",
		doc.sales_invoice,
		["currency", "party_account_currency", "conversion_rate", "outstanding_amount"],
		as_dict=True,
	)
	account = get_bank_cash_account(row.mode_of_payment, doc.company)["account"]
	cash_currency = frappe.get_cached_value("Account", account, "account_currency")
	# debitor hisobi valyutasidagi summa
	party_amount = (
		flt(row.sotuv_summa)
		if si.party_account_currency == si.currency
		else flt(row.sotuv_summa) * flt(si.conversion_rate)
	)
	# Dollarda sotilgan, mijoz hisobi va kassa so'mda: ERPNext kassaga party_amount yozadi (bank_amount e'tiborga
	# olinmaydi). Kassaga aynan olingan pul yozilishi kerak, qarz esa sotuv kursida yopiladi - farq kurs farqi.
	fx_case = si.party_account_currency != si.currency and cash_currency == si.party_account_currency
	allocate = min(party_amount, flt(si.outstanding_amount))
	if fx_case:
		party_amount = flt(row.summa)
	pe = get_payment_entry(
		"Sales Invoice",
		doc.sales_invoice,
		party_amount=party_amount,
		bank_account=account,
		bank_amount=flt(row.summa),
	)
	if fx_case:
		for ref in pe.references:
			if ref.reference_name == doc.sales_invoice:
				ref.allocated_amount = flt(allocate, 2)
		diff = flt(allocate - party_amount, 2)  # musbat - kurs zarari, manfiy - kurs foydasi
		if abs(diff) >= 0.01:
			pe.append(
				"deductions",
				{
					"account": frappe.get_cached_value("Company", doc.company, "exchange_gain_loss_account"),
					"cost_center": frappe.get_cached_value("Company", doc.company, "cost_center"),
					"amount": diff,
				},
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


def on_payment_entry_change(pe, method=None):
	"""hooks.py: Payment Entry on_submit / on_cancel - tashqaridan (Kassa yoki Payment Entry formasidan)
	kiritilgan to'lovlar ham Sotuv holati va qarzini yangilasin."""
	for ref in pe.references:
		if ref.reference_doctype != "Sales Invoice":
			continue
		for name in frappe.get_all(
			"Sotuv", filters={"sales_invoice": ref.reference_name, "docstatus": 1}, pluck="name"
		):
			frappe.get_doc("Sotuv", name).update_payment_status()
