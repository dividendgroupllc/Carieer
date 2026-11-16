# Kiruvchi hisob-faktura (Didox) -> «Приход» (Purchase Invoice qoralamasi).
# Buxgalter qoralamani tekshirib o'zi tasdiqlaydi (Submit). Tovarlar MXIK bo'yicha topiladi;
# foydalanuvchi qo'lda tanlagan tovarga MXIK yozib qo'yiladi - keyingi fakturada o'zi topiladi.

import json

import frappe
from frappe import _
from frappe.utils import flt

from carieer.didox.client import get_firma
from carieer.didox.sync import refresh
from carieer.utils import get_zavod

PRIXOD_TURLARI = ("002",)  # oddiy hisob-faktura
PRIXOD_HOLATLARI = (1, 2, 3)  # imzo kutilmoqda yoki imzolangan (rad etilgan / o'chirilgan emas)


def faktura_qatorlari(js: dict) -> list:
	"""Didox ESF JSON (kichik harfli kalitlar) -> qatorlar."""
	out = []
	for p in (js.get("productlist") or {}).get("products") or []:
		summa, qqs = flt(p.get("deliverysum")), flt(p.get("vatsum"))
		out.append(
			frappe._dict(
				ordno=int(p.get("ordno") or len(out) + 1),
				nomi=p.get("name") or p.get("catalogname") or "",
				mxik=p.get("catalogcode") or "",
				mxik_nomi=p.get("catalogname") or "",
				qadoq_kod=str(p.get("packagecode") or ""),
				qadoq=p.get("packagename") or "",
				miqdor=flt(p.get("count")),
				summa=summa,
				qqs=qqs,
				jami=flt(p.get("deliverysumwithvat")) or summa + qqs,
			)
		)
	return out


def narxlar(qatorlar: list, qqs_tolovchi: bool) -> tuple[list, float]:
	"""Har qatorning birlik narxi va alohida yoziladigan QQS.
	QQS to'lovchi QQSni hisobga oladi (alohida soliq qatori), aks holda QQS tannarxga kiradi."""
	rates = []
	for q in qatorlar:
		if q.miqdor <= 0:
			frappe.throw(_("Fakturaning {0}-qatorida miqdor yo'q").format(q.ordno))
		rates.append(flt((q.summa if qqs_tolovchi else q.jami) / q.miqdor, 6))
	qqs = flt(sum(q.qqs for q in qatorlar), 2) if qqs_tolovchi else 0
	return rates, qqs


def get_hujjat(hujjat: str):
	h = frappe.get_doc("Didox Hujjat", hujjat)
	if h.yonalish != "Kiruvchi" or h.hujjat_kodi not in PRIXOD_TURLARI:
		frappe.throw(_("Приход faqat kiruvchi hisob-fakturadan yaratiladi"))
	if h.status_kod not in PRIXOD_HOLATLARI:
		frappe.throw(_("Bu holatdagi fakturadan Приход yaratilmaydi: {0}").format(h.holat))
	if h.purchase_invoice and frappe.db.get_value("Purchase Invoice", h.purchase_invoice, "docstatus") in (0, 1):
		frappe.throw(_("Bu fakturaga Приход allaqachon yaratilgan: {0}").format(h.purchase_invoice))
	return h


def fakturani_ol(h) -> dict:
	"""Ro'yxatdan sinxronlangan hujjatda JSON bo'lmaydi - Didox'dan to'liq olinadi."""
	refresh(h.name)
	h.reload()
	return json.loads(h.hujjat_json or "{}")


def mxik_boyicha(mxik: str) -> str | None:
	if not mxik:
		return None
	return frappe.db.get_value("Item", {"mxik_kod": mxik, "disabled": 0}, "name")


def malumot(hujjat: str) -> dict:
	"""Dialog uchun: yetkazib beruvchi, ombor va faktura qatorlari (MXIK bo'yicha topilgan tovar bilan)."""
	h = get_hujjat(hujjat)
	qatorlar = faktura_qatorlari(fakturani_ol(h))
	if not qatorlar:
		frappe.throw(_("Fakturada tovar qatorlari yo'q"))
	for q in qatorlar:
		q.item_code = mxik_boyicha(q.mxik)
	return {
		"supplier": h.supplier,
		"kontragent": h.kontragent_nomi,
		"inn": h.kontragent_inn,
		"ombor": get_zavod(h.company).asosiy_ombor,
		"qqs_tolovchi": get_firma(h.company).qqs_tolovchi,
		"qatorlar": qatorlar,
	}


