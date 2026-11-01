# Panel grafigi: shu oy har bir karer mahsuloti bo'yicha qancha qazib olindi, qancha sotildi va omborda
# qancha qoldi. Sotildi / qoldi - «Материальный отчет» (Продажа, Кон. остаток), qazib olindi - «Qazib olish»
# hujjatlaridan (Мат отчет «Производство» - faqat retsept bo'yicha ishlab chiqarish, Stock Entry Manufacture).

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
	qazib = dict(
		frappe.db.sql(
			"""select i.item_code, sum(i.qty) from `tabQazib Olish Tovar` i
			join `tabQazib Olish` q on q.name = i.parent
			where q.company = %(company)s and q.docstatus = 1
				and q.posting_date between %(from_date)s and %(to_date)s
			group by i.item_code""",
			davr,
		)
	)
	return {
		"labels": [f"{r.item_code} ({r.uom})" for r in rows],
		"datasets": [
			{"name": "Qazib olindi", "values": [flt(qazib.get(r.item_code)) for r in rows]},
			{"name": "Sotildi", "values": [flt(r.prodaja_qty) for r in rows]},
			{"name": "Omborda qoldi", "values": [flt(r.kon_qty) for r in rows]},
		],
	}
