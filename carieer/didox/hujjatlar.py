# Didox: Sotuv'dan TTN, yetkazib beruvchidan tovar olish uchun ishonchnoma, mijoz bilan shartnoma.
# Har biri Didox'da qoralama bo'lib yaratiladi va «Didox Hujjat»ga tushadi; keyin u yerdagi
# «Imzolab yuborish» (ERI) bilan yuboriladi - imzolash chiquvchi faktura bilan bir xil.
# Ikki tomon rekvizitlari (rahbar PINFL, OKED, bank) soliq bazasidan olinadi (Didox utils/info).

import frappe
from frappe import _
from frappe.utils import flt, getdate

from carieer.didox.client import DidoxClient, get_firma
from carieer.didox.factura import item_malumoti, qator_summalari, sotuv_qatorlari
from carieer.didox.sync import upsert_from_detail

TTN = "041"
ISHONCHNOMA = "062"
SHARTNOMA = "007"

KATALOG_TTL = 24 * 3600


# ---------------------------------------------------------------- yordamchilar
def pinfl(qiymat, label: str) -> str:
	v = "".join(str(qiymat or "").split())
	if len(v) != 14 or not v.isdigit():
		frappe.throw(_("{0}: PINFL 14 ta raqamdan iborat bo'lishi kerak").format(label))
	return v


def summa_str(x) -> str:
	return f"{flt(x, 2):.2f}"


def miqdor_str(x) -> str:
	return f"{flt(x):f}".rstrip("0").rstrip(".") or "0"


def nom(info: dict) -> str:
	return info.get("shortName") or info.get("name") or ""


def nuqta(region_id, district_code, manzil, regions: list, districts: list) -> dict:
	"""TTN yuklash / tushirish manzili (Didox viloyat va tuman ma'lumotnomasidan nomlari bilan)."""
	region = next((r for r in regions if int(r["regionId"]) == int(region_id or 0)), None)
	district = next(
		(
			d
			for d in districts
			if int(d["regionId"]) == int(region_id or 0) and int(d["districtCode"]) == int(district_code or 0)
		),
		None,
	)
	if not (region and district):
		frappe.throw(_("Viloyat yoki tuman noto'g'ri tanlangan"))
	if not (manzil or "").strip():
		frappe.throw(_("Manzil yozilmagan"))
	return {
		"regionId": int(region["regionId"]),
		"regionName": region["name"],
		"districtCode": int(district["districtCode"]),
		"districtName": district["name"],
		"mahallaId": None,
		"mahallaName": None,
		"address": manzil.strip(),
		"longitude": None,
		"latitude": None,
	}


def katalog(client: DidoxClient) -> tuple[list, list]:
	"""Didox viloyat va tumanlar ro'yxati (kamdan-kam o'zgaradi - bir kun keshda)."""
	data = frappe.cache.get_value("didox_regions_districts")
	if not data:
		data = {"regions": client.get("/v1/regions/all"), "districts": client.get("/v1/districts/all")}
		frappe.cache.set_value("didox_regions_districts", data, expires_in_sec=KATALOG_TTL)
	return data["regions"], data["districts"]


def tovar(item_code: str, miqdor, narx=0, nomi: str | None = None):
	item = item_malumoti(item_code)
	if not (item.mxik_kod and item.upakovka_kod):
		frappe.throw(_("Tovar kartochkasida MXIK (ИКПУ) kodi yoki qadoq kodi yo'q: {0}").format(item_code))
	return frappe._dict(
		nomi=nomi or item_code,
		mxik=item.mxik_kod,
		mxik_nomi=item.mxik_nomi,
		qadoq_kod=item.upakovka_kod,
		qadoq=item.upakovka_nomi,
		miqdor=flt(miqdor),
		narx=flt(narx),
		is_stock_item=item.is_stock_item,
	)


def firma_sozlama(company: str, qiymatlar: dict):
	"""Keyingi safar oldindan to'ldirish uchun Didox Firma qatoriga yoziladi."""
	frappe.db.set_value("Didox Firma", get_firma(company).name, qiymatlar)
	frappe.clear_document_cache("Didox Sozlamalari", "Didox Sozlamalari")


def yarat(client: DidoxClient, kod: str, js: dict, **boglanish) -> str:
	res = client.create(kod, js)
	didox_id = res["_id"].upper()
	h = upsert_from_detail(client.company, didox_id, client.document(didox_id, owner=1), owner=1)
	for field, value in boglanish.items():
		if value:
			h.db_set(field, value)
	return h.name


def kontragent_inn(doctype: str, name: str) -> str:
	inn = "".join((frappe.db.get_value(doctype, name, "tax_id") or "").split())
	if len(inn) not in (9, 14) or not inn.isdigit():
		frappe.throw(_("{0} kartochkasida INN (9 raqam) yoki JShShIR (14 raqam) yo'q").format(name))
	return inn