def supplier_topish_yoki_yaratish(h) -> str:
	if h.supplier:
		return h.supplier
	inn = (h.kontragent_inn or "").strip()
	if not inn:
		frappe.throw(_("Fakturada yetkazib beruvchi INN'i yo'q"))
	nomi = (h.kontragent_nomi or inn).strip()
	# shu nomli, INN'i kiritilmagan yetkazib beruvchi bo'lsa - o'shanga INN yoziladi
	mavjud = frappe.db.get_value("Supplier", {"supplier_name": nomi}, ["name", "tax_id"], as_dict=True)
	if mavjud and not mavjud.tax_id:
		frappe.db.set_value("Supplier", mavjud.name, "tax_id", inn)
		return mavjud.name
	s = frappe.new_doc("Supplier")
	s.supplier_name = nomi if not mavjud else f"{nomi} ({inn})"
	s.tax_id = inn
	s.supplier_type = "Individual" if len(inn) == 14 else "Company"
	s.supplier_group = frappe.db.get_single_value("Buying Settings", "supplier_group") or "All Supplier Groups"
	s.insert()
	return s.name


def mxik_yozib_qoy(item_code: str, q):
	"""Qo'lda tanlangan tovarga MXIK va qadoq yoziladi (bo'sh bo'lsa) - keyingi safar avtomatik topiladi."""
	item = frappe.db.get_value("Item", item_code, ["mxik_kod", "upakovka_kod"], as_dict=True)
	updates = {}
	if not item.mxik_kod and q.mxik:
		updates.update(mxik_kod=q.mxik, mxik_nomi=(q.mxik_nomi or "")[:140])
	if not item.upakovka_kod and q.qadoq_kod:
		updates.update(upakovka_kod=q.qadoq_kod, upakovka_nomi=(q.qadoq or "")[:140])
	if updates:
		frappe.db.set_value("Item", item_code, updates)


def qqs_hisobi(company: str) -> str:
	account = frappe.db.get_value("Account", {"company": company, "account_type": "Tax", "is_group": 0}, "name")
	if not account:
		frappe.throw(_("{0} firmasida QQS hisobi (Account Type = Tax) topilmadi").format(company))
	return account


def boglanishni_uz(doc, method=None):
	"""Purchase Invoice bekor qilinsa / o'chirilsa - fakturadan qayta Приход yaratish mumkin bo'lsin."""
	for name in frappe.get_all("Didox Hujjat", filters={"purchase_invoice": doc.name}, pluck="name"):
		frappe.db.set_value("Didox Hujjat", name, "purchase_invoice", None)


def yaratish(hujjat: str, tanlov: list, supplier: str | None = None, ombor: str | None = None) -> str:
	"""tanlov: [{"ordno": 1, "item_code": "..."}] - har bir faktura qatoriga ERPNext tovari."""
	h = get_hujjat(hujjat)
	qatorlar = faktura_qatorlari(fakturani_ol(h))
	tanlangan = {int(t["ordno"]): t.get("item_code") for t in tanlov}
	yoq = [str(q.ordno) for q in qatorlar if not tanlangan.get(q.ordno)]
	if yoq:
		frappe.throw(_("Quyidagi qatorlarga tovar tanlanmagan: {0}").format(", ".join(yoq)))

	qqs_tolovchi = bool(get_firma(h.company).qqs_tolovchi)
	rates, qqs = narxlar(qatorlar, qqs_tolovchi)
	if supplier:
		h.supplier = supplier
	ombor = ombor or get_zavod(h.company).asosiy_ombor

	pi = frappe.new_doc("Purchase Invoice")
	pi.company = h.company
	pi.supplier = supplier_topish_yoki_yaratish(h)
	pi.currency = frappe.get_cached_value("Company", h.company, "default_currency")
	pi.bill_no = h.raqam
	pi.bill_date = h.sana
	if h.sana:
		pi.set_posting_time = 1
		pi.posting_date = h.sana
	for q, rate in zip(qatorlar, rates, strict=True):
		item_code = tanlangan[q.ordno]
		mxik_yozib_qoy(item_code, q)
		is_stock = frappe.get_cached_value("Item", item_code, "is_stock_item")
		if is_stock:
			pi.update_stock = 1
		pi.append(
			"items",
			{
				"item_code": item_code,
				"description": q.nomi,
				"qty": q.miqdor,
				"rate": rate,
				"warehouse": ombor if is_stock else None,
			},
		)
	# ombor faqat tovar qatorlarida (set_warehouse xizmat qatorlariga ham yozib yuboradi)
	if pi.update_stock and not ombor:
		frappe.throw(_("Ombor tanlang"))
	if qqs:
		pi.append(
			"taxes",
			{
				"charge_type": "Actual",
				"category": "Total",
				"add_deduct_tax": "Add",
				"account_head": qqs_hisobi(h.company),
				"description": _("QQS (Didox faktura {0})").format(h.raqam),
				"tax_amount": qqs,
			},
		)
	pi.remarks = _("Didox kiruvchi faktura {0} dan {1}").format(h.raqam, h.sana)
	pi.insert()
	frappe.db.set_value("Didox Hujjat", h.name, {"purchase_invoice": pi.name, "supplier": pi.supplier})
	return pi.name
