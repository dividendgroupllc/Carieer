from carieer.install import make_report_roles, make_standard_permissions


def execute():
	"""Yangi «Karer Omborchi» roliga ERPNext hujjatlari va ombor hisobotlari uchun ruxsatlar
	(boshqa rollarning Role Permission Manager'da o'zgartirilgan ruxsatlariga tegilmaydi)."""
	make_standard_permissions(roles=("Karer Omborchi",))
	make_report_roles()
