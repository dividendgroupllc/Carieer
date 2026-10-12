# Firmalararo To'lov: bir firmamiz ikkinchisiga qarzini to'laydi (pul o'tkazmasi).
# Bitta hujjat ikkala kitobga yoziladi:
#   to'lovchi firmada  Payment Entry "Pay"     -> kassadan chiqim, oluvchi firmaga qarzimiz kamayadi
#   oluvchi firmada    Payment Entry "Receive" -> kassaga kirim, to'lovchi firmaning qarzi kamayadi
# Qaytarish (oluvchi ilgari ortiqcha to'lagan, to'lovchi avansini qaytaryapti): to'lovchida mijozga «Pay», oluvchida
# ta'minotchidan «Receive» - ikkala kitobda avans yopiladi (yangi soxta avans paydo bo'lmaydi).
# To'lov boshqa valyutada bo'lishi mumkin: 250 USD x kurs = so'm. Qarz so'mda kamayadi, kassadan esa
# kassa valyutasida chiqadi. To'lov eng eski to'lanmagan firmalararo hisob-fakturalarga taqsimlanadi.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money, now_datetime

from carieer.permissions import check_company, get_allowed_companies
from carieer.utils import (
	as_admin,
	check_kassa_balance,
	ensure_inter_company_parties,
	get_company_currency,
	get_kassa_info,
	get_rate,
	notify,
	reconcile,
)


