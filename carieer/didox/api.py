# Brauzerdan chaqiriladigan Didox amallari.
# Didox'ga barcha so'rovlar shu yerdan (serverdan) ketadi: partner token sir saqlanadi va Didox faqat
# serverning IP'sini taniydi. Brauzer faqat E-IMZO bilan imzo qo'yadi (public/js/didox.js).

import base64
import json

import frappe
from frappe import _
from frappe.utils import getdate

from carieer.didox.client import DidoxClient, get_firma
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
	text = json.dumps(data["json"], ensure_ascii=False, separators=(",", ":"))
	return {"data": base64.b64encode(text.encode()).decode(), "inn": client.firma.inn}


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
	warning = (res or {}).get("warningDetails") or {}
	return {"warning": warning.get("message")}


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
