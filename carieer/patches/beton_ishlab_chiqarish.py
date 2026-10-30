import frappe

from carieer.install import make_report_roles, make_roles, make_standard_permissions


def execute():
	"""Yangi «Beton Ishlab chiqarish» roli: rolning o'zi, ERPNext hujjatlari (Stock Entry, BOM ...) va ombor
	hisobotlari uchun ruxsatlar (boshqa rollarning Role Permission Manager'da o'zgartirilgan ruxsatlariga tegilmaydi)."""
	make_roles()
	make_standard_permissions(roles=("Beton Ishlab chiqarish",))
	make_report_roles()
	frappe.cache.delete_value("desktop_icons")
	frappe.cache.delete_value("bootinfo")