class FirmalararoTolov(Document):
	def validate(self):
		if self.tolovchi_firma == self.oluvchi_firma:
			frappe.throw(_("To'lovchi va oluvchi firma bir xil bo'lishi mumkin emas"))
		allowed = get_allowed_companies()
		if allowed and self.tolovchi_firma not in allowed:
			# kassalar alohida: pul qaysi firma kassasidan chiqsa, to'lovni (Submit) o'sha firma qiladi.
			# Oluvchi firma faqat to'lov SO'ROVI yuboradi (saqlangan, «To'lov kutilmoqda») - to'lovchiga bildirishnoma.
			if self.docstatus == 1 or self.oluvchi_firma not in allowed:
				frappe.throw(
					_(
						"Bu to'lovni <b>{0}</b> tasdiqlaydi - pul uning kassasidan chiqadi. "
						"Siz to'lov so'rovini saqlab qo'yishingiz mumkin: {0} ga bildirishnoma boradi."
					).format(self.tolovchi_firma),
					frappe.PermissionError,
				)
		from carieer.utils import get_zavod

		self.oluvchi_kassa = self.oluvchi_kassa or get_zavod(self.oluvchi_firma).get("kassa")
		self.tolovchi_kassa = self.tolovchi_kassa or get_zavod(self.tolovchi_firma).get("kassa")
		if self.docstatus == 1 and not self.tolovchi_kassa:
			frappe.throw(_("Pul qaysi kassadan chiqishini tanlang (To'lovchi kassa)"))
		self.currency = get_company_currency(self.tolovchi_firma)
		if get_company_currency(self.oluvchi_firma) != self.currency:
			frappe.throw(_("Ikkala firmaning asosiy valyutasi bir xil bo'lishi kerak"))
		if flt(self.summa) <= 0:
			frappe.throw(_("Summa 0 dan katta bo'lishi kerak"))
		self.check_sotuv_qarzi()
		self.set_amounts()
		self.set_joriy_qarz()
		if self.docstatus == 0:
			self.nima_uchun = describe(self)
		# Click / Payme kabi: saqlangan = to'lov kutilmoqda, tasdiqlangan = to'langan
		self.status = {0: "To'lov kutilmoqda", 1: "To'langan", 2: "Bekor qilingan"}[self.docstatus]

	def after_insert(self):
		# to'lov so'rovi (oluvchi firma yoki «To'lov so'rash» tugmasi) - to'lovchi firmaga bildirishnoma
		if self.docstatus == 0 and (self.flags.tolov_sorovi or not check_company(self.tolovchi_firma, throw=False)):
			notify(
				self.tolovchi_firma,
				_("{0} sizdan {1} to'lov so'ramoqda{2}. Ochib «Submit» bosing - pul kassangizdan o'tkaziladi").format(
					self.oluvchi_firma,
					fmt_money(self.summa, 0, self.valyuta or self.currency),
					f" ({self.sotuv})" if self.sotuv else "",
				),
				self.doctype,
				self.name,
			)

	def check_sotuv_qarzi(self):
		"""Aniq sotuv uchun to'lov shu sotuv qarzidan ko'p bo'lmasin: ortiqchasi boshqa (eski) qarzlarga o'tib ketmasin."""
		if not self.sotuv or self.docstatus != 0:
			return
		qarz = flt(frappe.db.get_value("Sotuv", self.sotuv, "outstanding_amount"))
		kurs = flt(self.kurs) or 1
		if flt(self.summa) * kurs > qarz + 0.01:
			frappe.throw(
				_(
					"{0} bo'yicha qarz {1}. Bundan ko'p ({2}) to'lab bo'lmaydi: ortiqcha pul boshqa qarzlarga o'tib ketadi. "
					"Summani kamaytiring yoki «Qaysi sotuv uchun» ni bo'sh qoldiring."
				).format(self.sotuv, fmt_money(qarz, 0, self.currency), fmt_money(flt(self.summa) * kurs, 0, self.currency))
			)

	def set_joriy_qarz(self):
		"""Formada ko'rsatish uchun: to'lovchi firma oluvchidan qancha qarz (oluvchi kitobi bo'yicha)."""
		from carieer.carieer.report.firmalararo_qarzlar.firmalararo_qarzlar import balance

		if self.docstatus != 0:
			return
		qarz = balance(self.oluvchi_firma, self.tolovchi_firma, self.posting_date)
		if abs(qarz) < 0.5:
			self.joriy_qarz = _("Qarz yo'q")
		elif qarz > 0:
			self.joriy_qarz = _("{0} {1} dan {2} qarz").format(
				self.tolovchi_firma, self.oluvchi_firma, fmt_money(qarz, 0, self.currency)
			)
		else:
			self.joriy_qarz = _("{0} {1} dan {2} qarz").format(
				self.oluvchi_firma, self.tolovchi_firma, fmt_money(-qarz, 0, self.currency)
			)

	def set_amounts(self):
		"""To'lov valyutasi -> so'm (qarzdan ayriladi) -> har bir kassaning valyutasi.
		Masalan: 250 USD × 12 000 = 3 000 000 so'm; so'm kassadan 3 000 000 chiqadi, qarz 3 000 000 ga kamayadi."""
		self.valyuta = self.valyuta or self.currency
		if self.valyuta == self.currency:
			self.kurs = 1
		elif flt(self.kurs) <= 0 or flt(self.kurs) == 1:
			self.kurs = get_rate(self.valyuta, self.currency, self.posting_date)
		self.base_summa = flt(flt(self.summa) * flt(self.kurs), 2)
		for side in ("tolovchi", "oluvchi"):
			firma, kassa = self.get(f"{side}_firma"), self.get(f"{side}_kassa")
			info = get_kassa_info(kassa, firma)
			if not info["account"]:
				frappe.throw(
					_("{0} kassasi uchun {1} firmasida hisob ko'rsatilmagan (Mode of Payment)").format(
						kassa, firma
					)
				)
			self.set(f"{side}_valyuta", info["currency"])
			self.set(f"{side}_kassa_summa", self.kassa_amount(info["currency"]))
			if side == "tolovchi":
				# boshqa firmaning kassa qoldig'i ko'rsatilmaydi
				self.tolovchi_qoldiq = info["balance"] if check_company(firma, throw=False) else 0
		if self.docstatus == 1:
			# kassa nazorati (pul haqiqatan chiqayotganda): kassa minusga kirsa - ogohlantirish / blok (sozlamaga qarab)
			check_kassa_balance(
				self.tolovchi_kassa, self.tolovchi_firma, self.tolovchi_kassa_summa, self.posting_date
			)

	def kassa_amount(self, kassa_currency):
		"""Kassadan chiqadigan / kassaga kiradigan summa (kassa valyutasida)."""
		if kassa_currency == self.valyuta:
			return flt(self.summa, 2)
		if kassa_currency == self.currency:
			return flt(self.base_summa, 2)
		return flt(flt(self.base_summa) / get_rate(kassa_currency, self.currency, self.posting_date), 2)

	def on_submit(self):
		with as_admin():
			self.make_documents()
		self.db_set("nima_uchun", describe(self), update_modified=False)
		notify(
			self.oluvchi_firma,
			_(
				"{0} {1} to'ladi{2}. Pul tushganini tekshiring va ochib «Pulni qabul qildim» bosing: "
				"qaysi kassaga (naqd, USD, karta, bank) tushganini tanlang - shundan keyin qarz yopiladi"
			).format(
				self.tolovchi_firma,
				fmt_money(self.summa, 0, self.valyuta or self.currency),
				f" ({self.sotuv})" if self.sotuv else "",
			),
			self.doctype,
			self.name,
		)

	def make_documents(self):
		"""To'lovchi firma kitobiga darhol yoziladi (kassadan chiqim, oluvchiga qarz kamayadi). Oluvchi firma kitobiga -
		pulni haqiqatan olganini tasdiqlagandan keyin (tasdiqlash): qaysi kassaga tushgani (naqd / USD / karta / bank) o'sha paytda tanlanadi."""
		refund = self.is_refund()
		self.db_set("qaytarish", int(refund))
		if refund:
			# Qaytarish: oluvchi ilgari ortiqcha to'lagan, to'lovchi uning avansini qaytaryapti.
			# To'lovchida - mijozga (oluvchi) pul qaytarildi, oluvchida - ta'minotchidan (to'lovchi) pul qaytdi.
			customer, _supplier = ensure_inter_company_parties(self.tolovchi_firma, self.oluvchi_firma)
			pay = self.make_payment_entry("Pay", self.tolovchi_firma, self.tolovchi_kassa, "Customer", customer)
		else:
			# oluvchi = "sotuvchi" (unda to'lovchi firma ichki mijoz), to'lovchi = "xaridor" (unda oluvchi ichki yetkazib beruvchi)
			_customer, supplier = ensure_inter_company_parties(self.oluvchi_firma, self.tolovchi_firma)
			pay = self.make_payment_entry("Pay", self.tolovchi_firma, self.tolovchi_kassa, "Supplier", supplier)
		self.db_set({"tolovchi_payment_entry": pay, "status": "Tasdiq kutilmoqda", "tasdiq_holati": "Kutilmoqda"})

	def make_receive_entry(self) -> str:
		if self.qaytarish:
			_customer, supplier = ensure_inter_company_parties(self.tolovchi_firma, self.oluvchi_firma)
			return self.make_payment_entry("Receive", self.oluvchi_firma, self.oluvchi_kassa, "Supplier", supplier)
		customer, _supplier = ensure_inter_company_parties(self.oluvchi_firma, self.tolovchi_firma)
		return self.make_payment_entry("Receive", self.oluvchi_firma, self.oluvchi_kassa, "Customer", customer)

	def onload(self):
		self.set_onload(
			"can_confirm",
			self.docstatus == 1
			and self.tasdiq_holati == "Kutilmoqda"
			and check_company(self.oluvchi_firma, throw=False),
		)

	@frappe.whitelist()
	def tasdiqlash(self, kassa: str | None = None):
		"""Oluvchi firma: pul tushganini tasdiqlaydi va qaysi kassaga tushganini tanlaydi (naqd UZS / naqd USD / karta / bank).
		Shundan keyin oluvchi kitobiga kirim yoziladi va qarz (sotuv) yopiladi."""
		if self.docstatus != 1 or self.tasdiq_holati != "Kutilmoqda":
			frappe.throw(_("Bu to'lov tasdiq kutmayapti"))
		check_company(self.oluvchi_firma)
		kassa = kassa or self.oluvchi_kassa
		info = get_kassa_info(kassa, self.oluvchi_firma)
		if not info.account:
			frappe.throw(_("{0} kassasi uchun {1} firmasida hisob ko'rsatilmagan").format(kassa, self.oluvchi_firma))
		who = frappe.session.user
		self.db_set(
			{
				"oluvchi_kassa": kassa,
				"oluvchi_valyuta": info.currency,
				"oluvchi_kassa_summa": self.kassa_amount(info.currency),
			}
		)
		with as_admin():
			receive = self.make_receive_entry()
		self.db_set(
			{
				"oluvchi_payment_entry": receive,
				"status": "To'langan",
				"tasdiq_holati": "Tasdiqlandi",
				"tasdiq_qildi": who,
				"tasdiq_vaqti": now_datetime(),
			}
		)
		self.db_set("nima_uchun", describe(self), update_modified=False)
		notify(
			self.tolovchi_firma,
			_("{0} to'lovni tasdiqladi: {1} {2} ga ({3}) tushdi{4}").format(
				self.oluvchi_firma,
				fmt_money(self.kassa_amount(info.currency), 2, info.currency),
				kassa,
				who,
				f" - {self.sotuv}" if self.sotuv else "",
			),
			self.doctype,
			self.name,
		)
		return receive

	def is_refund(self) -> bool:
		"""To'lovchi kitobida: oluvchiga tovar uchun qarzi yo'q, lekin oluvchidan olgan ishlatilmagan avansi bor ->
		bu to'lov avansni qaytarish (masalan Beton Karer'ga ortiqcha to'lagan, Karer farqni qaytaryapti)."""
		from carieer.carieer.report.firmalararo_qarzlar.firmalararo_qarzlar import internal_parties

		qarz = avans = 0.0
		for party_type, party in internal_parties(self.oluvchi_firma):
			credit = -flt(
				frappe.db.sql(
					"""select sum(debit) - sum(credit) from `tabGL Entry` where company = %s and party_type = %s
					and party = %s and posting_date <= %s and is_cancelled = 0""",
					(self.tolovchi_firma, party_type, party, self.posting_date),
				)[0][0]
			)
			if party_type == "Supplier":
				qarz += credit  # ta'minotchi kredit qoldig'i - biz unga qarzdormiz
			else:
				avans += credit  # mijoz kredit qoldig'i - uning bizdagi avansi
		return qarz < 0.005 and avans > 0.005

	def on_cancel(self):
		with as_admin():
			self.cancel_documents()

	def cancel_documents(self):
		self.ignore_linked_doctypes = ("GL Entry", "Payment Ledger Entry", "Payment Entry")
		self.db_set("status", "Bekor qilingan")
		for name in (self.oluvchi_payment_entry, self.tolovchi_payment_entry):
			if name and frappe.db.get_value("Payment Entry", name, "docstatus") == 1:
				pe = frappe.get_doc("Payment Entry", name)
				pe.flags.ignore_permissions = True
				pe.cancel()

	def make_payment_entry(self, payment_type, company, kassa, party_type, party):
		from erpnext.accounts.party import get_party_account

		info = get_kassa_info(kassa, company)
		party_account = get_party_account(party_type, party, company)
		base = flt(self.base_summa)  # qarz (firma valyutasida)
		kassa_summa = self.kassa_amount(info["currency"])
		kassa_rate = base / kassa_summa if kassa_summa else 1  # 1 kassa valyutasi = ? so'm
		pay = payment_type == "Pay"
		pe = frappe.new_doc("Payment Entry")
		pe.update(
			{
				"payment_type": payment_type,
				"company": company,
				"posting_date": self.posting_date,
				"mode_of_payment": kassa,
				"party_type": party_type,
				"party": party,
				"paid_from": info["account"] if pay else party_account,
				"paid_to": party_account if pay else info["account"],
				"paid_from_account_currency": info["currency"] if pay else self.currency,
				"paid_to_account_currency": self.currency if pay else info["currency"],
				"paid_amount": kassa_summa if pay else base,
				"received_amount": base if pay else kassa_summa,
				"source_exchange_rate": kassa_rate if pay else 1,
				"target_exchange_rate": 1 if pay else kassa_rate,
				"reference_no": self.name,
				"reference_date": self.posting_date,
				"remarks": _("Firmalararo to'lov {0}: {1} → {2}, {3}. {4}").format(
					self.name,
					self.tolovchi_firma,
					self.oluvchi_firma,
					fmt_money(self.summa, 2, self.valyuta),
					" · ".join(filter(None, (self.sotuv and self.nima_uchun, self.izoh))),
				),
			}
		)
		refund = (party_type == "Customer") == pay  # mijozga to'lov / ta'minotchidan kirim - avans qaytarilmoqda
		if not refund:
			voucher_type = "Purchase Invoice" if pay else "Sales Invoice"
			# aniq sotuv uchun to'lov (so'rov / «qabul qilib to'lash») - avval o'sha sotuvning hujjati yopiladi
			first = self.sotuv and frappe.db.get_value(
				"Sotuv", self.sotuv, "purchase_invoice" if pay else "sales_invoice"
			)
			allocate(pe, voucher_type, party_type, party, company, base, first=first, only=bool(self.sotuv))
		pe.flags.ignore_permissions = True
		pe.setup_party_account_field()
		pe.set_missing_values()
		pe.set_amounts()
		pe.insert()
		pe.submit()
		if refund:
			# qaytarilgan pul avansga bog'lanadi (ERPNext Payment Reconciliation) - AR / AP da osilib qolmaydi
			reconcile(company, party_type, party, party_account, voucher=pe.name)
		return pe.name


