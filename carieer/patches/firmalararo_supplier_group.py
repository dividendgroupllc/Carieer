import frappe

from carieer.install import KONTRAGENT_GURUHLARI


def execute():
	"""Ichki ta'minotchi (boshqa firmamiz, masalan «Beton Zavod») setup_firmalararo'da tasodifan «Налог» guruhiga tushib
	qolgan: hisobotlarda soliq bo'lib ketardi, Karer'ning Qarzdorlik «Поставщик»ida Beton'ga qarz ko'rinmasdi.
	Faqat ma'lumot tuzatiladi; setup_firmalararo kodi (Sherzod) o'zgartirilmaydi."""
	group = frappe.db.get_single_value("Buying Settings", "supplier_group") or frappe.db.get_value(
		"Supplier Group",
		{"is_group": 0, "name": ["not in", KONTRAGENT_GURUHLARI]},
		"name",
		order_by="creation asc",
	)
	if not group:
		return
	for name in frappe.get_all(
		"Supplier",
		filters={"is_internal_supplier": 1, "supplier_group": ["in", KONTRAGENT_GURUHLARI]},
		pluck="name",
	):
		frappe.db.set_value("Supplier", name, "supplier_group", group)
