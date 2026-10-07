# Sotuv - sotuv posti. Post ikkala zavodga ishlaydi: «Тип» = Karer yoki Beton -> firma o'zi qo'yiladi.
#
#   Saqlash (Save)     -> summalar, ombor, kurs, qarz hisoblanadi (hammasi serverda, JS yo'q)
#   Tasdiqlash (Submit) -> Sales Invoice (tovar ombordan chiqadi, mijozga qarz) + har bir to'lov qatori uchun
#                         Payment Entry (kassaga kirim) + SMS
#   Keyinroq to'lov    -> «Оплаты» jadvaliga qator qo'shib «Update» bosiladi -> yangi Payment Entry
#
# Mijoz o'zimizning ikkinchi firmamiz bo'lsa (ichki mijoz) bu - firmalararo sotuv / perexod:
#   sotuvchida Sales Invoice, xaridor firmada avtomatik Purchase Invoice (tovar uning xomashyo omboriga kiradi).
#   Bunday sotuvda pul «Firmalararo To'lov» orqali to'lanadi (ikkala kitobga yoziladi).

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money, formatdate, nowdate

from carieer.utils import (
	apply_advances,
	as_admin,
	company_for_tip,
	ensure_inter_company_parties,
	get_company_currency,
	get_internal_company,
	get_item_warehouse,
	get_kassa_info,
	get_rate,
	get_zavod,
	make_inter_company_purchase_invoice,
	send_sms,
	validate_warehouse_company,
)