def allocate(pe, voucher_type, party_type, party, company, amount, first=None, only=False):
	"""To'lovni to'lanmagan hisob-fakturalarga taqsimlaydi: avval `first` (to'lov aynan shu sotuv uchun), keyin
	eng eskilaridan (FIFO). Ortib qolgani avans bo'lib qoladi."""
	party_field = "supplier" if party_type == "Supplier" else "customer"
	left = flt(amount)
	invoices = frappe.get_all(
		voucher_type,
		{"company": company, party_field: party, "docstatus": 1, "outstanding_amount": [">", 0]},
		["name", "grand_total", "outstanding_amount", "due_date"],
		order_by="posting_date asc, creation asc",
	)
	invoices.sort(key=lambda inv: inv.name != first)  # barqaror: qolganlari FIFO tartibida
	if only and first:
		invoices = [inv for inv in invoices if inv.name == first]  # aniq sotuv uchun to'lov: boshqa qarzlarga tegmaydi
	for inv in invoices:
		if left <= 0:
			break
		alloc = min(left, flt(inv.outstanding_amount))
		pe.append(
			"references",
			{
				"reference_doctype": voucher_type,
				"reference_name": inv.name,
				"due_date": inv.due_date,
				"total_amount": inv.grand_total,
				"outstanding_amount": inv.outstanding_amount,
				"allocated_amount": alloc,
			},
		)
		left -= alloc