# ---------------------------------------------------------------- TTN (Sotuv'dan)
def ttn_tomon(inn: str, info: dict) -> dict:
	return {"TinOrPinfl": inn, "Name": nom(info), "BranchCode": "", "BranchName": ""}


def build_ttn(v, tovarlar, biz_inn, biz, mijoz_inn, mijoz, regions, districts) -> dict:
	products = [
		{
			"ordNo": i,
			"CommittentTinOrPinfl": "",
			"CommittentName": "",
			"CatalogCode": t.mxik,
			"CatalogName": t.mxik_nomi or t.nomi,
			"ProductName": t.nomi,
			"PackageCode": t.qadoq_kod,
			"PackageName": t.qadoq,
			"Amount": miqdor_str(t.miqdor),
			"Price": summa_str(t.narx),
			"DeliverySum": summa_str(t.miqdor * t.narx),
			"WeightBrutto": 0,
			"WeightNetto": 0,
		}
		for i, t in enumerate(tovarlar, start=1)
	]
	biz_t, mijoz_t = ttn_tomon(biz_inn, biz), ttn_tomon(mijoz_inn, mijoz)
	contract = {"ContractNo": v.shartnoma_raqami, "ContractDate": str(getdate(v.shartnoma_sanasi))}
	return {
		"WaybillLocalType": 0,
		"DeliveryType": 2,
		"WaybillDoc": {"WaybillNo": v.raqam, "WaybillDate": str(getdate(v.sana))},
		"ContractDoc": contract,
		"OldWaybillDoc": None,
		"HasCommittent": False,
		"SingleSidedType": 0,
		"Consignor": biz_t,
		"Consignee": mijoz_t,
		"FreightForwarder": None,
		# mijoz o'z mashinasida olib ketadi yoki Karer o'z texnikasida yetkazadi
		"Carrier": mijoz_t if v.tashuvchi == "Mijoz" else biz_t,
		"Client": {**mijoz_t, **contract},
		"Payer": None,
		"TransportType": 1,
		"Roadway": {
			"OtherCarOwners": None,
			"Truck": {"RegNo": v.mashina_raqami, "Model": v.mashina_modeli},
			"Trailer": None,
			"Carriages": [],
			"Driver": {"pinfl": pinfl(v.haydovchi_pinfl, _("Haydovchi")), "FullName": v.haydovchi_fio},
			"ProductGroups": [
				{
					"LoadingPoint": nuqta(v.yuklash_viloyat, v.yuklash_tuman, v.yuklash_manzil, regions, districts),
					"LoadingTrustee": {
						"pinfl": pinfl(v.yuklash_masul_pinfl, _("Yuklovchi mas'ul")),
						"fullName": v.yuklash_masul_fio,
					},
					"UnloadingPoint": nuqta(
						v.tushirish_viloyat, v.tushirish_tuman, v.tushirish_manzil, regions, districts
					),
					"UnloadingTrustee": {
						"Pinfl": pinfl(v.tushirish_masul_pinfl, _("Qabul qiluvchi mas'ul")),
						"FullName": v.tushirish_masul_fio,
					},
					"UnloadingEmpowerment": None,
					"ProductInfo": {
						"TotalDeliverySum": flt(sum(flt(p["DeliverySum"]) for p in products), 2),
						"TotalWeightBrutto": 0,
						"products": products,
					},
				}
			],
		},
		"Railway": None,
		"ResponsiblePerson": None,
		"ResponsibleCompany": None,
		"TotalDistance": summa_str(v.masofa),
		"DeliveryCost": summa_str(v.km_narxi),
		"TotalDeliveryCost": summa_str(flt(v.masofa) * flt(v.km_narxi)),
	}


def sotuv_tovarlari(sotuv) -> list:
	"""TTN'ga Sotuv'ning faqat ombor tovarlari kiradi (xizmatlar - yuk emas)."""
	out = []
	for r in sotuv_qatorlari(sotuv):
		if not frappe.get_cached_value("Item", r.item_code, "is_stock_item"):
			continue
		out.append(tovar(r.item_code, r.qty, r.rate, r.name))
	if not out:
		frappe.throw(_("Sotuv'da TTN uchun tovar yo'q"))
	return out


def sotuv_ttnlari(sotuv: str) -> list:
	return frappe.get_all(
		"Didox Hujjat",
		filters={"sotuv": sotuv, "hujjat_kodi": TTN, "status_kod": ["not in", (5, 55)]},
		pluck="name",
	)


