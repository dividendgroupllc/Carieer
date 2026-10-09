# Kontrol Hisobot - jadvaldagi «Отчет» (kunlik hisobot) va sotuvlar nazorati.
#   Ko'rinish = «Kunlik otchet»: chapda ПРОДАЖА (mijoz, tovar, miqdor, narx, summa), ostida КАССА (kategoriya
#                bo'yicha kirim / chiqim), tepada kassa qoldig'i: Остаток начало -> приход -> расход -> Остаток конец.
#   Ko'rinish = «Sotuvlar»: har bir sotuv qatori (mashina, to'langan, qarz) - mijoz / tovar / kun bo'yicha guruhlash.

import frappe
from frappe import _
from frappe.utils import flt

from carieer.carieer.report.common import blank_zeros, bold, prepare, usd_rate

GROUPS = {
	"Mijoz": ("customer", _("Mijoz"), "Link", "Customer"),
	"Tovar": ("item_code", _("Tovar"), "Link", "Item"),
	"Kun": ("posting_date", _("Sana"), "Date", None),
	"Mashina": ("mashina_raqami", _("Mashina"), "Data", None),
	"Valyuta": ("currency", _("Valyuta"), "Link", "Currency"),
}


def execute(filters=None):
	kunlik = ((filters or {}).get("korinish") or "Kunlik otchet") == "Kunlik otchet"
	if kunlik and not (filters or {}).get("from_date"):
		# jadvaldagi «Отчет» - bitta kun («Дата отчета»): «Sana dan» bo'sh bo'lsa faqat «Sana gacha» kuni
		filters = dict(filters or {}, from_date=(filters or {}).get("to_date") or frappe.utils.today())
	filters = prepare(filters, period="month")
	if kunlik:
		return kunlik_otchet(filters)
	data = get_data(filters)
	group_by = filters.get("group_by")
	if group_by and group_by in GROUPS:
		columns, data = grouped(data, group_by)
	else:
		columns = get_columns()
	return columns, data, None, get_chart(filters), get_summary(filters)


def conditions(filters, alias="ks"):
	cond = [
		f"{alias}.docstatus = 1",
		# firmalararo sotuv - ikkinchi firma qabul qilgandan keyin sotuv bo'ladi
		f"ifnull({alias}.qabul_holati, '') != 'Kutilmoqda'",
		f"{alias}.posting_date between %(from_date)s and %(to_date)s",
	]
	for f in ("company", "customer", "status", "currency", "tip"):
		if filters.get(f):
			cond.append(f"{alias}.{f} = %({f})s")
	if filters.get("mashina_raqami"):
		cond.append(f"{alias}.mashina_raqami like %(mashina_like)s")
		filters.mashina_like = f"%{filters.mashina_raqami}%"
	if filters.get("item_code"):
		cond.append(
			f"""exists(select 1 from `tabSotuv Tovar` t where t.parent = {alias}.name and t.item_code = %(item_code)s)"""
		)
	return " and ".join(cond)


