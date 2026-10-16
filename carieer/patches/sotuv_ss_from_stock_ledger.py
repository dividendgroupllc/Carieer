import frappe

from carieer.carieer.doctype.sotuv.sotuv import sales_invoice_cost


def execute():
	"""Eski Sotuv'larda «Цена СС» / «Сумма СС» Sales Invoice'dagi incoming_rate'dan olingan edi - ombordagi
	haqiqiy tan narx (Stock Ledger Entry) bilan qayta hisoblanadi."""
	for name, sales_invoice in frappe.get_all(
		"Sotuv",
		filters={"docstatus": 1, "sales_invoice": ["is", "set"]},
		fields=["name", "sales_invoice"],
		as_list=True,
	):
		cost = sales_invoice_cost(sales_invoice)
		si_rows = frappe.get_all(
			"Sales Invoice Item", filters={"parent": sales_invoice}, pluck="name", order_by="idx"
		)
		rows = frappe.get_all("Sotuv Tovar", filters={"parent": name}, fields=["name", "qty"], order_by="idx")
		for row, si_row in zip(rows, si_rows[: len(rows)], strict=False):
			summa = frappe.utils.flt(cost.get(si_row), 2)
			narx = frappe.utils.flt(summa / row.qty, 2) if row.qty else 0
			frappe.db.set_value(
				"Sotuv Tovar", row.name, {"narx_ss": narx, "summa_ss": summa}, update_modified=False
			)