# ------------------------------------------------------------------ Ruxsat: ikkala firma ham ko'radi
# Firma maydonlarida User Permission o'chirilgan (ignore_user_permissions), cheklov shu yerda.
def get_permission_query_conditions(user=None):
	allowed = get_allowed_companies(user)
	if not allowed:
		return ""
	values = ", ".join(frappe.db.escape(c) for c in allowed)
	return f"(`tabFirmalararo Tolov`.tolovchi_firma in ({values}) or `tabFirmalararo Tolov`.oluvchi_firma in ({values}))"


def has_permission(doc, ptype=None, user=None):
	allowed = get_allowed_companies(user)
	if not allowed or not (doc.tolovchi_firma or doc.oluvchi_firma):
		return True
	return doc.tolovchi_firma in allowed or doc.oluvchi_firma in allowed


# ------------------------------------------------------------------ «Nima uchun»: qaysi tovar uchun to'lov
def fmt_qty(qty) -> str:
	qty = flt(qty)
	return f"{qty:,.0f}".replace(",", " ") if qty == int(qty) else f"{qty:,.2f}".replace(",", " ")


def sotuv_line(name: str, summa: float | None = None) -> str:
	"""«SOT-2026-00007 (09-10-2026): Beton 5 t × 1 200 000 = 6 000 000»."""
	s = frappe.db.get_value("Sotuv", name, ["posting_date", "amount", "currency"], as_dict=True)
	if not s:
		return name
	items = frappe.get_all(
		"Sotuv Tovar", {"parent": name}, ["item_name", "item_code", "qty", "uom", "rate"], order_by="idx"
	)
	tovar = ", ".join(
		f"{i.item_name or i.item_code} {fmt_qty(i.qty)} {i.uom or ''} × {fmt_qty(i.rate)}".replace("  ", " ")
		for i in items
	)
	line = f"{name} ({frappe.format(s.posting_date, 'Date')}): {tovar} = {fmt_qty(s.amount)}"
	if summa is not None and abs(flt(summa) - flt(s.amount)) >= 0.01:
		line += " · " + _("shundan to'landi {0}").format(fmt_qty(summa))
	return line


