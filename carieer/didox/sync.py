# Didox -> «Didox Hujjat» jurnali: har bir firmaning kiruvchi va chiquvchi hujjatlari tarixi.
# Har 30 daqiqada oxirgi sinxrondan beri o'zgargan hujjatlar tortib olinadi (hooks.scheduler_events).
# Server o'zi faqat paroli kiritilgan firmaga kira oladi; ERI bilan kirilgan firma token muddati
# (6 soat) ichida sinxronlanadi.

import frappe
from frappe.utils import add_days, getdate, now_datetime

from carieer.didox.client import DidoxClient, token_key
from carieer.didox.common import holat, hujjat_turi

YONALISH = {1: "Chiquvchi", 0: "Kiruvchi"}
BOSHLANISH = "2024-01-01"  # birinchi sinxron shu sanadan


def sync_all(company: str | None = None):
	settings = frappe.get_cached_doc("Didox Sozlamalari")
	if not settings.yoqilgan:
		return
	for firma in settings.firmalar:
		if company and firma.company != company:
			continue
		can_login = firma.get_password("parol", raise_exception=False) or frappe.cache.get_value(
			token_key(firma.company)
		)
		if not can_login:
			continue
		try:
			sync_firma(firma.company)
		except Exception:
			frappe.log_error(title=f"Didox sinxron: {firma.company}")


def sync_firma(company: str):
	client = DidoxClient(company)
	started = now_datetime()
	since = add_days(getdate(client.firma.oxirgi_sinxron), -1) if client.firma.oxirgi_sinxron else BOSHLANISH
	for owner in (1, 0):
		page = 1
		while True:
			res = client.documents(page=page, owner=owner, dateFromUpdated=str(getdate(since)))
			for row in res.get("data") or []:
				upsert_from_list(company, row, owner)
			frappe.db.commit()
			if not res.get("next_page_url") or not res.get("data"):
				break
			page += 1
	frappe.db.set_value("Didox Firma", client.firma.name, "oxirgi_sinxron", started)
	frappe.clear_document_cache("Didox Sozlamalari", "Didox Sozlamalari")


def get_or_new(didox_id: str):
	if frappe.db.exists("Didox Hujjat", didox_id):
		return frappe.get_doc("Didox Hujjat", didox_id)
	return frappe.new_doc("Didox Hujjat", didox_id=didox_id)


def link_party(doc):
	if not doc.kontragent_inn:
		return
	field = "customer" if doc.yonalish == "Chiquvchi" else "supplier"
	doctype = "Customer" if field == "customer" else "Supplier"
	if not doc.get(field):
		doc.set(field, frappe.db.get_value(doctype, {"tax_id": doc.kontragent_inn}, "name"))


def save(doc):
	link_party(doc)
	doc.flags.ignore_permissions = True
	doc.save()
	return doc


def upsert_from_list(company: str, row: dict, owner: int):
	"""GET /v2/documents ro'yxatidagi bitta qator."""
	doc = get_or_new(row["doc_id"].upper())
	doc.update(
		{
			"company": company,
			"yonalish": YONALISH[owner],
			"hujjat_kodi": row.get("doctype"),
			"hujjat_turi": hujjat_turi(row.get("doctype")),
			"raqam": row.get("name"),
			"sana": row.get("doc_date"),
			"shartnoma_raqami": row.get("contract_number"),
			"shartnoma_sanasi": row.get("contract_date"),
			"kontragent_inn": row.get("partnerTin"),
			"kontragent_nomi": row.get("partnerCompany"),
			"summa": row.get("total_delivery_sum"),
			"qqs_summa": row.get("total_vat_sum"),
			"jami": row.get("total_delivery_sum_with_vat"),
			"status_kod": row.get("doc_status"),
			"holat": holat(row.get("doc_status")),
			"holat_izoh": row.get("status_comment"),
			"imzolangan": row.get("signed"),
			"yangilangan": (row.get("updated_date") or "").replace("T", " ") or None,
		}
	)
	return save(doc)