INTER_COMPANY_PRICE_LIST = "Firmalararo narx"


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
			self.ichki_firma = get_internal_company("Customer", self.customer)
			if self.ichki_firma == self.company:
				frappe.throw(_("Firma o'ziga o'zi sotolmaydi"))
		self.set_rate()
		self.set_items()
		self.set_xizmatlar()
		self.set_tolovlar()
		self.set_totals()
		if self.docstatus == 0:
			self.status = "Draft"

	def set_rate(self):
		company_currency = get_company_currency(self.company)
		if self.ichki_firma:
			# ERPNext talabi: firmalararo hujjat firma valyutasida bo'ladi
			self.currency = company_currency
		self.currency = self.currency or company_currency
		if self.currency == company_currency:
			self.conversion_rate = 1
		elif self.docstatus == 0 or not flt(self.conversion_rate):
			self.conversion_rate = get_rate(self.currency, company_currency, self.posting_date)

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
				row.rate = get_selling_price(row.item_code, row.uom, self.currency)
				if not row.rate:
					frappe.throw(
						_(
							"Товары {0}-qator: {1} narxini kiriting yoki «Narxlar (Item Price)» ga {2} narx qo'shing"
						).format(row.idx, row.item_code, self.currency)
					)
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
		if self.ichki_firma and self.tolovlar:
			frappe.throw(
				_("Ichki firmaga sotuvda to'lov shu yerda olinmaydi: «Firmalararo To'lov» orqali kiriting"),
				title=_("Firmalararo sotuv"),
			)
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
		self.base_amount = flt(self.amount * flt(self.conversion_rate or 1), 2)
		if self.docstatus == 0:
			paid = flt(sum(flt(r.sotuv_summa) for r in self.tolovlar), 2)
			if paid > self.amount + 0.01:
				frappe.throw(_("To'lovlar ({0}) jami summadan ({1}) katta").format(paid, self.amount))
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
			if available + 1e-6 < qty:
				uom = frappe.get_cached_value("Item", item, "stock_uom")
				# boshqa omborlarda bormi (o'z firmasi va ikkinchi firma) - operator qayerdan olishni bilsin
				boshqa = frappe.db.sql(
					"""select b.warehouse, b.actual_qty, w.company from `tabBin` b join `tabWarehouse` w on w.name = b.warehouse
					where b.item_code = %s and b.actual_qty > 0 and b.warehouse != %s order by b.actual_qty desc limit 5""",
					(item, wh),
					as_dict=True,
				)
				hint = (
					"<br>"
					+ _("Boshqa omborlarda: {0}").format(
						", ".join(f"{b.warehouse} ({b.company}) — {flt(b.actual_qty):g} {uom}" for b in boshqa)
					)
					if boshqa
					else "<br>" + _("Bu tovar hech qaysi omborda yo'q.")
				)
				frappe.throw(
					_(
						"<b>{0}</b> omborida <b>{1}</b> yetarli emas: bor {2} {5}, kerak {3} {5}.{4}<br><br>"
						"Tovarni kiritish: ikkinchi firmadan olinsa - o'sha firma <b>Sotuv</b> qiladi (Клиент = {6}) va "
						"tasdiqlaydi (to'lov shart emas, qarzga ham bo'ladi); tashqaridan olinsa - <b>Xarid fakturasi</b> "
						"(Update Stock ✓)."
					).format(wh, item, flt(available), qty, hint, uom, self.company),
					title=_("Qoldiq yetarli emas"),
				)

	def on_submit(self):
		if self.ichki_firma:
			with as_admin():
				ensure_inter_company_parties(self.company, self.ichki_firma)
				si = self.make_sales_invoice()
				pi = self.make_purchase_invoice(si)
				# xaridor firma oldindan pul bergan bo'lsa (Firmalararo To'lov avansi) - ikkala kitobda tovarga o'tadi
				apply_advances(self.company, "Customer", self.customer, "Sales Invoice", si.name)
				apply_advances(self.ichki_firma, "Supplier", pi.supplier, "Purchase Invoice", pi.name)
			self.db_set({"sales_invoice": si.name, "purchase_invoice": pi.name})
		else:
			si = self.make_sales_invoice()
			self.db_set("sales_invoice", si.name)
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
		)
		with as_admin():
			if (
				self.purchase_invoice
				and frappe.db.get_value("Purchase Invoice", self.purchase_invoice, "docstatus") == 1
			):
				pi = frappe.get_doc("Purchase Invoice", self.purchase_invoice)
				pi.flags.ignore_permissions = True
				pi.cancel()
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
				si.cancel()
		self.db_set("status", "Cancelled")

	# ------------------------------------------------------------ hujjatlar
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
		if self.ichki_firma:
			si.selling_price_list = get_inter_company_price_list(self.currency)
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

	def make_purchase_invoice(self, si):
		"""Firmalararo: xaridor firmada Purchase Invoice (update_stock) -> tovar uning xomashyo omboriga kiradi."""
		buyer = get_zavod(self.ichki_firma)
		warehouse = buyer.get("xomashyo_ombori") or buyer.get("asosiy_ombor")
		if not warehouse:
			frappe.throw(
				_("{0} firmasi uchun Zavod'da xomashyo ombori ko'rsatilmagan").format(self.ichki_firma)
			)
		pi = make_inter_company_purchase_invoice(si.name)
		pi.posting_date = self.posting_date
		pi.posting_time = self.posting_time
		pi.set_posting_time = 1
		pi.bill_no = si.name
		pi.bill_date = self.posting_date
		pi.due_date = self.posting_date
		pi.update_stock = 1
		pi.set_warehouse = warehouse
		pi.disable_rounded_total = 1
		pi.remarks = _("Firmalararo xarid: {0} ({1})").format(self.name, self.company)
		for row in pi.items:
			row.warehouse = (
				warehouse if frappe.get_cached_value("Item", row.item_code, "is_stock_item") else None
			)
		pi.flags.ignore_permissions = True
		pi.insert()
		pi.submit()
		return pi

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
		if not settings.sms_yoqilgan or not self.mobile_no or self.ichki_firma:
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


# ---------------------------------------------------------------- module level
def is_posted(payment_entry: str | None) -> bool:
	"""To'lov qatori haqiqatan o'tkazilganmi (Payment Entry tasdiqlangan, bekor qilinmagan)."""
	return bool(payment_entry) and frappe.db.get_value("Payment Entry", payment_entry, "docstatus") == 1


def get_inter_company_price_list(currency: str) -> str:
	"""ERPNext firmalararo hujjat uchun buying + selling belgilangan narx varaqasini talab qiladi."""
	if not frappe.db.exists("Price List", INTER_COMPANY_PRICE_LIST):
		pl = frappe.new_doc("Price List")
		pl.price_list_name = INTER_COMPANY_PRICE_LIST
		pl.currency = currency
		pl.buying = 1
		pl.selling = 1
		pl.enabled = 1
		pl.flags.ignore_permissions = True
		pl.insert()
	return INTER_COMPANY_PRICE_LIST


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