def fifo_preview(doc) -> str:
	"""Sotuv tanlanmagan to'lov: qaysi (eng eski) qarzlar yopilishini oldindan ko'rsatadi."""
	_customer, supplier = ensure_inter_company_parties(doc.oluvchi_firma, doc.tolovchi_firma)
	left = flt(doc.base_summa) or flt(doc.summa)
	lines = [_("Sotuv tanlanmagan - eng eski qarzlar yopiladi:")]
	for inv in frappe.get_all(
		"Purchase Invoice",
		{"company": doc.tolovchi_firma, "supplier": supplier, "docstatus": 1, "outstanding_amount": [">", 0]},
		["name", "posting_date", "outstanding_amount"],
		order_by="posting_date asc, creation asc",
	):
		if left <= 0:
			break
		part = min(left, flt(inv.outstanding_amount))
		lines.append(f"{inv.name} ({inv.posting_date}): {fmt_qty(part)} / qarz {fmt_qty(inv.outstanding_amount)}")
		left -= part
	if left > 0.01:
		lines.append(_("Avans (keyingi tovar uchun): {0}").format(fmt_qty(left)))
	return "\n".join(lines)


def describe(doc) -> str:
	"""To'lov nima uchun. Saqlanganda - bog'langan sotuv; tasdiqlangandan keyin - to'lov aslida yopgan hujjatlar
	(oluvchi kitobidagi Sales Invoice -> Sotuv), ortib qolgani avans; qaytarish bo'lsa - shu yoziladi."""
	if doc.docstatus == 0:
		if doc.sotuv:
			return sotuv_line(doc.sotuv)
		return fifo_preview(doc)
	if not doc.oluvchi_payment_entry:
		# pul oluvchi tasdig'ini kutmoqda: hali oluvchi kitobiga yozilmagan
		base = sotuv_line(doc.sotuv) if doc.sotuv else _("Qarzni to'lash")
		return base + "\n" + _("⏳ {0} pulni tasdiqlashi kutilmoqda").format(doc.oluvchi_firma)
	if frappe.db.get_value("Payment Entry", doc.tolovchi_payment_entry, "party_type") == "Customer":
		return _("Ortiqcha to'lovni qaytarish ({0} → {1})").format(doc.tolovchi_firma, doc.oluvchi_firma)
	lines, used = [], 0.0
	for ref in frappe.get_all(
		"Payment Entry Reference",
		{"parent": doc.oluvchi_payment_entry},
		["reference_doctype", "reference_name", "allocated_amount"],
		order_by="idx",
	):
		if ref.reference_doctype == "Sales Invoice":
			sotuv = frappe.db.get_value("Sotuv", {"sales_invoice": ref.reference_name, "docstatus": 1}, "name")
			lines.append(
				sotuv_line(sotuv, ref.allocated_amount)
				if sotuv
				else f"{ref.reference_name}: {fmt_qty(ref.allocated_amount)}"
			)
		elif ref.reference_doctype == "Payment Entry":
			# ortiqcha to'langan qism keyin qaytarilgan (qaytarish to'lovi bilan yopilgan)
			qaytarish = frappe.db.get_value("Payment Entry", ref.reference_name, "reference_no")
			lines.append(_("Qaytarib berildi ({0}): {1}").format(qaytarish or ref.reference_name, fmt_qty(ref.allocated_amount)))
		else:
			continue
		used += flt(ref.allocated_amount)
	avans = flt(doc.base_summa) - used
	if avans >= 0.01:
		lines.append(_("Avans (keyingi tovar uchun): {0}").format(fmt_qty(avans)))
	return "\n".join(lines)


