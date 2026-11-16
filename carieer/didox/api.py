# Brauzerdan chaqiriladigan Didox amallari.
# Didox'ga barcha so'rovlar shu yerdan (serverdan) ketadi: partner token sir saqlanadi va Didox faqat
# serverning IP'sini taniydi. Brauzer faqat E-IMZO bilan imzo qo'yadi (public/js/didox.js).

import base64

import frappe
from frappe import _
from frappe.utils import getdate

from carieer.didox.client import DidoxClient, get_firma
from carieer.didox.common import bekor_qilinadimi, imzo_uchun, kiruvchi_imzolanadimi
from carieer.didox.factura import ESF, build_factura
from carieer.didox.sync import refresh, upsert_from_detail


def check(doctype: str, ptype: str, name: str | None = None):
	frappe.has_permission(doctype, ptype, name, throw=True)


@frappe.whitelist()
def sotuvdan_faktura(sotuv: str) -> str:
	"""Sotuv bo'yicha Didox'da hisob-faktura qoralamasini yaratadi va Didox Hujjat qaytaradi."""
	check("Sotuv", "read", sotuv)
	check("Didox Hujjat", "create")
	doc = frappe.get_doc("Sotuv", sotuv)
	if doc.docstatus != 1:
		frappe.throw(_("Avval Sotuv'ni tasdiqlang (Submit)"))
	if doc.didox_hujjat and frappe.db.get_value("Didox Hujjat", doc.didox_hujjat, "status_kod") not in (
		5,
		55,
	):
		frappe.throw(_("Bu sotuvga faktura allaqachon yaratilgan: {0}").format(doc.didox_hujjat))

	customer = frappe.get_cached_value(
		"Customer", doc.customer, ["tax_id", "shartnoma_raqami", "shartnoma_sanasi"], as_dict=True
	)
	inn = (customer.tax_id or "").strip()
	if len(inn) not in (9, 14) or not inn.isdigit():
		frappe.throw(
			_("Mijoz {0} kartochkasida INN (9 raqam) yoki JShShIR (14 raqam) yo'q").format(doc.customer)
		)
	if not (customer.shartnoma_raqami and customer.shartnoma_sanasi):
		frappe.throw(_("Mijoz {0} kartochkasida shartnoma raqami va sanasi yo'q").format(doc.customer))

	client = DidoxClient(doc.company)
	sana = str(getdate(doc.posting_date))
	factura = build_factura(
		doc,
		client.firma,
		seller_info=client.org_info(client.firma.inn, sana, seller=True),
		buyer_inn=inn,
		buyer_info=client.org_info(inn, sana),
		contract={"raqam": customer.shartnoma_raqami, "sana": customer.shartnoma_sanasi},
	)
	res = client.create(ESF, factura)
	didox_id = res["_id"].upper()

	hujjat = upsert_from_detail(doc.company, didox_id, client.document(didox_id, owner=1), owner=1)
	hujjat.db_set("sotuv", doc.name)
	doc.db_set("didox_hujjat", hujjat.name)
	return hujjat.name


@frappe.whitelist()
def imzo_malumoti(hujjat: str) -> dict:
	"""Chiquvchi qoralamani imzolash uchun: Didox'dagi hujjat JSON'i base64 ko'rinishida."""
	check("Didox Hujjat", "write", hujjat)
	h = frappe.get_doc("Didox Hujjat", hujjat)
	if h.yonalish != "Chiquvchi" or h.status_kod != 0:
		frappe.throw(_("Faqat chiquvchi qoralama imzolanadi"))
	client = DidoxClient(h.company)
	data = client.document(h.didox_id, owner=1)
	return {"data": imzo_uchun(data["json"]), "inn": client.firma.inn}


@frappe.whitelist()
def kirish_malumoti(company: str) -> dict:
	"""ERI bilan kirish uchun: firma INN'i base64 ko'rinishida imzolanadi."""
	check("Didox Hujjat", "read")
	inn = get_firma(company).inn
	return {"data": base64.b64encode(inn.encode()).decode(), "inn": inn}


@frappe.whitelist()
def timestamp(company: str, pkcs7: str, signature_hex: str) -> str:
	"""E-IMZO imzosiga Didox orqali vaqt belgisi (timestamp) qo'shiladi."""
	check("Didox Hujjat", "read")
	return DidoxClient(company).timestamp(pkcs7, signature_hex)


@frappe.whitelist()
def eri_login(company: str, signature: str):
	check("Didox Hujjat", "read")
	DidoxClient(company).login_signature(signature)


@frappe.whitelist()
def imzolash(hujjat: str, signature: str) -> dict:
	check("Didox Hujjat", "write", hujjat)
	h = frappe.get_doc("Didox Hujjat", hujjat)
	res = DidoxClient(h.company).sign(h.didox_id, signature)
	refresh(h.name)
	return ogohlantirish(res)


