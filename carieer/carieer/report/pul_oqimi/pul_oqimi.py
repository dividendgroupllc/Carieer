# Pul Oqimi ("Движение денежных средств"): oyma-oy, kategoriyalar kesimida.
# Google Sheets'dagi "Cash Flow" varag'i tartibida:
#   Денег на начало месяца -> Поступления (kategoriyalar) -> Выплаты (kategoriyalar) -> Денег на конец месяца
# Manba va toifalash DDS hisoboti bilan bir xil (kassa hisoblaridagi GL yozuvlar), shuning uchun ikkalasi doim mos keladi.
# Qator nomi: Kassa hujjatidagi kategoriya; bo'lmasa xarajat/daromad moddasi; kontragent to'lovlari uchun
# kontragent turi (Покупатели, Поставщики ...); kassalar orasidagi o'tkazma - "Перемещение".
# Bitta kassa tanlansa - o'sha kassa valyutasida, aks holda firma valyutasida.

import frappe
from frappe import _
from frappe.utils import flt, getdate

from carieer.carieer.report.dds.dds import CATEGORY_LABELS, get_data as get_dds_data
from carieer.carieer.report.moliya import get_months, line, month_columns
from carieer.utils import check_report_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	check_report_company(filters)
	months = get_months(filters.from_date, filters.to_date)
	return month_columns(months, _("Категория")), get_data(filters, months)


def row_label(d) -> str:
	if d.get("kategoriya"):
		return d["kategoriya"]
	if d["category"] in ("expense", "income", "other"):
		return d["description"]
	if d["category"] == "transfer":
		return _("Перемещение")
	return CATEGORY_LABELS.get(d["category"], d["description"])


def get_data(filters, months):
	dds_filters = frappe._dict(
		company=filters.company,
		from_date=months[0].start,
		to_date=getdate(filters.to_date),
		mode_of_payment=filters.get("mode_of_payment"),
	)
	rows, _expense, opening, _closing = get_dds_data(dds_filters)

	index = {m.key: i for i, m in enumerate(months)}
	n = len(months)
	kirim, chiqim = {}, {}
	for d in rows:
		i = index.get(getdate(d["posting_date"]).strftime("%Y-%m"))
		if i is None:
			continue
		label = row_label(d)
		if flt(d["kirim"]):
			kirim.setdefault(label, [0.0] * n)[i] += flt(d["kirim"])
		if flt(d["chiqim"]):
			chiqim.setdefault(label, [0.0] * n)[i] += flt(d["chiqim"])

	kirim_total = [sum(v[i] for v in kirim.values()) for i in range(n)]
	chiqim_total = [sum(v[i] for v in chiqim.values()) for i in range(n)]
	start, end, balance = [], [], flt(opening)
	for i in range(n):
		start.append(balance)
		balance += kirim_total[i] - chiqim_total[i]
		end.append(balance)

	def balance_line(label, vals):
		# qoldiq qatorlarida "Жами" ustuni ma'nosiz (oylar qoldig'ini qo'shib bo'lmaydi)
		return {**line(label, months, vals, total=False), "bold": 1, "total_row": 1}

	data = [balance_line(_("Денег на начало месяца"), start)]
	data.append(line(_("Поступления"), months, kirim_total, bold=1))
	data += [line(label, months, vals, indent=1) for label, vals in sorted(kirim.items())]
	data.append(line(_("Выплаты"), months, [-v for v in chiqim_total], bold=1))
	data += [line(label, months, [-v for v in vals], indent=1) for label, vals in sorted(chiqim.items())]
	data.append(line(_("Изменение за месяц"), months, [k - c for k, c in zip(kirim_total, chiqim_total)], bold=1))
	data.append(balance_line(_("Денег на конец месяца"), end))
	return data
