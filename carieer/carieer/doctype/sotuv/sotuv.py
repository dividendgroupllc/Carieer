# Sotuv - sotuv posti. Post ikkala zavodga ishlaydi: «Тип» = Karer yoki Beton -> firma o'zi qo'yiladi.
#
#   Saqlash (Save)     -> summalar, ombor, kurs, qarz hisoblanadi (hammasi serverda, JS yo'q)
#   Tasdiqlash (Submit) -> Sales Invoice (tovar ombordan chiqadi, mijozga qarz) + har bir to'lov qatori uchun
#                         Payment Entry (kassaga kirim) + SMS
#   Keyinroq to'lov    -> «Оплаты» jadvaliga qator qo'shib «Update» bosiladi -> yangi Payment Entry
#
# Mijoz o'zimizning ikkinchi firmamiz bo'lsa (ichki mijoz) bu - firmalararo sotuv / perexod (Click / Payme kabi):
#   1. Sotuvchi tasdiqlaydi (Submit)  -> holat «Tasdiq kutilmoqda», xaridor firmaga bildirishnoma (qo'ng'iroqcha).
#      Ombor va qarz hali o'zgarmaydi.
#   2. Xaridor «Qabul qilish" bosadi  -> sotuvchida Sales Invoice (ombordan chiqim, xaridorning qarzi), xaridorda
#      Purchase Invoice (omborga kirim, qarzi). Xohlasa shu zahoti to'laydi (Firmalararo To'lov), aks holda qarzga.
#      Xaridor «Rad etish» bossa - sotuv bekor qilinadi, sotuvchiga xabar.
#   3. Keyin pul «Firmalararo To'lov» orqali (ikkala kitobga). Sotuvchi «To'lov so'rash» bilan so'rov yuboradi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money, formatdate, now_datetime, nowdate