def ogohlantirish(res) -> dict:
	"""Soliq imzolashda ogohlantirish qaytargan bo'lsa (warningDetails), foydalanuvchiga ko'rsatiladi."""
	warning = (res or {}).get("warningDetails") or {}
	return {"warning": warning.get("message")}


# ---------------------------------------------------------------- kiruvchi hujjat: qabul / rad etish
def kiruvchi(hujjat: str):
	check("Didox Hujjat", "write", hujjat)
	h = frappe.get_doc("Didox Hujjat", hujjat)
	if not kiruvchi_imzolanadimi(h):
		frappe.throw(_("Bu hujjatni qabul qilish yoki rad etish mumkin emas (holati: {0})").format(h.holat))
	return h


@frappe.whitelist()
def qabul_malumoti(hujjat: str) -> dict:
	"""Kiruvchi hujjatni qabul qilish uchun imzolanadigan matn (Didox bergan base64)."""
	h = kiruvchi(hujjat)
	client = DidoxClient(h.company)
	return {"data": client.document_base64(h.didox_id), "inn": client.firma.inn}


@frappe.whitelist()
def qabul_qilish(hujjat: str, signature: str) -> dict:
	"""Bizning imzo (timestamp bilan) sotuvchi imzosiga qo'shilib, Didox'ga yuboriladi."""
	h = kiruvchi(hujjat)
	client = DidoxClient(h.company)
	sotuvchi_imzosi = client.document(h.didox_id, owner=0).get("toSign")
	if not sotuvchi_imzosi:
		frappe.throw(_("Didox hujjatda sotuvchi imzosini bermadi, «Yangilash» qilib qayta urinib ko'ring"))
	res = client.sign(h.didox_id, client.join_signatures(sotuvchi_imzosi, signature))
	refresh(h.name)
	return ogohlantirish(res)


def rad_izohi(izoh: str | None) -> str:
	izoh = (izoh or "").strip()
	if not izoh:
		frappe.throw(_("Rad etish sababini yozing: u kontragentga ko'rinadi"))
	return izoh


@frappe.whitelist()
def rad_malumoti(hujjat: str, izoh: str) -> dict:
	h = kiruvchi(hujjat)
	client = DidoxClient(h.company)
	data = client.tosign(h.didox_id, "reject", rad_izohi(izoh))
	return {"data": imzo_uchun(data), "inn": client.firma.inn}


@frappe.whitelist()
def rad_etish(hujjat: str, izoh: str, signature: str):
	# izoh imzolangan ma'lumotdagi bilan bir xil bo'lishi shart (Didox talabi)
	h = kiruvchi(hujjat)
	DidoxClient(h.company).reject(h.didox_id, signature, rad_izohi(izoh))
	refresh(h.name)


# ---------------------------------------------------------------- kiruvchi faktura -> Приход
@frappe.whitelist()
def prixod_malumoti(hujjat: str) -> dict:
	from carieer.didox import prixod

	check("Didox Hujjat", "read", hujjat)
	check("Purchase Invoice", "create")
	return prixod.malumot(hujjat)


@frappe.whitelist()
def prixod_yaratish(hujjat: str, tanlov: str | list, supplier: str | None = None, ombor: str | None = None) -> str:
	from carieer.didox import prixod

	check("Didox Hujjat", "write", hujjat)
	check("Purchase Invoice", "create")
	return prixod.yaratish(hujjat, frappe.parse_json(tanlov), supplier or None, ombor or None)


# ---------------------------------------------------------------- TTN, ishonchnoma, shartnoma
@frappe.whitelist()
def ttn_malumoti(sotuv: str) -> dict:
	from carieer.didox import hujjatlar

	check("Sotuv", "read", sotuv)
	check("Didox Hujjat", "create")
	return hujjatlar.ttn_malumoti(sotuv)


@frappe.whitelist()
def ttn_yaratish(sotuv: str, qiymatlar: str | dict) -> str:
	from carieer.didox import hujjatlar

	check("Sotuv", "read", sotuv)
	check("Didox Hujjat", "create")
	return hujjatlar.ttn_yaratish(sotuv, frappe.parse_json(qiymatlar))


@frappe.whitelist()
def firma_standartlari(company: str) -> dict:
	"""Ishonchnoma dialogi uchun: Didox Sozlamalari'da saqlangan bosh buxgalter."""
	check("Didox Hujjat", "create")
	firma = get_firma(company)
	return {"buxgalter_pinfl": firma.buxgalter_pinfl, "buxgalter_fio": firma.buxgalter_fio}


