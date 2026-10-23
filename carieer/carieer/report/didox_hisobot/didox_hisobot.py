# Didox Hisobot: firmaning Didox orqali o'tgan hujjatlari - kim bilan, qachon, qancha.
# Guruhlash: kontragent, oy, yil, hujjat turi yoki har bir hujjat alohida.
# O'chirilgan hujjatlar va qoralama o'chirilganlar hisobga olinmaydi.

import frappe
from frappe import _
from frappe.utils import flt, getdate

OCHIRILGAN = (5, 55)

GURUH = {
	"Kontragent": ("kontragent", _("Kontragent")),
	"Oy": ("oy", _("Oy")),
	"Yil": ("yil", _("Yil")),
	"Hujjat turi": ("hujjat_turi", _("Hujjat turi")),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_rows(filters)
	if filters.guruhlash == "Hujjatlar":
		return hujjat_columns(), rows
	return guruh_columns(filters.guruhlash), group(rows, GURUH[filters.guruhlash][0])


def get_rows(filters):
	conditions = {
		"company": filters.company,
		"sana": ["between", [filters.from_date, filters.to_date]],
		"status_kod": ["not in", OCHIRILGAN],
	}
	if filters.yonalish:
		conditions["yonalish"] = filters.yonalish
	if filters.faqat_imzolangan:
		conditions["holat"] = "Imzolangan"
	rows = frappe.get_all(
		"Didox Hujjat",
		filters=conditions,
		fields=[
			"name",
			"sana",
			"yonalish",
			"hujjat_turi",
			"raqam",
			"kontragent_nomi",
			"kontragent_inn",
			"holat",
			"summa",
			"qqs_summa",
			"jami",
			"sotuv",
		],
		order_by="sana asc, raqam asc",
	)
	for r in rows:
		r.kontragent = r.kontragent_nomi or r.kontragent_inn or _("Noma'lum")
		r.oy = getdate(r.sana).strftime("%Y-%m") if r.sana else ""
		r.yil = str(getdate(r.sana).year) if r.sana else ""
		r.chiquvchi = flt(r.jami) if r.yonalish == "Chiquvchi" else 0
		r.kiruvchi = flt(r.jami) if r.yonalish == "Kiruvchi" else 0
	return rows


def group(rows, key):
	out = {}
	for r in rows:
		g = out.setdefault(
			r[key],
			frappe._dict(
				guruh=r[key], soni=0, imzolangan=0, summa=0, qqs_summa=0, jami=0, chiquvchi=0, kiruvchi=0
			),
		)
		g.soni += 1
		g.imzolangan += 1 if r.holat == "Imzolangan" else 0
		for f in ("summa", "qqs_summa", "jami", "chiquvchi", "kiruvchi"):
			g[f] += flt(r[f])
	return sorted(out.values(), key=lambda g: g.guruh)


def money(fieldname, label, width=150):
	return {"label": label, "fieldname": fieldname, "fieldtype": "Currency", "width": width}


def guruh_columns(guruhlash):
	return [
		{"label": GURUH[guruhlash][1], "fieldname": "guruh", "fieldtype": "Data", "width": 260},
		{"label": _("Hujjatlar"), "fieldname": "soni", "fieldtype": "Int", "width": 100},
		{"label": _("Imzolangan"), "fieldname": "imzolangan", "fieldtype": "Int", "width": 110},
		money("chiquvchi", _("Chiquvchi (sotuv)")),
		money("kiruvchi", _("Kiruvchi (xarid)")),
		money("summa", _("Summa (QQSsiz)")),
		money("qqs_summa", _("QQS"), 130),
		money("jami", _("Jami")),
	]


def hujjat_columns():
	return [
		{"label": _("Sana"), "fieldname": "sana", "fieldtype": "Date", "width": 100},
		{
			"label": _("Hujjat"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Didox Hujjat",
			"width": 120,
		},
		{"label": _("Raqam"), "fieldname": "raqam", "fieldtype": "Data", "width": 120},
		{"label": _("Turi"), "fieldname": "hujjat_turi", "fieldtype": "Data", "width": 130},
		{"label": _("Yo'nalish"), "fieldname": "yonalish", "fieldtype": "Data", "width": 100},
		{"label": _("Kontragent"), "fieldname": "kontragent", "fieldtype": "Data", "width": 220},
		{"label": _("INN"), "fieldname": "kontragent_inn", "fieldtype": "Data", "width": 110},
		{"label": _("Holat"), "fieldname": "holat", "fieldtype": "Data", "width": 160},
		money("summa", _("Summa (QQSsiz)")),
		money("qqs_summa", _("QQS"), 130),
		money("jami", _("Jami")),
		{"label": _("Sotuv"), "fieldname": "sotuv", "fieldtype": "Link", "options": "Sotuv", "width": 140},
	]
