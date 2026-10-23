import frappe

ESKI_BOLIMLAR = (
	"Eko Carier", "Диспетчер", "Продажа карьер", "Касса карьер", "Приход", "Приход ОС", "Инвентаризация",
	"Начисление карьер", "Оборотка Контрагентов", "Акт сверка", "Баланс", "P&L", "Cash Flow", "Отчет", "ДДС",
	"Постав Клиент", "P&L Разбитый", "Баланс бпр", "Кардорликлар", "БД контрагент", "Постав Клиент Факт",
	"ПР Срав.", "Контрагент отчет нев", "Материальный отчет",
)


def execute():
	"""Bitta «Eko Carier» workspace va 23 ta bo'lim sidebar'i o'rniga lavozim bo'yicha workspace'lar
	(Operator, Kassir, Omborchi, Menejer) - eskilari bazadan o'chiriladi."""
	for name in ESKI_BOLIMLAR:
		for doctype in ("Desktop Icon", "Workspace Sidebar"):
			if frappe.db.get_value(doctype, name, "app") == "carieer":
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
	if frappe.db.exists("Workspace", "Eko Carier"):
		frappe.delete_doc("Workspace", "Eko Carier", ignore_permissions=True, force=True)

	frappe.cache.delete_value("desktop_icons")
	frappe.cache.delete_value("bootinfo")