def ttn_malumoti(sotuv_name: str) -> dict:
	sotuv = frappe.get_doc("Sotuv", sotuv_name)
	firma = get_firma(sotuv.company)
	client = DidoxClient(sotuv.company)
	regions, districts = katalog(client)
	mashina, model = sotuv.mashina_raqami, ""
	if sotuv.get("vehicle"):
		v = frappe.db.get_value("Vehicle", sotuv.vehicle, ["license_plate", "model", "make"], as_dict=True) or {}
		mashina = mashina or v.get("license_plate") or sotuv.vehicle
		model = " ".join(filter(None, [v.get("make"), v.get("model")]))
	return {
		"mavjud": sotuv_ttnlari(sotuv.name),
		"tovarlar": sotuv_tovarlari(sotuv),
		"tashuvchi": "Karer" if sotuv.get("dostavka") == "Да" else "Mijoz",
		"mashina_raqami": mashina,
		"mashina_modeli": model,
		"haydovchi_fio": sotuv.get("haydovchi"),
		"yuklash_viloyat": firma.yuklash_viloyat,
		"yuklash_tuman": firma.yuklash_tuman,
		"yuklash_manzil": firma.yuklash_manzil,
		"yuklash_masul_pinfl": firma.yuklash_masul_pinfl,
		"yuklash_masul_fio": firma.yuklash_masul_fio,
		"regions": regions,
		"districts": districts,
	}


def ttn_yaratish(sotuv_name: str, v: dict) -> str:
	v = frappe._dict(v)
	sotuv = frappe.get_doc("Sotuv", sotuv_name)
	if sotuv.docstatus != 1:
		frappe.throw(_("Avval Sotuv'ni tasdiqlang (Submit)"))
	inn = kontragent_inn("Customer", sotuv.customer)
	customer = frappe.db.get_value("Customer", sotuv.customer, ["shartnoma_raqami", "shartnoma_sanasi"], as_dict=True)
	if not (customer.shartnoma_raqami and customer.shartnoma_sanasi):
		frappe.throw(_("Mijoz {0} kartochkasida shartnoma raqami va sanasi yo'q").format(sotuv.customer))
	v.update(
		raqam=sotuv.name,
		sana=sotuv.posting_date,
		shartnoma_raqami=customer.shartnoma_raqami,
		shartnoma_sanasi=customer.shartnoma_sanasi,
	)
	client = DidoxClient(sotuv.company)
	regions, districts = katalog(client)
	sana = str(getdate(sotuv.posting_date))
	js = build_ttn(
		v,
		sotuv_tovarlari(sotuv),
		client.firma.inn,
		client.org_info(client.firma.inn, sana, seller=True),
		inn,
		client.org_info(inn, sana),
		regions,
		districts,
	)
	name = yarat(client, TTN, js, sotuv=sotuv.name)
	if v.saqlash:
		firma_sozlama(
			sotuv.company,
			{
				k: v.get(k)
				for k in ("yuklash_viloyat", "yuklash_tuman", "yuklash_manzil", "yuklash_masul_pinfl", "yuklash_masul_fio")
			},
		)
	return name


# ---------------------------------------------------------------- ishonchnoma (biz - xaridor)
def tomon_062(inn: str, info: dict) -> dict:
	return {
		"TinOrPinfl": inn,
		"Name": nom(info),
		"BranchCode": "",
		"BranchName": "",
		"Address": info.get("address") or "",
		"Director": {"Pinfl": info.get("directorPinfl") or "", "FullName": info.get("director") or ""},
	}


def build_ishonchnoma(v, biz_inn, biz, sotuvchi_inn, sotuvchi, tovarlar) -> dict:
	return {
		"EmpowermentType": 0,
		"EmpowermentDoc": {
			"No": v.raqam,
			"DateOfIssue": str(getdate(v.sana)),
			"DateOfExpire": str(getdate(v.muddat)),
		},
		"ContractDoc": {
			"No": v.shartnoma_raqami or "",
			"Date": str(getdate(v.shartnoma_sanasi)) if v.shartnoma_sanasi else None,
		},
		"Seller": tomon_062(sotuvchi_inn, sotuvchi),
		"Buyer": {
			**tomon_062(biz_inn, biz),
			"Accountant": {
				"Pinfl": pinfl(v.buxgalter_pinfl, _("Bosh buxgalter")),
				"FullName": v.buxgalter_fio,
			},
		},
		"Agent": {"Pinfl": pinfl(v.agent_pinfl, _("Ishonchli shaxs")), "FullName": v.agent_fio},
		"Products": [
			{
				"OrdNo": i,
				"Name": t.nomi,
				"CatalogCode": t.mxik,
				"CatalogName": t.mxik_nomi or t.nomi,
				"PackageCode": t.qadoq_kod,
				"PackageName": t.qadoq,
				"Amount": flt(t.miqdor),
			}
			for i, t in enumerate(tovarlar, start=1)
		],
	}