def tomon(js: dict, owner: int) -> dict:
	"""Kontragent: chiquvchida - qarshi tomon (xaridor / yuk oluvchi / sotuvchi), kiruvchida - jo'natuvchi."""
	if js.get("consignor") or js.get("consignee"):  # TTN
		t = js.get("consignee" if owner == 1 else "consignor") or {}
		return {"inn": t.get("tinorpinfl"), "nomi": t.get("name")}
	if js.get("empowermentdoc"):  # ishonchnoma: biz xaridor bo'lib beramiz, kontragent - sotuvchi
		t = js.get("seller" if owner == 1 else "buyer") or {}
		return {"inn": t.get("tinorpinfl"), "nomi": t.get("name")}
	if js.get("clients") is not None and js.get("owner"):  # shartnoma
		t = (js.get("clients") or [{}])[0] if owner == 1 else js.get("owner") or {}
		return {"inn": t.get("tin"), "nomi": t.get("name")}
	field, party = ("buyertin", "buyer") if owner == 1 else ("sellertin", "seller")
	return {"inn": js.get(field), "nomi": (js.get(party) or {}).get("name")}


def mahsulotlar(js: dict) -> list:
	products = list((js.get("productlist") or {}).get("products") or js.get("products") or [])
	for group in (js.get("roadway") or {}).get("productgroups") or []:  # TTN
		products += (group.get("productinfo") or {}).get("products") or []
	return products


def hujjat_malumoti(js: dict, owner: int) -> frappe._dict:
	"""Har xil hujjat turi JSON'idan (kichik harfli kalitlar): raqam, sana, shartnoma, kontragent, summa."""
	if js.get("facturadoc"):
		raqam, sana = js["facturadoc"].get("facturano"), js["facturadoc"].get("facturadate")
	elif js.get("actdoc"):
		raqam, sana = js["actdoc"].get("actno"), js["actdoc"].get("actdate")
	elif js.get("waybilldoc"):
		raqam, sana = js["waybilldoc"].get("waybillno"), js["waybilldoc"].get("waybilldate")
	elif js.get("empowermentdoc"):
		raqam, sana = js["empowermentdoc"].get("no"), js["empowermentdoc"].get("dateofissue")
	else:  # shartnoma: o'zi contractdoc
		raqam, sana = (js.get("contractdoc") or {}).get("contractno"), (js.get("contractdoc") or {}).get("contractdate")
	contract = js.get("contractdoc") or {}
	products = mahsulotlar(js)
	t = tomon(js, owner)
	return frappe._dict(
		raqam=raqam,
		sana=sana or None,
		shartnoma_raqami=contract.get("contractno") or contract.get("no"),
		shartnoma_sanasi=contract.get("contractdate") or contract.get("date") or None,
		kontragent_inn=t["inn"],
		kontragent_nomi=t["nomi"],
		summa=sum(float(p.get("deliverysum") or 0) for p in products),
		qqs=sum(float(p.get("vatsum") or 0) for p in products),
	)


def upsert_from_detail(company: str, didox_id: str, data: dict, owner: int):
	"""GET /v1/documents/{id} javobi (bitta hujjat to'liq)."""
	meta = data.get("document") or {}
	js = data.get("json") or {}
	m = hujjat_malumoti(js, owner)

	doc = get_or_new(didox_id.upper())
	doc.update(
		{
			"company": company,
			"yonalish": YONALISH[owner],
			"hujjat_kodi": meta.get("doctype"),
			"hujjat_turi": hujjat_turi(meta.get("doctype")),
			"raqam": m.raqam or meta.get("name"),
			"sana": m.sana,
			"shartnoma_raqami": m.shartnoma_raqami,
			"shartnoma_sanasi": m.shartnoma_sanasi,
			"kontragent_inn": m.kontragent_inn,
			"kontragent_nomi": m.kontragent_nomi,
			"summa": m.summa,
			"qqs_summa": m.qqs,
			"jami": m.summa + m.qqs,
			"status_kod": meta.get("doc_status", meta.get("status")),
			"holat": holat(meta.get("doc_status", meta.get("status"))),
			"holat_izoh": meta.get("status_comment"),
			"yangilangan": meta.get("updated"),
			"hujjat_json": frappe.as_json(js),
		}
	)
	return save(doc)


def refresh(hujjat: str):
	doc = frappe.get_doc("Didox Hujjat", hujjat)
	owner = 1 if doc.yonalish == "Chiquvchi" else 0
	data = DidoxClient(doc.company).document(doc.didox_id, owner=owner)
	upsert_from_detail(doc.company, doc.didox_id, data, owner)