def get_data(filters):
	"""Har bir tovar va xizmat qatori alohida ("Продажа карьер" varag'idagi kabi).
	To'langan / qarz hujjat bo'yicha - faqat hujjatning birinchi qatorida ko'rsatiladi."""
	rows = frappe.db.sql(
		f"""select ks.name, ks.posting_date, ks.posting_time, ks.tip, ks.customer, ks.customer_name, ks.mashina_raqami,
			ks.currency, ks.conversion_rate, ks.total_paid, ks.outstanding_amount, ks.status, ks.sales_invoice,
			t.item_code, t.item_name, t.qty, t.uom, t.stock_qty, t.rate, t.amount, t.warehouse, t.idx, 0 as is_service
		from `tabSotuv` ks join `tabSotuv Tovar` t on t.parent = ks.name
		where {conditions(filters)}
		union all
		select ks.name, ks.posting_date, ks.posting_time, ks.tip, ks.customer, ks.customer_name, ks.mashina_raqami,
			ks.currency, ks.conversion_rate, ks.total_paid, ks.outstanding_amount, ks.status, ks.sales_invoice,
			x.xizmat, x.xizmat, x.qty, '', 0, x.rate, x.amount, '', 100 + x.idx, 1
		from `tabSotuv` ks join `tabSotuv Xizmat` x on x.parent = ks.name
		where {conditions(filters)} and %(show_services)s = 1
		order by posting_date, posting_time, name, idx""",
		dict(filters, show_services=0 if filters.get("item_code") else 1),
		as_dict=True,
	)
	seen = set()
	cost = get_cost(rows)
	rates = {}
	item_groups = dict(frappe.get_all("Item", fields=["name", "item_group"], as_list=True))
	for r in rows:
		r.base_amount = flt(r.amount) * flt(r.conversion_rate or 1)
		# «Курс» - shu kungi USD kursi, «Сумма $» - dollardagi summa (jadvaldagi kabi)
		kurs = usd_rate(filters.company, r.posting_date, rates) if filters.get("company") else 0
		r.kurs = flt(r.conversion_rate) if r.currency == "USD" else kurs
		r.amount_usd = flt(r.amount) if r.currency == "USD" else (r.base_amount / kurs if kurs else None)
		r.item_group = item_groups.get(r.item_code)
		# «Цена СС / Сумма СС» - sotilgan tovarning tan narxi (ombordan chiqqan qiymat, firma valyutasida)
		if not r.is_service:
			c = cost.get((r.sales_invoice, r.item_code))
			if c and flt(c[0]):
				r.cc_amount = flt(c[1] * flt(r.stock_qty) / c[0], 2)
				r.cc_rate = flt(r.cc_amount / flt(r.qty), 2) if flt(r.qty) else 0
		if r.name in seen:
			r.total_paid = r.outstanding_amount = 0
			r.status = ""
		seen.add(r.name)
	return rows


def get_cost(rows):
	"""{(Sales Invoice, tovar): (ombordan chiqqan miqdor, tan narx qiymati)} - Stock Ledger Entry'dan."""
	invoices = list({r.sales_invoice for r in rows if r.sales_invoice})
	if not invoices:
		return {}
	return {
		(r.voucher_no, r.item_code): (flt(r.qty), flt(r.value))
		for r in frappe.db.sql(
			"""select voucher_no, item_code, -sum(actual_qty) qty, -sum(stock_value_difference) value
			from `tabStock Ledger Entry`
			where voucher_type = 'Sales Invoice' and voucher_no in %(invoices)s and is_cancelled = 0
			group by voucher_no, item_code""",
			{"invoices": invoices},
			as_dict=True,
		)
	}