def ishonchnoma_yaratish(company: str, v: dict) -> str:
	v = frappe._dict(v)
	if getdate(v.muddat) < getdate(v.sana):
		frappe.throw(_("Amal qilish muddati berilgan sanadan oldin bo'lishi mumkin emas"))
	inn = kontragent_inn("Supplier", v.supplier)
	tovarlar = [tovar(r["item_code"], r.get("miqdor")) for r in v.get("tovarlar") or []]
	if not tovarlar:
		frappe.throw(_("Kamida bitta tovar kiriting"))
	client = DidoxClient(company)
	sana = str(getdate(v.sana))
	js = build_ishonchnoma(
		v, client.firma.inn, client.org_info(client.firma.inn, sana), inn, client.org_info(inn, sana), tovarlar
	)
	name = yarat(client, ISHONCHNOMA, js, supplier=v.supplier)
	if v.saqlash:
		firma_sozlama(company, {"buxgalter_pinfl": v.buxgalter_pinfl, "buxgalter_fio": v.buxgalter_fio})
	return name


# ---------------------------------------------------------------- shartnoma (biz - yetkazib beruvchi)
def tomon_007(inn: str, info: dict) -> dict:
	return {
		"Tin": inn,
		"Name": nom(info),
		"BranchCode": "",
		"BranchName": "",
		"FizTin": info.get("directorPinfl") or "",
		"Fio": info.get("director") or "",
		"Address": info.get("address") or "",
		"WorkPhone": "",
		"Mobile": "",
		"Oked": info.get("oked") or "",
		"Account": info.get("account") or "",
		"BankId": info.get("mfo") or "",
	}


def build_shartnoma(v, firma, biz_inn, biz, mijoz_inn, mijoz, tovarlar) -> dict:
	bolimlar = [b for b in (v.bolimlar or []) if (b.get("title") or "").strip() and (b.get("body") or "").strip()]
	if not bolimlar:
		frappe.throw(_("Shartnoma matni kerak: kamida bitta bo'lim (sarlavha va matn)"))
	qqs = bool(firma.qqs_tolovchi)
	products = [
		{
			"OrdNo": i,
			"Name": t.nomi,
			"CatalogCode": t.mxik,
			"CatalogName": t.mxik_nomi or t.nomi,
			"Barcode": "",
			"MeasureId": None,
			"PackageCode": t.qadoq_kod,
			"PackageName": t.qadoq,
			**qator_summalari(t.miqdor, t.narx, qqs, firma.qqs_stavka, firma.narx_qqs_bilan),
			"WithoutVat": not qqs,
		}
		for i, t in enumerate(tovarlar, start=1)
	]
	return {
		"ContractDoc": {
			"ContractName": v.nomi,
			"ContractNo": v.raqam,
			"ContractDate": str(getdate(v.sana)),
			"ContractExpireDate": str(getdate(v.muddat)),
			"ContractPlace": v.joyi,
		},
		"Owner": tomon_007(biz_inn, biz),
		"Clients": [tomon_007(mijoz_inn, mijoz)],
		"Parts": [
			{"ordno": i, "title": b["title"].strip(), "body": b["body"].strip()} for i, b in enumerate(bolimlar, start=1)
		],
		"Products": products,
		"HasVat": qqs,
	}


def shartnoma_yaratish(company: str, v: dict) -> str:
	v = frappe._dict(v)
	if getdate(v.muddat) < getdate(v.sana):
		frappe.throw(_("Tugash sanasi shartnoma sanasidan oldin bo'lishi mumkin emas"))
	inn = kontragent_inn("Customer", v.customer)
	tovarlar = [tovar(r["item_code"], r.get("miqdor"), r.get("narx")) for r in v.get("tovarlar") or []]
	if not tovarlar:
		frappe.throw(_("Kamida bitta tovar kiriting"))
	client = DidoxClient(company)
	sana = str(getdate(v.sana))
	js = build_shartnoma(
		v,
		client.firma,
		client.firma.inn,
		client.org_info(client.firma.inn, sana, seller=True),
		inn,
		client.org_info(inn, sana),
		tovarlar,
	)
	name = yarat(client, SHARTNOMA, js, customer=v.customer)
	# mijozda shartnoma yozilmagan bo'lsa - hisob-faktura va TTN shu shartnomaga tayansin
	customer = frappe.db.get_value("Customer", v.customer, ["shartnoma_raqami", "shartnoma_sanasi"], as_dict=True)
	if not customer.shartnoma_raqami:
		frappe.db.set_value(
			"Customer", v.customer, {"shartnoma_raqami": v.raqam, "shartnoma_sanasi": getdate(v.sana)}
		)
	return name
