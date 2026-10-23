# Sotuv -> Didox hisob-faktura (ESF, hujjat turi 002) JSON'i.
# Didox tuzilmani qat'iy tekshiradi: namunada yo'q maydon yuborilmaydi, ishlatilmaydigan obyekt
# butunligicha null, sanalar yyyy-MM-dd, summalar 2 xona, miqdor 6 xonagacha.

import frappe
from frappe import _
from frappe.utils import flt, getdate

ESF = "002"
ORIGIN_ISHLAB_CHIQARISH = 1  # karerdan qazib olingan tovar
ORIGIN_XIZMAT = 3


def money(value) -> str:
	return f"{flt(value, 2):.2f}"


def stavka(value) -> str:
	return f"{flt(value, 2):g}"


def qator_summalari(count, narx, qqs_tolovchi: bool, qqs_stavka, narx_qqs_bilan: bool) -> dict:
	"""Bitta tovar qatori: Summa (QQSsiz birlik narxi), DeliverySum = Count * Summa, VatSum, jami."""
	count = flt(count, 6)
	rate = flt(qqs_stavka) if qqs_tolovchi else 0
	summa = flt(narx / (1 + rate / 100) if narx_qqs_bilan else narx, 2)
	delivery = flt(count * summa, 2)
	vat = flt(delivery * rate / 100, 2)
	return {
		"Count": count,
		"Summa": money(summa),
		"DeliverySum": money(delivery),
		"VatRate": stavka(rate),
		"VatSum": money(vat),
		"DeliverySumWithVat": money(delivery + vat),
	}


def tomon(info: dict) -> dict:
	"""Didox /v1/utils/info javobi -> Seller / Buyer obyekti."""
	return {
		"Name": info.get("shortName") or info.get("name") or "",
		"BranchCode": "",
		"BranchName": "",
		"VatRegCode": info.get("VATRegCode") or "",
		"Account": info.get("account") or "",
		"BankId": info.get("mfo") or "",
		"Address": info.get("address") or "",
		"Director": info.get("director") or "",
		"Accountant": info.get("accountant") or "",
		"VatRegStatus": info.get("VATRegStatus"),
	}


def sotuv_qatorlari(sotuv) -> list[dict]:
	"""Tovar va xizmat qatorlari: (item_code, nom, miqdor, so'mdagi birlik narx)."""
	kurs = flt(sotuv.conversion_rate) or 1
	rows = []
	for r in sotuv.items:
		rows.append(
			frappe._dict(
				item_code=r.item_code, name=r.item_name or r.item_code, qty=r.qty, rate=flt(r.rate) * kurs
			)
		)
	for r in sotuv.xizmatlar:
		rows.append(frappe._dict(item_code=r.xizmat, name=r.xizmat, qty=r.qty, rate=flt(r.rate) * kurs))
	return [r for r in rows if flt(r.qty) and flt(r.rate)]


def item_malumoti(item_code: str):
	return frappe.get_cached_value(
		"Item",
		item_code,
		["mxik_kod", "mxik_nomi", "upakovka_kod", "upakovka_nomi", "is_stock_item"],
		as_dict=True,
	)


def build_factura(sotuv, firma, seller_info: dict, buyer_inn: str, buyer_info: dict, contract: dict) -> dict:
	qqs_tolovchi = bool(firma.qqs_tolovchi)
	products = []
	missing = []
	for i, row in enumerate(sotuv_qatorlari(sotuv), start=1):
		item = item_malumoti(row.item_code)
		if not (item.mxik_kod and item.upakovka_kod):
			missing.append(row.item_code)
			continue
		product = {
			"OrdNo": i,
			"LgotaId": None,
			"CommittentName": "",
			"CommittentTin": "",
			"CommittentVatRegCode": "",
			"CommittentVatRegStatus": None,
			"Name": row.name,
			"CatalogCode": item.mxik_kod,
			"CatalogName": item.mxik_nomi or row.name,
			"Marks": None,
			"Barcode": "",
			"PackageCode": item.upakovka_kod,
			"PackageName": item.upakovka_nomi or "",
			**qator_summalari(row.qty, row.rate, qqs_tolovchi, firma.qqs_stavka, firma.narx_qqs_bilan),
			"ExciseRate": 0,
			"ExciseSum": 0,
			"LgotaType": None,
			"LgotaName": None,
			"LgotaVatSum": None,
			"WarehouseId": None,
			"Origin": ORIGIN_ISHLAB_CHIQARISH if item.is_stock_item else ORIGIN_XIZMAT,
		}
		if qqs_tolovchi:
			product["WithoutVat"] = False
		products.append(product)

	if missing:
		frappe.throw(
			_("Tovar kartochkasida MXIK (ИКПУ) kodi yoki qadoq kodi yo'q: {0}").format(", ".join(missing)),
			title=_("Didox"),
		)
	if not products:
		frappe.throw(_("Fakturaga tushadigan tovar yoki xizmat yo'q"), title=_("Didox"))

	return {
		"Version": 1,
		"WaybillLocalIds": [],
		"HasMarking": False,
		"HasRent": False,
		"FacturaRentDoc": None,
		"FacturaType": 0,
		"ProductList": {
			"HasCommittent": False,
			"HasLgota": False,
			"Tin": firma.inn,
			"HideReportCommittent": False,
			"HasExcise": False,
			"HasVat": qqs_tolovchi,
			"Products": products,
		},
		"FacturaDoc": {
			"FacturaNo": sotuv.name,
			"FacturaDate": str(getdate(sotuv.posting_date)),
		},
		"ContractDoc": {
			"ContractNo": contract["raqam"],
			"ContractDate": str(getdate(contract["sana"])),
		},
		"ContractId": None,
		"LotId": "",
		"OldFacturaDoc": None,
		"SellerTin": firma.inn,
		"Seller": tomon(seller_info),
		"ItemReleasedDoc": None,
		"BuyerTin": buyer_inn,
		"Buyer": tomon(buyer_info),
		"FacturaInvestmentObjectDoc": None,
		"FacturaEmpowermentDoc": None,
		"ForeignCompany": None,
	}
