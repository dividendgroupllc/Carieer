# Beton zavod xodimlari endi alohida rollarda (Beton Operator / Kassir / Menejer). Avval ularga karer rollari
# (Karer Menejer ...) berilgan edi - shu sababli karer sahifalari ham ko'rinardi. Rollar almashtiriladi.

import frappe

from carieer.install import BETON_ROLES, KARER_ROLES, make_roles


def execute():
	make_roles()
	almashtirish = dict(zip(KARER_ROLES, BETON_ROLES, strict=True))
	users = frappe.get_all("Has Role", {"parenttype": "User", "role": "Beton zavod xodimi"}, pluck="parent")
	for user in set(users):
		roles = set(frappe.get_all("Has Role", {"parenttype": "User", "parent": user}, pluck="role"))
		if "Karer xodimi" in roles:
			continue  # ikkala zavod xodimi - tegilmaydi
		for karer, beton in almashtirish.items():
			if karer in roles:
				frappe.db.set_value("Has Role", {"parenttype": "User", "parent": user, "role": karer}, "role", beton)
		frappe.clear_cache(user=user)
