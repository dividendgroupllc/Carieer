# Panel grafigi: shu oy har bir karer mahsuloti bo'yicha qancha qazib olindi, qancha sotildi va omborda qancha
# qoldi. Raqamlar «Материальный отчет» bilan bir xil (o'sha hisobot hisoblaydi).

import frappe
from frappe.utils import flt, get_first_day, nowdate

from carieer.carieer.dashboard import get_company
from carieer.carieer.doctype.qazib_olish.qazib_olish import TOVAR_GURUHLARI
from carieer.carieer.report.material_hisobot.material_hisobot import get_data


@frappe.whitelist()
def get(
	chart_name=None,
	chart=None,
	no_cache=None,
	filters=None,
	from_date=None,
	to_date=None,
	timespan=None,
	time_interval=None,
	heatmap_year=None,
) -> dict:
	frappe.has_permission("Qazib Olish", "read", throw=True)
	company = get_company(filters)
	davr = frappe._dict(company=company, from_date=get_first_day(nowdate()), to_date=nowdate())
	rows = [r for r in get_data(davr) if r.item_group in TOVAR_GURUHLARI]
	return {
		"labels": [f"{r.item_code} ({r.uom})" for r in rows],
		"datasets": [
			{"name": "Qazib olindi", "values": [flt(r.proizv_qty) for r in rows]},
			{"name": "Sotildi", "values": [flt(r.sotuv_qty) for r in rows]},
			{"name": "Omborda qoldi", "values": [flt(r.kon_qty) for r in rows]},
		],
	}