def refresh_descriptions(company_a: str, company_b: str):
	"""Avans keyinroq tovarga o'tkazilganda (Sotuv qabul qilinganda) - ikki firma o'rtasidagi to'lovlar matni yangilanadi."""
	for name in frappe.get_all(
		"Firmalararo Tolov",
		{"docstatus": 1, "tolovchi_firma": ["in", [company_a, company_b]], "oluvchi_firma": ["in", [company_a, company_b]]},
		pluck="name",
	):
		doc = frappe.get_doc("Firmalararo Tolov", name)
		text = describe(doc)
		if text != doc.nima_uchun:
			doc.db_set("nima_uchun", text, update_modified=False)


@frappe.whitelist()
def kassa_preview(company: str, kassa: str, summa: float, valyuta: str | None = None, kirim: int = 0, posting_date=None):
	"""Forma uchun: kassada hozir qancha pul bor va shu to'lovdan keyin qancha qoladi (minus bo'lsa - qarzga kiradi)."""
	from frappe.utils import cint, nowdate

	info = get_kassa_info(kassa, company)
	if not info.account:
		return {}
	company_currency = get_company_currency(company)
	tmp = frappe.new_doc("Firmalararo Tolov")
	tmp.currency = company_currency
	tmp.valyuta = valyuta or company_currency
	tmp.posting_date = posting_date or nowdate()
	tmp.summa = flt(summa)
	tmp.kurs = 1 if tmp.valyuta == company_currency else get_rate(tmp.valyuta, company_currency, tmp.posting_date)
	tmp.base_summa = flt(tmp.summa * tmp.kurs, 2)
	amount = tmp.kassa_amount(info.currency)
	balance = flt(info.balance, 2)
	return {
		"balance": balance,
		"amount": amount,
		"after": flt(balance + amount if cint(kirim) else balance - amount, 2),
		"currency": info.currency,
	}
