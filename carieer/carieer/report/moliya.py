# Moliyaviy hisobotlar (Balans, Karer P&L, Pul Oqimi) uchun umumiy yordamchi funksiyalar.
# Google Sheets'dagi "Баланс", "P&L", "Cash Flow" varaqlari kabi: har bir oy alohida ustun.
# Bu hisobotlar Carieer modulida turadi, shuning uchun Karer rollari (Menejer, Kassir) ERPNext'ning
# Accounts bo'limiga o'tmasdan va Accounts rollarisiz ko'ra oladi.

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate

MAX_OY = 36


def get_months(from_date, to_date) -> list[frappe._dict]:
	"""Davr ichidagi oylar: key ("2026-09"), fieldname ("m_2026_09"), label ("09.2026"), start, end."""
	start, end = get_first_day(getdate(from_date)), getdate(to_date)
	if start > end:
		frappe.throw(_("Boshlanish sanasi tugash sanasidan katta"))
	months = []
	while start <= end:
		months.append(
			frappe._dict(
				key=start.strftime("%Y-%m"),
				fieldname=start.strftime("m_%Y_%m"),
				label=start.strftime("%m.%Y"),
				start=start,
				end=min(getdate(get_last_day(start)), end),
			)
		)
		start = getdate(add_months(start, 1))
		if len(months) > MAX_OY:
			frappe.throw(_("Davr juda katta: ko'pi bilan {0} oy tanlang").format(MAX_OY))
	return months


def month_columns(months, first_label, total=True, width=140):
	cols = [{"fieldname": "label", "label": first_label, "fieldtype": "Data", "width": 320}]
	for m in months:
		cols.append({"fieldname": m.fieldname, "label": m.label, "fieldtype": "Currency", "width": width})
	if total:
		cols.append({"fieldname": "total", "label": _("Жами"), "fieldtype": "Currency", "width": width + 10})
	return cols


def get_accounts(company: str, root_types) -> list[frappe._dict]:
	return frappe.get_all(
		"Account",
		filters={"company": company, "root_type": ["in", list(root_types)]},
		fields=["name", "account_name", "parent_account", "is_group", "root_type", "account_type", "lft", "rgt"],
		order_by="lft",
	)


def get_monthly_gl(company: str, root_types, to_date, from_date=None, skip_closing=False) -> dict:
	"""{account: {"2026-09": debit - credit}}: hisob va oy bo'yicha GL yig'indisi (firma valyutasida)."""
	cond = ""
	if from_date:
		cond += " and gle.posting_date >= %(from_date)s"
	if skip_closing:
		# Yil yopish provodkasi daromad/xarajatni nolga tushiradi - P&L da hisobga olinmaydi
		cond += " and gle.voucher_type != 'Period Closing Voucher'"
	rows = frappe.db.sql(
		f"""select gle.account, date_format(gle.posting_date, '%%Y-%%m') ym, sum(gle.debit) - sum(gle.credit) net
		from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
		where gle.company = %(company)s and gle.is_cancelled = 0 and gle.posting_date <= %(to_date)s
			and acc.root_type in %(root_types)s {cond}
		group by gle.account, ym""",
		{"company": company, "to_date": to_date, "from_date": from_date, "root_types": list(root_types)},
		as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.account, {})[r.ym] = flt(r.net)
	return out


def tree_rows(accounts, values: dict, months, sign=1, skip=None, cumulative=False, base_indent=0) -> tuple[list, dict]:
	"""Hisoblar daraxtini hisobot qatorlariga aylantiradi (guruh = bolalari yig'indisi, nol qatorlar tashlanadi).

	values     - get_monthly_gl natijasi
	sign       - 1: debet - kredit (aktiv, xarajat), -1: kredit - debet (passiv, daromad)
	skip       - qatorga kirmaydigan hisoblar (masalan tan narx hisoblari alohida ko'rsatiladi)
	cumulative - True: oy oxiridagi qoldiq (balans), False: oy ichidagi aylanma (P&L)
	Qaytaradi: (qatorlar, {fieldname: jami})
	"""
	skip = skip or set()
	keys = [m.key for m in months]

	def leaf(account):
		per_month = values.get(account, {})
		if cumulative:
			return [sign * sum(v for ym, v in per_month.items() if ym <= k) for k in keys]
		return [sign * flt(per_month.get(k)) for k in keys]

	by_name = {a.name: a for a in accounts}
	totals = {a.name: [0.0] * len(keys) for a in accounts}
	for a in accounts:
		if a.is_group or a.name in skip:
			continue
		vals = leaf(a.name)
		node = a
		while node:  # o'zi va barcha ota guruhlariga qo'shiladi
			totals[node.name] = [x + y for x, y in zip(totals[node.name], vals)]
			node = by_name.get(node.parent_account)

	depth = {}
	rows = []
	grand = [0.0] * len(keys)
	for a in accounts:  # lft bo'yicha tartiblangan
		depth[a.name] = depth.get(a.parent_account, -1) + 1 if a.parent_account in by_name else 0
		vals = totals[a.name]
		if a.name in skip or not any(abs(v) >= 0.005 for v in vals):
			continue
		if depth[a.name] == 0:
			grand = [x + y for x, y in zip(grand, vals)]
		row = {
			"label": a.account_name,
			"account": a.name,
			"indent": base_indent + depth[a.name],
			"is_group": a.is_group,
			"bold": 1 if a.is_group and depth[a.name] <= 1 else 0,
		}
		row.update(month_values(months, vals, total=not cumulative))
		rows.append(row)
	return rows, month_values(months, grand, total=not cumulative)


def month_values(months, vals, total=True) -> dict:
	out = {m.fieldname: flt(v, 2) for m, v in zip(months, vals)}
	if total:
		out["total"] = flt(sum(vals), 2)
	return out


def line(label, months, vals, total=True, **extra) -> dict:
	"""Yig'ma qator (masalan "Итого", "Чистая прибыль")."""
	if isinstance(vals, dict):
		vals = [flt(vals.get(m.fieldname)) for m in months]
	return {"label": label, **month_values(months, vals, total=total), **extra}


def percent_line(label, months, numerator: dict, denominator: dict) -> dict:
	"""Rentabellik qatori: numerator / denominator * 100 (har oy va jami uchun)."""
	row = {"label": label, "is_percent": 1, "indent": 1}
	for f in [m.fieldname for m in months] + ["total"]:
		d = flt(denominator.get(f))
		row[f] = flt(flt(numerator.get(f)) / d * 100, 1) if d else None
	return row