from carieer.permissions import check_company, get_allowed_companies
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
	notify,
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
	def onload(self):
		"""Forma tugmalari (sotuv.js): xaridor firma - «Qabul qilish / Rad etish», sotuvchi - «To'lov so'rash»."""
		if not self.ichki_firma or self.docstatus != 1:
			return
		self.set_onload(
			"can_accept", self.qabul_holati == "Kutilmoqda" and check_company(self.ichki_firma, throw=False)
		)
		self.set_onload(
			"can_request_payment",
			self.qabul_holati == "Qabul qilindi"
			and flt(self.outstanding_amount) > 0.01
			and check_company(self.company, throw=False),
		)

	def validate(self):
		if self.docstatus == 0:
			self.company = company_for_tip(self.tip)
			# «Тип» ro'yxatida ikkala zavod ko'rinadi (xaridor firma ham sotuvni ko'radi) - sotish faqat o'z firmasidan
			check_company(self.company)
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
			# firmalararo: xaridor firma qabul qilguncha ombor va qarz o'zgarmaydi
			self.db_set({"qabul_holati": "Kutilmoqda", "status": "Tasdiq kutilmoqda"})
			notify(
				self.ichki_firma,
				_("{0} sizga tovar yubordi: {1} - {2}. Qabul qiling yoki rad eting").format(
					self.company, self.items_text(), fmt_money(self.amount, 0, self.currency)
				),
				"Sotuv",
				self.name,
			)
			return
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
		if self.qabul_holati == "Rad etildi":
			self.db_set("status", "Rad etildi")
			return
		if self.qabul_holati == "Kutilmoqda" and self.ichki_firma:
			# sotuvchi o'zi bekor qildi - xaridor firma kutib qolmasin
			self.db_set("qabul_holati", "")
			notify(self.ichki_firma, _("{0} yuborgan tovarni bekor qildi: {1}").format(self.company, self.name), "Sotuv", self.name)
		self.db_set("status", "Cancelled")

	# ------------------------------------------------------------ firmalararo: xaridor tasdig'i
	def items_text(self) -> str:
		return ", ".join(f"{r.item_name or r.item_code} {flt(r.qty):g} {r.uom or ''}".strip() for r in self.items)

	def check_buyer(self):
		if not self.ichki_firma or self.docstatus != 1 or self.qabul_holati != "Kutilmoqda":
			frappe.throw(_("Bu sotuv tasdiq kutmayapti (holati: {0})").format(self.qabul_holati or self.status))
		# faqat xaridor firma xodimi (yoki ikkala firmaga ruxsati bor egasi)
		check_company(self.ichki_firma)

	def accept(self, kassa: str | None = None, summa: float = 0):
		"""Xaridor firma qabul qildi: tovar omboridan omboriga o'tadi, qarz ikkala kitobga yoziladi.
		kassa + summa berilsa - shu zahoti to'laydi (Firmalararo To'lov), aks holda qarzga."""
		self.check_buyer()
		self.check_stock()  # yuborilgandan keyin sotuvchi omborida tovar kamaygan bo'lishi mumkin
		with as_admin():
			ensure_inter_company_parties(self.company, self.ichki_firma)
			si = self.make_sales_invoice()
			pi = self.make_purchase_invoice(si)
			# xaridor oldindan pul bergan bo'lsa (avans) - ikkala kitobda tovarga o'tadi
			apply_advances(self.company, "Customer", self.customer, "Sales Invoice", si.name)
			apply_advances(self.ichki_firma, "Supplier", pi.supplier, "Purchase Invoice", pi.name)
			# avans shu tovarga o'tgan bo'lsa - to'lovlarning «Nima uchun» matni yangilanadi
			from carieer.carieer.doctype.firmalararo_tolov.firmalararo_tolov import refresh_descriptions

			refresh_descriptions(self.company, self.ichki_firma)
		self.db_set(
			{
				"sales_invoice": si.name,
				"purchase_invoice": pi.name,
				"qabul_holati": "Qabul qilindi",
				"qabul_qildi": frappe.session.user,
				"qabul_vaqti": now_datetime(),
			}
		)
		self.update_payment_status()
		ft = None
		summa = min(flt(summa), flt(frappe.db.get_value("Sotuv", self.name, "outstanding_amount")))
		if kassa and summa > 0:
			ft = make_firmalararo_tolov(self, summa, tolovchi_kassa=kassa, submit=True)
			self.update_payment_status()
		self.reload()
		if self.outstanding_amount > 0.01:
			# qarzga olindi: to'lov so'rovi o'zi yaratiladi («Firmalararo to'lov» ro'yxatida «To'lov kutilmoqda»)
			make_firmalararo_tolov(self, self.outstanding_amount, submit=False)
		if self.outstanding_amount <= 0.01:
			holat = _("to'liq to'landi")
		elif ft:
			holat = _("{0} to'landi, qarz {1}").format(
				fmt_money(summa, 0, self.currency), fmt_money(self.outstanding_amount, 0, self.currency)
			)
		else:
			holat = _("qarzga olindi, qarz {0}").format(fmt_money(self.outstanding_amount, 0, self.currency))
		notify(self.company, _("{0} tovarni qabul qildi: {1} - {2}").format(self.ichki_firma, self.name, holat), "Sotuv", self.name)
		return ft

	def reject(self, sabab: str):
		"""Xaridor firma rad etdi: sotuv bekor qilinadi (ombor va qarz o'zgarmagan edi)."""
		self.check_buyer()
		if not (sabab or "").strip():
			frappe.throw(_("Rad etish sababini yozing"))
		self.db_set(
			{
				"qabul_holati": "Rad etildi",
				"rad_sababi": sabab,
				"qabul_qildi": frappe.session.user,
				"qabul_vaqti": now_datetime(),
			}
		)
		self.reload()
		self.flags.ignore_permissions = True
		self.cancel()
		notify(self.company, _("{0} tovarni rad etdi: {1}. Sabab: {2}").format(self.ichki_firma, self.name, sabab), "Sotuv", self.name)

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
		si.flags.carieer_sotuv = True  # utils.validate_inter_company_document: ichki mijozga faqat Sotuv orqali
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
		if self.ichki_firma:
			self.sync_payment_request(outstanding)

	def sync_payment_request(self, outstanding: float):
		"""Kutilayotgan to'lov so'rovi (Firmalararo To'lov, saqlangan) qarzga mos bo'lsin: qisman to'lansa summa
		kamayadi, to'liq to'lansa so'rov olib tashlanadi."""
		for name in frappe.get_all("Firmalararo Tolov", {"sotuv": self.name, "docstatus": 0}, pluck="name"):
			with as_admin():
				if outstanding <= 0.01:
					frappe.delete_doc("Firmalararo Tolov", name, ignore_permissions=True, force=True)
					continue
				ft = frappe.get_doc("Firmalararo Tolov", name)
				if abs(flt(ft.summa) - outstanding) >= 0.01:
					ft.summa = outstanding
					ft.flags.ignore_permissions = True
					ft.save()

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