@frappe.whitelist()
def ishonchnoma_yaratish(company: str, qiymatlar: str | dict) -> str:
	from carieer.didox import hujjatlar

	check("Didox Hujjat", "create")
	return hujjatlar.ishonchnoma_yaratish(company, frappe.parse_json(qiymatlar))


@frappe.whitelist()
def shartnoma_yaratish(company: str, qiymatlar: str | dict) -> str:
	from carieer.didox import hujjatlar

	check("Didox Hujjat", "create")
	check("Customer", "read", frappe.parse_json(qiymatlar).get("customer"))
	return hujjatlar.shartnoma_yaratish(company, frappe.parse_json(qiymatlar))


# ---------------------------------------------------------------- yuborilgan hujjatni bekor qilish
def bekor_qilinadigan(hujjat: str):
	check("Didox Hujjat", "write", hujjat)
	h = frappe.get_doc("Didox Hujjat", hujjat)
	if not bekor_qilinadimi(h):
		frappe.throw(
			_("Faqat kontragent hali imzolamagan yuborilgan hujjat bekor qilinadi (holati: {0})").format(h.holat)
		)
	return h


@frappe.whitelist()
def bekor_malumoti(hujjat: str) -> dict:
	h = bekor_qilinadigan(hujjat)
	client = DidoxClient(h.company)
	return {"data": imzo_uchun(client.tosign(h.didox_id, "cancel")), "inn": client.firma.inn}


@frappe.whitelist()
def bekor_qilish(hujjat: str, signature: str):
	h = bekor_qilinadigan(hujjat)
	DidoxClient(h.company).cancel(h.didox_id, signature)
	refresh(h.name)


@frappe.whitelist()
def yangilash(hujjat: str):
	check("Didox Hujjat", "read", hujjat)
	refresh(hujjat)


@frappe.whitelist()
def qoralamani_ochirish(hujjat: str):
	check("Didox Hujjat", "write", hujjat)
	h = frappe.get_doc("Didox Hujjat", hujjat)
	if h.status_kod != 0:
		frappe.throw(_("Faqat qoralamani o'chirish mumkin"))
	DidoxClient(h.company).delete_draft(h.didox_id)
	refresh(h.name)


@frappe.whitelist()
def pdf_yuklash(hujjat: str) -> str:
	"""Didox'dagi bosma shaklni (PDF) hujjatga biriktiradi."""
	check("Didox Hujjat", "read", hujjat)
	h = frappe.get_doc("Didox Hujjat", hujjat)
	content = DidoxClient(h.company).pdf(h.didox_id)
	f = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"didox-{h.raqam or h.name}.pdf",
			"attached_to_doctype": "Didox Hujjat",
			"attached_to_name": h.name,
			"attached_to_field": "pdf",
			"is_private": 1,
			"content": content,
		}
	).insert(ignore_permissions=True)
	h.db_set("pdf", f.file_url)
	return f.file_url


@frappe.whitelist()
def sinxronlash(company: str | None = None):
	check("Didox Hujjat", "read")
	frappe.enqueue(
		"carieer.didox.sync.sync_all",
		company=company,
		queue="long",
		job_id=f"didox_sync:{company or 'all'}",
		deduplicate=True,
	)


@frappe.whitelist()
def eimzo_kalitlari() -> list[str]:
	"""E-IMZO «apikey» uchun [domen, kalit, domen, kalit ...] (Didox Sozlamalari'dan)."""
	check("Didox Hujjat", "read")
	text = frappe.db.get_single_value("Didox Sozlamalari", "eimzo_api_kalitlari") or ""
	out = []
	for line in text.splitlines():
		domen, _sep, kalit = line.partition("|")
		if domen.strip() and kalit.strip():
			out += [domen.strip(), kalit.strip()]
	return out


@frappe.whitelist()
def rekvizitlar(inn: str) -> dict:
	"""Mijoz formasi: INN / JShShIR bo'yicha soliq bazasidagi rekvizitlar (Didox orqali)."""
	check("Customer", "write")
	inn = (inn or "").replace(" ", "")
	if not inn.isdigit() or len(inn) not in (9, 14):
		frappe.throw(_("Avval to'g'ri INN (9 raqam) yoki JShShIR (14 raqam) kiriting"))
	firmalar = frappe.get_cached_doc("Didox Sozlamalari").firmalar
	if not firmalar:
		frappe.throw(_("Didox hali ulanmagan: Didox Sozlamalari'da firma va token kiritilmagan"))
	info = DidoxClient(firmalar[0].company).org_info(inn)
	return {
		"nomi": info.get("shortName") or info.get("name"),
		"bank_hisob": info.get("account"),
		"mfo": info.get("mfo"),
		"qqs_kodi": info.get("VATRegCode"),
		"direktor": info.get("director"),
		"yuridik_manzil": info.get("address"),
	}
