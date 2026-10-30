import frappe

from carieer.install import KONTRAGENT_GURUHLARI, oddiy_supplier_group


def execute():
	"""Ichki ta'minotchi (boshqa firmamiz, masalan «Beton Zavod») setup_firmalararo'da tasodifan «Налог» guruhiga tushib
	qolgan: hisobotlarda soliq bo'lib ketardi, Karer'ning Qarzdorlik «Поставщик»ida Beton'ga qarz ko'rinmasdi."""
	group = oddiy_supplier_group()
	if not group:
		return
	for name in frappe.get_all(
		"Supplier",
		filters={"is_internal_supplier": 1, "supplier_group": ["in", KONTRAGENT_GURUHLARI]},
		pluck="name",
	):
		frappe.db.set_value("Supplier", name, "supplier_group", group)