def get_columns():
	"""«Продажа карьер» varag'i tartibida: Дата, Наименование, Кол-во, Ед.изм, Цена, Валюта, Сумма, Клиент,
	Номер машины, Курс, Сумма $, Цех, Цена СС, Сумма СС, Тип продукта; keyin hujjat va to'lov holati."""
	return [
		{"fieldname": "posting_date", "label": _("Дата"), "fieldtype": "Date", "width": 95},
		{
			"fieldname": "item_code",
			"label": _("Наименование"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 120,
		},
		{"fieldname": "qty", "label": _("Кол-во"), "fieldtype": "Float", "width": 80},
		{"fieldname": "uom", "label": _("Ед.изм"), "fieldtype": "Data", "width": 70},
		{
			"fieldname": "rate",
			"label": _("Цена"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 100,
		},
		{
			"fieldname": "currency",
			"label": _("Валюта"),
			"fieldtype": "Link",
			"options": "Currency",
			"width": 65,
		},
		{
			"fieldname": "amount",
			"label": _("Сумма"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "customer",
			"label": _("Клиент"),
			"fieldtype": "Link",
			"options": "Customer",
			"width": 150,
		},
		{"fieldname": "mashina_raqami", "label": _("Номер машины"), "fieldtype": "Data", "width": 110},
		{"fieldname": "kurs", "label": _("Курс"), "fieldtype": "Float", "precision": "0", "width": 80},
		{"fieldname": "amount_usd", "label": _("Сумма $"), "fieldtype": "Float", "precision": "2", "width": 110},
		{"fieldname": "tip", "label": _("Цех"), "fieldtype": "Data", "width": 100},
		{"fieldname": "cc_rate", "label": _("Цена СС"), "fieldtype": "Currency", "width": 105},
		{"fieldname": "cc_amount", "label": _("Сумма СС"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "item_group", "label": _("Тип продукта"), "fieldtype": "Data", "width": 120},
		{"fieldname": "name", "label": _("Hujjat"), "fieldtype": "Link", "options": "Sotuv", "width": 130},
		{"fieldname": "base_amount", "label": _("Сумма (сўм)"), "fieldtype": "Currency", "width": 120},
		{
			"fieldname": "total_paid",
			"label": _("Оплачено"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 110,
		},
		{
			"fieldname": "outstanding_amount",
			"label": _("Долг"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 110,
		},
		{"fieldname": "status", "label": _("Holat"), "fieldtype": "Data", "width": 100},
	]


def grouped(rows, group_by):
	key, label, ftype, options = GROUPS[group_by]
	out = {}
	for r in rows:
		k = (r[key], r.currency)
		g = out.setdefault(
			k,
			frappe._dict(
				group=r[key],
				currency=r.currency,
				count=0,
				stock_qty=0,
				amount=0,
				total_paid=0,
				outstanding_amount=0,
				base_amount=0,
			),
		)
		g.count += 0 if r.name in g.setdefault("docs", set()) else 1
		g.docs.add(r.name)
		for f in ("stock_qty", "amount", "total_paid", "outstanding_amount", "base_amount"):
			g[f] += flt(r[f])
	col = {"fieldname": "group", "label": label, "fieldtype": ftype, "width": 180}
	if options:
		col["options"] = options
	columns = [
		col,
		{"fieldname": "count", "label": _("Reyslar soni"), "fieldtype": "Int", "width": 100},
		{
			"fieldname": "stock_qty",
			"label": _("Miqdor (ombor birligida)"),
			"fieldtype": "Float",
			"width": 150,
		},
		{
			"fieldname": "currency",
			"label": _("Valyuta"),
			"fieldtype": "Link",
			"options": "Currency",
			"width": 80,
		},
		{
			"fieldname": "amount",
			"label": _("Summa"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"fieldname": "total_paid",
			"label": _("To'langan"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"fieldname": "outstanding_amount",
			"label": _("Qarz"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{"fieldname": "base_amount", "label": _("Summa (UZS)"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "cc_amount", "label": _("Сумма СС (tan narx)"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "foyda", "label": _("Маржа (foyda)"), "fieldtype": "Currency", "width": 140},
	]
	return columns, sorted(out.values(), key=lambda d: (str(d.group), d.currency))


def get_summary(filters):
	rows = frappe.db.sql(
		f"""select currency, sum(amount) amount, sum(total_paid) paid, sum(outstanding_amount) debt, count(*) cnt
		from `tabSotuv` ks where {conditions(filters)} group by currency""",
		filters,
		as_dict=True,
	)
	summary = []
	for r in rows:
		summary += [
			{
				"label": _("Sotuv") + f" ({r.currency})",
				"value": r.amount,
				"datatype": "Currency",
				"currency": r.currency,
				"indicator": "Blue",
			},
			{
				"label": _("To'langan") + f" ({r.currency})",
				"value": r.paid,
				"datatype": "Currency",
				"currency": r.currency,
				"indicator": "Green",
			},
			{
				"label": _("Qarz") + f" ({r.currency})",
				"value": r.debt,
				"datatype": "Currency",
				"currency": r.currency,
				"indicator": "Red",
			},
		]
	if rows:
		summary.append({"label": _("Reyslar"), "value": sum(r.cnt for r in rows), "datatype": "Int"})
	return summary


def get_chart(filters):
	rows = frappe.db.sql(
		f"""select posting_date, sum(base_amount) total from `tabSotuv` ks
		where {conditions(filters)} group by posting_date order by posting_date""",
		filters,
		as_dict=True,
	)
	if not rows:
		return None
	return {
		"data": {
			"labels": [frappe.format(r.posting_date, "Date") for r in rows],
			"datasets": [{"name": _("Sotuv (UZS)"), "values": [flt(r.total) for r in rows]}],
		},
		"type": "bar",
		"fieldtype": "Currency",
	}


# ------------------------------------------------------------------ Kunlik otchet («Отчет» varag'i)
def kunlik_otchet(filters):
	from carieer.carieer.report.dds.dds import get_balances
	from carieer.carieer.report.dds.dds import get_data as get_dds_data

	columns = [
		{"fieldname": "nomi", "label": _("Клиент / Категория"), "fieldtype": "Data", "width": 240},
		{"fieldname": "item_code", "label": _("Наименование товара"), "fieldtype": "Data", "width": 160},
		{"fieldname": "qty", "label": _("Кол-во"), "fieldtype": "Float", "width": 90},
		{"fieldname": "uom", "label": _("Ед.изм"), "fieldtype": "Data", "width": 70},
		{"fieldname": "rate", "label": _("Цена"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "summa", "label": _("Сумма"), "fieldtype": "Float", "precision": 2, "width": 140},
		{"fieldname": "tolandi", "label": _("Тўланди"), "fieldtype": "Float", "precision": 2, "width": 130},
		{"fieldname": "qarz", "label": _("Қарзга"), "fieldtype": "Float", "precision": 2, "width": 130},
		{"fieldname": "prixod", "label": _("Кассага кирим"), "fieldtype": "Float", "precision": 2, "width": 140},
		{"fieldname": "rasxod", "label": _("Кассадан чиқим"), "fieldtype": "Float", "precision": 2, "width": 140},
		{"fieldname": "currency", "label": _("Валюта"), "fieldtype": "Data", "width": 70},
	]
	numeric = ("qty", "rate", "summa", "tolandi", "qarz", "prixod", "rasxod")
	data = [{"nomi": bold(_("ПРОДАЖА"))}]
	sales = frappe.db.sql(
		f"""select ks.customer_name, t.item_code, t.uom, ks.currency, sum(t.qty) qty, sum(t.amount) summa
		from `tabSotuv` ks join `tabSotuv Tovar` t on t.parent = ks.name
		where {conditions(filters)}
		group by ks.customer_name, t.item_code, t.uom, ks.currency
		union all
		select ks.customer_name, x.xizmat, '', ks.currency, sum(x.qty) qty, sum(x.amount) summa
		from `tabSotuv` ks join `tabSotuv Xizmat` x on x.parent = ks.name
		where {conditions(filters)}
		group by ks.customer_name, x.xizmat, ks.currency
		order by customer_name, item_code""",
		filters,
		as_dict=True,
	)
	# mijoz bo'yicha to'lov holati (sotuv hujjatlari bo'yicha: to'langan / qarzga qolgan)
	tolov = {
		(r.customer_name, r.currency): r
		for r in frappe.db.sql(
			f"""select ks.customer_name, ks.currency, sum(ks.total_paid) tolandi, sum(ks.outstanding_amount) qarz
			from `tabSotuv` ks where {conditions(filters)} group by ks.customer_name, ks.currency""",
			filters,
			as_dict=True,
		)
	}
	jami, shown = {}, set()
	for r in sales:
		row = {
			"nomi": r.customer_name,
			"item_code": r.item_code,
			"qty": flt(r.qty),
			"uom": r.uom,
			"rate": flt(r.summa) / flt(r.qty) if flt(r.qty) else 0,
			"summa": flt(r.summa),
			"currency": r.currency,
			"indent": 1,
		}
		key = (r.customer_name, r.currency)
		if key not in shown and key in tolov:  # mijozning birinchi qatorida
			shown.add(key)
			row.update(tolandi=flt(tolov[key].tolandi), qarz=flt(tolov[key].qarz))
		data.append(row)
		t = jami.setdefault(r.currency, [0.0, 0.0, 0.0])
		t[0] += flt(r.summa)
	for (_c, cur), r in tolov.items():
		t = jami.setdefault(cur, [0.0, 0.0, 0.0])
		t[1] += flt(r.tolandi)
		t[2] += flt(r.qarz)
	for cur, (total, tolandi, qarz) in jami.items():
		data.append({"nomi": bold(_("Итого продажа")), "summa": total, "tolandi": tolandi, "qarz": qarz, "currency": cur, "indent": 1})
	if not sales:
		data.append({"nomi": _("Sotuv yo'q"), "indent": 1})

	data += prixod_rows(filters)

	summary = []
	if not frappe.has_permission("GL Entry", "read"):
		# operator kassa harakatlarini ko'rmaydi (faqat kassir / menejer)
		return columns, blank_zeros(data, numeric), None, None, summary

	data.append({"nomi": bold(_("КАССА"))})
	dds_filters = frappe._dict(
		company=filters.company,
		from_date=filters.from_date,
		to_date=filters.to_date,
		mode_of_payment=filters.get("mode_of_payment"),
	)
	groups = {}
	for d in get_dds_data(dds_filters)[0]:
		g = groups.setdefault((d["dds_kategoriya"], d["acc_currency"]), [0.0, 0.0])
		g[0] += d["kirim_acc"]
		g[1] += d["chiqim_acc"]
	for (kategoriya, cur), (kirim, chiqim) in sorted(groups.items()):
		data.append({"nomi": kategoriya, "prixod": kirim, "rasxod": chiqim, "currency": cur, "indent": 1})
	if not groups:
		data.append({"nomi": _("Kassada harakat yo'q (sotuv qarzga yoki avansdan yopilgan)"), "indent": 1})

	for cur, b in get_balances(dds_filters).items():
		summary += [
			{
				"label": _("Kassada boshida ({0})").format(cur),
				"value": b["opening"],
				"datatype": "Float",
				"indicator": "Blue",
			},
			{
				"label": _("Kassaga kirdi ({0})").format(cur),
				"value": b["kirim"],
				"datatype": "Float",
				"indicator": "Green",
			},
			{
				"label": _("Kassadan chiqdi ({0})").format(cur),
				"value": b["chiqim"],
				"datatype": "Float",
				"indicator": "Red",
			},
			{
				"label": _("Kassada oxirida ({0})").format(cur),
				"value": b["closing"],
				"datatype": "Float",
				"indicator": "Blue",
			},
		]
	return columns, blank_zeros(data, numeric), None, None, summary


def prixod_rows(filters) -> list[dict]:
	"""ПРИХОД (xarid): davr ichida kimdan nima olindi - Xarid fakturasi (o'zimizning ikkinchi firmamizdan olingan tovar
	ham) va xizmat nachisleniyasi. To'langan / qarzga qolgan qismi bilan."""
	rows = frappe.db.sql(
		"""select pi.name, pi.supplier_name, pi.supplier, i.item_name, i.qty, i.uom, i.rate, i.amount,
			pi.currency, pi.grand_total, pi.outstanding_amount, pi.represents_company
		from `tabPurchase Invoice` pi join `tabPurchase Invoice Item` i on i.parent = pi.name
		where pi.company = %(company)s and pi.docstatus = 1 and pi.is_return = 0
			and pi.posting_date between %(from_date)s and %(to_date)s
		order by pi.posting_date, pi.name, i.idx""",
		filters,
		as_dict=True,
	)
	nach = frappe.db.sql(
		"""select party_name, kategoriya, qty, rate, amount, currency from `tabNachislenie`
		where company = %(company)s and docstatus = 1 and turi = 'Закуп услуга'
			and sana between %(from_date)s and %(to_date)s""",
		filters,
		as_dict=True,
	)
	out = [{"nomi": bold(_("ПРИХОД (xarid)"))}]
	if not rows and not nach:
		out.append({"nomi": _("Xarid yo'q"), "indent": 1})
		return out
	shown, jami = set(), {}
	for r in rows:
		nomi = r.supplier_name or r.supplier
		if r.represents_company:
			nomi += " " + _("(firmalararo)")
		row = {
			"nomi": nomi,
			"item_code": r.item_name,
			"qty": flt(r.qty),
			"uom": r.uom,
			"rate": flt(r.rate),
			"summa": flt(r.amount),
			"currency": r.currency,
			"indent": 1,
		}
		if r.name not in shown:  # hujjatning birinchi qatorida
			shown.add(r.name)
			row.update(tolandi=flt(r.grand_total) - flt(r.outstanding_amount), qarz=flt(r.outstanding_amount))
		out.append(row)
		jami[r.currency] = jami.get(r.currency, 0) + flt(r.amount)
	for n in nach:
		out.append(
			{
				"nomi": n.party_name,
				"item_code": n.kategoriya or _("Xizmat"),
				"qty": flt(n.qty),
				"rate": flt(n.rate),
				"summa": flt(n.amount),
				"qarz": flt(n.amount),
				"currency": n.currency,
				"indent": 1,
			}
		)
		jami[n.currency] = jami.get(n.currency, 0) + flt(n.amount)
	for cur, total in jami.items():
		out.append({"nomi": bold(_("Итого приход")), "summa": total, "currency": cur, "indent": 1})
	return out