# ---------------------------------------------------------------- firmalararo (forma tugmalari, sotuv.js)
@frappe.whitelist()
def qabul_qilish(name: str, kassa: str | None = None, summa: float | None = None):
	"""Xaridor firma: «Qabul qilish». kassa + summa - shu zahoti to'lash, bo'sh - qarzga."""
	doc = frappe.get_doc("Sotuv", name)
	ft = doc.accept(kassa=kassa, summa=flt(summa))
	return {"status": frappe.db.get_value("Sotuv", name, "status"), "firmalararo_tolov": ft}


@frappe.whitelist()
def rad_etish(name: str, sabab: str):
	frappe.get_doc("Sotuv", name).reject(sabab)
	return frappe.db.get_value("Sotuv", name, "status")


@frappe.whitelist()
def tolov_sorash(name: str):
	"""Sotuvchi firma: qabul qilingan, lekin to'lanmagan sotuv uchun xaridorga to'lov so'rovi (Click / Payme kabi):
	«To'lov kutilmoqda» holatidagi Firmalararo To'lov yaratiladi, xaridorga bildirishnoma. Xaridor uni ochib to'laydi."""
	doc = frappe.get_doc("Sotuv", name)
	check_company(doc.company)
	if not doc.ichki_firma or doc.qabul_holati != "Qabul qilindi" or flt(doc.outstanding_amount) <= 0.01:
		frappe.throw(_("Bu sotuv bo'yicha to'lanmagan qarz yo'q"))
	pending = frappe.db.get_value("Firmalararo Tolov", {"docstatus": 0, "sotuv": doc.name}, "name")
	if pending:
		return pending
	return make_firmalararo_tolov(doc, flt(doc.outstanding_amount), submit=False)


def make_firmalararo_tolov(doc, summa: float, tolovchi_kassa: str | None = None, submit: bool = False) -> str:
	"""Xaridor (ichki_firma) -> sotuvchi (company) to'lov. submit=False - to'lov so'rovi (kutilmoqda)."""
	ft = frappe.new_doc("Firmalararo Tolov")
	ft.update(
		{
			"posting_date": nowdate(),
			"tolovchi_firma": doc.ichki_firma,
			"tolovchi_kassa": tolovchi_kassa or get_zavod(doc.ichki_firma).get("kassa"),
			"oluvchi_firma": doc.company,
			"oluvchi_kassa": get_zavod(doc.company).get("kassa"),
			"summa": flt(summa, 2),
			"valyuta": get_company_currency(doc.company),
			"izoh": _("{0}: {1}").format(doc.name, doc.items_text()),
		}
	)
	ft.sotuv = doc.name
	ft.flags.tolov_sorovi = not submit
	ft.insert()
	if submit:
		ft.submit()
	return ft.name


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


# ---------------------------------------------------------------- ruxsat (hooks.py)
# «Firma» va «Тип» maydonlarida User Permission o'chirilgan: xaridor firma unga yuborilgan sotuvni ko'radi.
def get_permission_query_conditions(user=None):
	allowed = get_allowed_companies(user)
	if not allowed:
		return ""
	values = ", ".join(frappe.db.escape(c) for c in allowed)
	return f"(`tabSotuv`.company in ({values}) or `tabSotuv`.ichki_firma in ({values}))"


def has_permission(doc, ptype=None, user=None):
	allowed = get_allowed_companies(user)
	if not allowed or not doc.company or doc.company in allowed:
		return True
	# xaridor firma - faqat ko'radi (qabul qilish / rad etish - alohida metod, o'z tekshiruvi bilan)
	return doc.ichki_firma in allowed and (ptype or "read") in ("read", "print", "email", "report", "export")
