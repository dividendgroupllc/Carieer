# DDS Hisobot (движение денежных средств): kassa va bank hisoblari bo'yicha
# boshlang'ich qoldiq, kirim, chiqim, yakuniy qoldiq (hisob valyutasida) + moddalar kesimida.

import frappe
from frappe import _
from frappe.utils import flt, getdate

PARTY_LABEL = {
	"Customer": (_("Mijozlardan tushum"), _("Mijozlarga qaytarish")),
	"Supplier": (_("Yetkazib beruvchidan qaytim"), _("Yetkazib beruvchilarga to'lov")),
	"Employee": (_("Xodimdan qaytim"), _("Xodimlarga (oylik, avans)")),
	"Shareholder": (_("Ta'sischidan"), _("Ta'sischiga")),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "name", "label": _("Hisob / modda"), "fieldtype": "Data", "width": 300},
		{"fieldname": "account_currency", "label": _("Valyuta"), "fieldtype": "Link", "options": "Currency", "width": 70},
		{"fieldname": "opening", "label": _("Boshlang'ich qoldiq"), "fieldtype": "Currency", "options": "account_currency", "width": 150},
		{"fieldname": "kirim", "label": _("Kirim"), "fieldtype": "Currency", "options": "account_currency", "width": 150},
		{"fieldname": "chiqim", "label": _("Chiqim"), "fieldtype": "Currency", "options": "account_currency", "width": 150},
		{"fieldname": "closing", "label": _("Yakuniy qoldiq"), "fieldtype": "Currency", "options": "account_currency", "width": 150},
	]


def get_data(filters):
	acc_filters = {"company": filters.company, "account_type": ["in", ["Cash", "Bank"]], "is_group": 0}
	if filters.get("account"):
		acc_filters["name"] = filters.account
	accounts = frappe.get_all("Account", filters=acc_filters, fields=["name", "account_currency"], order_by="lft")
	if not accounts:
		return []
	cash_accounts = {a.name for a in accounts}

	gl = frappe.db.sql(
		"""select gle.account, gle.posting_date, coalesce(nullif(gle.party_type, ''), pe.party_type) party_type,
			gle.against, gle.voucher_type,
			gle.debit_in_account_currency dr, gle.credit_in_account_currency cr
		from `tabGL Entry` gle
		left join `tabPayment Entry` pe on gle.voucher_type = 'Payment Entry' and pe.name = gle.voucher_no
		where gle.company=%(company)s and gle.is_cancelled=0 and gle.posting_date <= %(to_date)s
			and gle.account in %(accounts)s""",
		{**filters, "accounts": tuple(cash_accounts)},
		as_dict=True,
	)
	from_date = getdate(filters.from_date)
	res = {a.name: frappe._dict(opening=0, kirim=0, chiqim=0, moddalar={}) for a in accounts}
	for g in gl:
		r = res[g.account]
		net = flt(g.dr) - flt(g.cr)
		if g.posting_date < from_date:
			r.opening += net
			continue
		r.kirim += flt(g.dr)
		r.chiqim += flt(g.cr)
		key = modda(g, net, cash_accounts)
		m = r.moddalar.setdefault(key, [0, 0])
		m[0] += flt(g.dr)
		m[1] += flt(g.cr)

	data = []
	totals = {}
	for a in accounts:
		r = res[a.name]
		closing = r.opening + r.kirim - r.chiqim
		if not (r.opening or r.kirim or r.chiqim) and not filters.get("show_zero"):
			continue
		data.append(dict(name=a.name, account_currency=a.account_currency, opening=r.opening, kirim=r.kirim,
						 chiqim=r.chiqim, closing=closing, indent=0, bold=1))
		if filters.get("moddalar", 1):
			for key, (dr, cr) in sorted(r.moddalar.items()):
				data.append(dict(name=key, account_currency=a.account_currency, kirim=dr, chiqim=cr, indent=1))
		t = totals.setdefault(a.account_currency, [0, 0, 0, 0])
		for i, v in enumerate((r.opening, r.kirim, r.chiqim, closing)):
			t[i] += v

	for cur, t in totals.items():
		data.append(dict(name=_("JAMI") + f" ({cur})", account_currency=cur, opening=t[0], kirim=t[1], chiqim=t[2],
						 closing=t[3], indent=0, bold=1))
	return data


def modda(g, net, cash_accounts):
	if g.party_type in PARTY_LABEL:
		return PARTY_LABEL[g.party_type][0 if net > 0 else 1]
	against = [a.strip() for a in (g.against or "").split(",") if a.strip()]
	if against and all(a in cash_accounts for a in against):
		return _("Kassa/bank orasida o'tkazma")
	if against:
		return (_("Kirim") if net > 0 else _("Chiqim")) + ": " + against[0]
	return g.voucher_type
