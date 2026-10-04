"""O'rnatish va boshlang'ich sozlash.

Avtomatik (install-app va har bir migrate'dan keyin) - after_migrate():
  - 6 ta rol: Karer / Beton x Operator / Kassir / Menejer
  - Vehicle'ga maydonlar: texnika turi, GPS IMEI, oxirgi joy (latitude / longitude -> Vehicle «Map» ko'rinishi)
  - Rollar uchun ERPNext hujjatlariga kerakli minimal ruxsatlar
  - «Karer xodim» modul profili, Item formasidagi keraksiz maydonlar yashiriladi

Bir marta, qo'lda (firmalar yaratilgandan keyin):
  bench --site SITE execute carieer.install.setup_karer --kwargs "{'karer_company': 'Eko Karer', 'beton_company': 'Eko Beton'}"
    -> omborlar, kassalar (Наличные, Р/С, Карта ...), Zavod yozuvlari, tovarlar, xizmatlar, birliklar,
       xarajat kategoriyalari va hisoblar rejasidagi moddalar, firmalararo kontragentlar

Xodim qo'shish (rol + faqat o'z firmasi + o'z bo'limi):
  bench --site SITE execute carieer.install.setup_user --kwargs "{'email': 'kassir@karer.uz', 'full_name': 'Ali Valiyev', 'zavod': 'Karer', 'lavozim': 'Kassir', 'password': 'Parol123!'}"
    zavod: Karer | Beton | Ikkalasi (sotuv posti operatori ikkala zavod nomidan sotadi)
    lavozim: Operator | Kassir | Menejer
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from carieer.permissions import ALL_ROLES, BETON_ROLES, BETON_SECTION, KARER_ROLES, KARER_SECTION

MODULE_PROFILE = "Karer xodim"


def after_install():
	after_migrate()


def after_migrate():
	make_roles()
	make_custom_fields()
	make_standard_permissions()
	hide_item_fields()
	make_module_profile()
	set_uzs_symbol()


# ============================================================================ rollar va ruxsatlar
def make_roles():
	for role in ALL_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)


R = ("read",)
RR = ("read", "report")
CRW = ("read", "write", "create", "report")
FULL = ("read", "write", "create", "submit", "cancel", "amend", "report", "print", "export")

# Bizning hujjatlar avtomatik yaratadigan / ishlatadigan ERPNext hujjatlari uchun minimal ruxsatlar (lavozim bo'yicha).
LAVOZIM_PERMS = {
	"Operator": {
		"Customer": CRW,  # postda yangi mijoz qo'shish
		"Item": R,
		"UOM": R,
		"Warehouse": R,
		"Mode of Payment": R,
		"Company": R,
		"Account": R,  # ERPNext Sales Invoice / Payment Entry yaratishda debitor va kassa hisobini tekshiradi
		"Cost Center": R,
		"Vehicle": R,
		"Employee": ("select",),
		"Supplier": ("select",),
		"Sales Invoice": R,
		"Payment Entry": ("read", "create", "submit"),  # postda to'lov qabul qilish (Sotuv -> Оплаты)
		"Stock Entry": R,
		"Stock Ledger Entry": RR,  # Material Hisobot
		"BOM": R,
	},
	"Kassir": {
		"Customer": CRW,
		"Supplier": CRW,
		"Employee": R,
		"Item": R,
		"UOM": R,
		"Warehouse": R,
		"Mode of Payment": R,
		"Company": R,
		"Account": R,
		"Cost Center": R,
		"Vehicle": R,
		"Currency Exchange": CRW,  # kunlik kurs
		"Sales Invoice": RR,
		"Purchase Invoice": RR,
		"Payment Entry": ("read", "create", "submit", "report"),
		"Journal Entry": RR,
		"GL Entry": RR,  # moliyaviy hisobotlar
	},
	"Menejer": {
		"Customer": CRW,
		"Supplier": CRW,
		"Employee": R,
		"Item": CRW,
		"Item Group": R,
		"UOM": R,
		"Warehouse": CRW,
		"Mode of Payment": R,
		"Company": R,
		"Account": R,
		"Cost Center": R,
		"Vehicle": CRW,
		"Currency Exchange": CRW,
		"Price List": R,
		"BOM": ("read", "write", "create", "submit", "cancel", "amend", "report"),
		"Sales Invoice": FULL,
		"Purchase Invoice": FULL,
		"Purchase Receipt": FULL,
		"Payment Entry": FULL,
		"Journal Entry": FULL,
		"Stock Entry": FULL,
		"Stock Reconciliation": FULL,
		"GL Entry": RR,
		"Stock Ledger Entry": RR,
	},
}


def make_standard_permissions():
	from frappe.permissions import add_permission, update_permission_property

	for role in ALL_ROLES:
		lavozim = role.split()[-1]
		for doctype, rights in LAVOZIM_PERMS[lavozim].items():
			if not frappe.db.exists("DocType", doctype):
				continue
			if not frappe.db.exists(
				"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
			):
				add_permission(doctype, role, 0)
			for right in rights:
				update_permission_property(doctype, role, 0, right, 1, validate=False)


def make_module_profile():
	"""«Karer xodim» modul profili: ERPNext'ning boshqa bo'limlari (Selling, Stock, HR ...) xodimga ko'rinmaydi.
	Faqat o'zgarish bo'lsa saqlanadi (Module Profile saqlanganda fon vazifasi barcha userlarni yangilaydi)."""
	blocked = {m for m in frappe.get_all("Module Def", pluck="name") if m != "Carieer"}
	if frappe.db.exists("Module Profile", MODULE_PROFILE):
		doc = frappe.get_doc("Module Profile", MODULE_PROFILE)
		if {d.module for d in doc.block_modules} == blocked:
			return
	else:
		doc = frappe.new_doc("Module Profile")
		doc.module_profile_name = MODULE_PROFILE
	doc.set("block_modules", [{"module": m} for m in sorted(blocked)])
	try:
		doc.save(ignore_permissions=True)
	except frappe.DocumentLockedError:
		# oldingi yangilash hali navbatda - keyingi migrate'da qayta uriniladi
		frappe.clear_last_message()


# ============================================================================ maydonlar
def make_custom_fields():
	create_custom_fields(
		{
			"Vehicle": [
				{
					"fieldname": "karer_section",
					"fieldtype": "Section Break",
					"label": "Texnika va GPS",
					"insert_after": "employee",
				},
				{
					"fieldname": "texnika_turi",
					"fieldtype": "Select",
					"label": "Texnika turi",
					"options": "\nSamosval\nBetonovoz (mikser)\nEkskavator\nBuldozer\nPogruzchik\nKran\nYengil mashina\nBoshqa",
					"insert_after": "karer_section",
					"in_list_view": 1,
					"in_standard_filter": 1,
				},
				{
					"fieldname": "gps_imei",
					"fieldtype": "Data",
					"label": "GPS qurilma IMEI",
					"insert_after": "texnika_turi",
					"unique": 1,
					"search_index": 1,
					"description": "Traccar Client'dagi «Device identifier» yoki trekker IMEI",
				},
				{"fieldname": "karer_cb", "fieldtype": "Column Break", "insert_after": "gps_imei"},
				{
					"fieldname": "gps_vaqt",
					"fieldtype": "Datetime",
					"label": "Oxirgi GPS vaqti",
					"insert_after": "karer_cb",
					"read_only": 1,
					"in_list_view": 1,
				},
				{
					"fieldname": "latitude",
					"fieldtype": "Float",
					"label": "Latitude",
					"precision": "7",
					"insert_after": "gps_vaqt",
					"read_only": 1,
				},
				{
					"fieldname": "longitude",
					"fieldtype": "Float",
					"label": "Longitude",
					"precision": "7",
					"insert_after": "latitude",
					"read_only": 1,
				},
				{
					"fieldname": "gps_tezlik",
					"fieldtype": "Float",
					"label": "Tezlik (km/soat)",
					"insert_after": "longitude",
					"read_only": 1,
				},
			]
		},
		update=True,
	)


# Item formasida karer uchun keraksiz maydonlar yashiriladi (Property Setter)
ITEM_HIDDEN_FIELDS = [
	"variant_of",
	"allow_alternative_item",
	"is_fixed_asset",
	"asset_category",
	"asset_naming_series",
	"auto_create_assets",
	"is_grouped_asset",
	"brand",
	"sb_barcodes",
	"barcodes",
	"shelf_life_in_days",
	"end_of_life",
	"warranty_period",
	"weight_per_unit",
	"weight_uom",
	"serial_nos_and_batches",
	"variants_section",
	"is_customer_provided_item",
	"supplier_details",
	"delivered_by_supplier",
	"supplier_items",
	"foreign_trade_details",
	"customer_details",
	"customer_items",
	"max_discount",
	"grant_commission",
	"enable_deferred_revenue",
	"no_of_months",
	"enable_deferred_expense",
	"no_of_months_exp",
	"deferred_accounting_section",
	"item_tax_section_break",
	"taxes",
	"quality_tab",
	"inspection_required_before_purchase",
	"inspection_required_before_delivery",
	"quality_inspection_template",
	"default_item_manufacturer",
	"default_manufacturer_part_no",
	"is_sub_contracted_item",
	"purchase_tax_withholding_category",
	"sales_tax_withholding_category",
	"over_delivery_receipt_allowance",
	"over_billing_allowance",
	"production_capacity",
	"has_variants",
	"reorder_section",
	"reorder_levels",
	"has_batch_no",
	"create_new_batch",
	"batch_number_series",
	"has_expiry_date",
	"retain_sample",
	"sample_quantity",
	"has_serial_no",
	"serial_no_series",
	"use_serial_no_wise_valuation",
]


def hide_item_fields():
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	meta = frappe.get_meta("Item")
	for fieldname in ITEM_HIDDEN_FIELDS:
		if meta.get_field(fieldname):
			make_property_setter("Item", fieldname, "hidden", 1, "Check", validate_fields_for_doctype=False)


def set_uzs_symbol():
	if frappe.db.exists("Currency", "UZS"):
		frappe.db.set_value("Currency", "UZS", {"symbol": "so'm", "symbol_on_right": 1})


# ============================================================================ boshlang'ich ma'lumotlar
# Google Sheets «Диспетчер»: kassalar (Счета). (nomi, turi, valyuta: None = firma valyutasi)
KASSALAR = [
	("Наличные", "Cash", None),
	("Наличные $", "Cash", "USD"),
	("Наличные2", "Cash", None),
	("Наличка-3", "Cash", None),
	("Р/С", "Bank", None),
	("Карта", "Bank", None),
	("Биржа счёт", "Bank", None),
	("Дивиденд счёт", "Cash", None),
]
BIRLIKLAR = ["Куб", "Тонна", "Литр", "Шт", "Кг"]
TOVAR_GURUHLARI = ["Сырьё", "Полуфабрикат", "Готовый продукт", "ГП неизменный", "Расходник", "Услуга"]
# (nomi, birlik, guruh)
TOVARLAR = [
	("Клинец", "Куб", "Полуфабрикат"),
	("Шебень", "Куб", "Полуфабрикат"),
	("Қум", "Куб", "Полуфабрикат"),
	("Тош", "Куб", "Готовый продукт"),
	("Цемент", "Тонна", "Полуфабрикат"),
	("Бетон М100", "Куб", "Готовый продукт"),
	("Бетон М150", "Куб", "Готовый продукт"),
	("Бетон М200", "Куб", "Готовый продукт"),
	("Бетон М250", "Куб", "Готовый продукт"),
	("Бетон М300", "Куб", "Готовый продукт"),
	("Бетон М350", "Куб", "Готовый продукт"),
	("Бетон М400", "Куб", "Готовый продукт"),
	("Шлакоблок", "Шт", "Готовый продукт"),
	("Сув", "Литр", "Сырьё"),
	("Металл", "Шт", "Сырьё"),
	("Хим.добавка", "Кг", "Сырьё"),
	("Антимороз", "Кг", "Сырьё"),
	("Солярка", "Литр", "Расходник"),
	("Масло", "Литр", "Расходник"),
]
# «Типы Услуг»: ombor tovari bo'lmagan xizmatlar (Sotuv -> Услуги, Приход, Начисление)
XIZMATLAR = [
	"Погрузчик",
	"Доставка",
	"Миксер доставка",
	"Хова транспортировка",
	"Самосвал услуга",
	"Кран услуга",
	"Экскаватор услуга",
	"Аренда Бетоно Миксер",
	"Аренда поляк",
	"Ремонт техники",
	"Миксер шофёр",
	"Геология услуга",
	"Экология услуга",
	"Документация",
	"Услуги GPS",
	"Камера установка",
	"Клик услуга",
	"Финансовая услуга",
	"Услуга",
]
KONTRAGENT_GURUHLARI = ["Прочие лица", "Налог"]

# «Диспетчер» / «P&L Разбитый»: xarajat kategoriyalari 3 darajali: 1-tur -> 2-tur -> modda.
# Hisoblar rejasida xuddi shu daraxt yaratiladi -> P&L va DDS jadvaldagi ko'rinishda chiqadi.
ADM, INV, OPR, PRO, FIN = (
	"Административный расход",
	"Инвестиционные расходы",
	"Операционный расход",
	"Производственный расход",
	"Финансовые расходы",
)
XARAJAT_KATEGORIYALARI = [
	("Зарплата Администрации", ADM, "Заработная плата и бонусы", "Прибыль"),
	("Бонус сотрудникам", ADM, "Прочие расходы", "Прибыль"),
	("Связь и интернет", ADM, "Прочие расходы", "Прибыль"),
	("Почта", ADM, "Прочие расходы", "Прибыль"),
	("Хоз.расход", ADM, "Прочие расходы", "Произв"),
	("Документация", ADM, "Административные услуги", "Прибыль"),
	("Геология услуга", ADM, "Административные услуги", "Прибыль"),
	("Экология услуга", ADM, "Административные услуги", "Прибыль"),
	("Услуги GPS", ADM, "Административные услуги", "Прибыль"),
	("Камера установка", ADM, "Административные услуги", "Прибыль"),
	("Молларга йем", INV, "Прочие продовольственные расходы", "Прибыль"),
	("Материалы и Строительство", INV, "Расходы на О/С", "На ОС"),
	("Бетон завод кредит", INV, "Расходы на О/С", "На ОС"),
	("Капитальный ремонт/стройка", INV, "Расходы на О/С", "На ОС"),
	("Аренда цеха", OPR, "Аренда и Лизинг", "Произв"),
	("Аренда офиса", OPR, "Аренда и Лизинг", "Прибыль"),
	("Аренда Бетоно Миксер", OPR, "Аренда и Лизинг", "Произв"),
	("Аренда поляк", OPR, "Аренда и Лизинг", "Произв"),
	("Прочие произв расх", PRO, "Нематериальные производственные расходы", "Произв"),
	("Зарплата Производства", PRO, "Нематериальные производственные расходы", "Произв"),
	("Коммуналка", PRO, "Нематериальные производственные расходы", "Произв"),
	("Экскаватор услуга", PRO, "Нематериальные производственные расходы", "Произв"),
	("Топливо и ГСМ", PRO, "Топливо и Газ", "Произв"),
	("Кислород", PRO, "Топливо и Газ", "Произв"),
	("Пропан", PRO, "Топливо и Газ", "Произв"),
	("Питание", PRO, "Ремонт и Обслуживание", "Произв"),
	("Ремонт техники", PRO, "Ремонт и Обслуживание", "Произв"),
	("Запчасти техники", PRO, "Ремонт и Обслуживание", "Произв"),
	("Масло для техники", PRO, "Ремонт и Обслуживание", "Произв"),
	("Погрузчик", PRO, "Ремонт и Обслуживание", "Произв"),
	("Масло для завода", PRO, "Ремонт и Обслуживание", "Произв"),
	("Запчасти завода", PRO, "Ремонт и Обслуживание", "Произв"),
	("Ремонт завода", PRO, "Ремонт и Обслуживание", "Произв"),
	("Электрик", PRO, "Ремонт и Обслуживание", "Произв"),
	("Кран услуга", PRO, "Логистика и Транспорт", "Произв"),
	("Доставка", PRO, "Логистика и Транспорт", "Прибыль"),
	("Миксер доставка", PRO, "Логистика и Транспорт", "Произв"),
	("Самосвал услуга", PRO, "Логистика и Транспорт", "Произв"),
	("Дорожные расходы", PRO, "Логистика и Транспорт", "Произв"),
	("Хова транспортировка", PRO, "Логистика и Транспорт", "Произв"),
	("Коммиссия банка", FIN, "Штрафы, Налоги, Коммисионные", "Прибыль"),
	("Налог", FIN, "Штрафы, Налоги, Коммисионные", "Прибыль"),
	("Штраф", FIN, "Штрафы, Налоги, Коммисионные", "Прибыль"),
	("Клик услуга", FIN, "Штрафы, Налоги, Коммисионные", "Прибыль"),
	("Электросеть демонтаж", FIN, "Штрафы, Налоги, Коммисионные", "Произв"),
	("Откат", FIN, "Финансовые операции", "Прибыль"),
	("Оборудования", FIN, "Финансовые операции", "На ОС"),
	("Брокер", FIN, "Финансовые операции", "Прибыль"),
	("Обнал", FIN, "Финансовые операции", "Прибыль"),
	("Финансовая услуга", FIN, "Финансовые операции", "Прибыль"),
]
# Daromad moddalari: (kategoriya, hisob nomi)
DAROMAD_KATEGORIYALARI = [
	("Прочие доходы", "Прочие доходы"),
	("Продажа услуга", "Выручка от реализации услуг"),
]
# Faqat pul oqimi uchun (hisob ochilmaydi, Kassa'da kontragent bilan ishlatiladi)
DDS_KATEGORIYALARI = [
	("Клиент", "Kirim"),
	("Поставщик", "Chiqim"),
	("Сотрудник", "Ikkalasi"),
	("Прочие лица", "Ikkalasi"),
	("Дивиденд", "Chiqim"),
	("Перемещение", "Ikkalasi"),
	("Конвертация", "Ikkalasi"),
	("Займ", "Ikkalasi"),
]


def setup_karer(karer_company: str, beton_company: str | None = None):
	"""Ikkala firma uchun bir martalik sozlash (qayta ishga tushirsa ham xavfsiz - borlari o'zgarmaydi)."""
	frappe.only_for("System Manager")
	companies = [c for c in (karer_company, beton_company) if c]
	for company in companies:
		if not frappe.db.exists("Company", company):
			frappe.throw(
				_("Firma topilmadi: {0}. Avval Setup Wizard yoki Company orqali yarating").format(company)
			)

	make_masters()
	for company in companies:
		setup_company(company)

	make_zavod("Karer", karer_company, asosiy="Karer ombori", xomashyo=None)
	if beton_company:
		make_zavod("Beton", beton_company, asosiy="Beton ombori", xomashyo="Beton xomashyo")
		from carieer.utils import ensure_inter_company_parties

		ensure_inter_company_parties(karer_company, beton_company)
		ensure_inter_company_parties(beton_company, karer_company)
		from carieer.carieer.doctype.sotuv.sotuv import get_inter_company_price_list

		get_inter_company_price_list(frappe.get_cached_value("Company", karer_company, "default_currency"))

	# so'm hisobidagi mijozga dollarda ham sotish / to'lov olish mumkin bo'lsin
	frappe.db.set_single_value(
		"Accounts Settings", "allow_multi_currency_invoices_against_single_party_account", 1
	)
	# Sotuv bekor qilinsa Kassa orqali kiritilgan to'lov o'chmaydi, mijoz avansi bo'lib qoladi
	frappe.db.set_single_value("Accounts Settings", "unlink_payment_on_cancellation_of_invoice", 1)
	frappe.db.commit()
	return {"zavodlar": frappe.get_all("Zavod", fields=["name", "company", "asosiy_ombor", "kassa"])}


def make_masters():
	for uom in BIRLIKLAR:
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc(
				{"doctype": "UOM", "uom_name": uom, "must_be_whole_number": int(uom == "Шт")}
			).insert(ignore_permissions=True)

	root_group = frappe.db.get_value(
		"Item Group", {"is_group": 1, "parent_item_group": ["in", ["", None]]}, "name"
	)
	for group in TOVAR_GURUHLARI:
		if not frappe.db.exists("Item Group", group):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": group,
					"parent_item_group": root_group,
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

	for item_code, uom, group in TOVARLAR:
		make_item(item_code, uom, group, is_stock=1, is_sales=int(group != "Расходник"))
	for name in XIZMATLAR:
		make_item(name, "Шт", "Услуга", is_stock=0, is_sales=1)

	root_supplier_group = frappe.db.get_value(
		"Supplier Group", {"is_group": 1, "parent_supplier_group": ["in", ["", None]]}, "name"
	)
	for group in KONTRAGENT_GURUHLARI:
		if not frappe.db.exists("Supplier Group", group):
			frappe.get_doc(
				{
					"doctype": "Supplier Group",
					"supplier_group_name": group,
					"parent_supplier_group": root_supplier_group,
				}
			).insert(ignore_permissions=True)

	make_kategoriyalar()


def make_item(item_code, uom, group, is_stock, is_sales):
	if frappe.db.exists("Item", item_code):
		return
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_code,
			"item_group": group,
			"stock_uom": uom,
			"is_stock_item": is_stock,
			"is_sales_item": is_sales,
			"is_purchase_item": 1,
			"include_item_in_manufacturing": is_stock,
			"valuation_rate": 0,
		}
	).insert(ignore_permissions=True)


def make_kategoriyalar():
	rows = (
		[
			{"kategoriya": k, "turi": "Chiqim", "guruh_1": g1, "guruh_2": g2, "taqsimot": t}
			for k, g1, g2, t in XARAJAT_KATEGORIYALARI
		]
		+ [{"kategoriya": k, "turi": "Kirim", "hisob_nomi": h} for k, h in DAROMAD_KATEGORIYALARI]
		+ [{"kategoriya": k, "turi": t} for k, t in DDS_KATEGORIYALARI]
	)
	for row in rows:
		if not frappe.db.exists("Kassa Kategoriya", row["kategoriya"]):
			frappe.get_doc({"doctype": "Kassa Kategoriya", **row}).insert(ignore_permissions=True)


def setup_company(company: str):
	"""Omborlar, kassalar (Mode of Payment + hisob) va xarajat / daromad moddalari."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	currency = frappe.get_cached_value("Company", company, "default_currency")
	parent_wh = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 1}, "name", order_by="lft asc"
	)
	for name in ("Karer ombori", "Beton ombori", "Beton xomashyo", "Yoqilgi ombori"):
		if not frappe.db.exists("Warehouse", f"{name} - {abbr}"):
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": name,
					"company": company,
					"parent_warehouse": parent_wh,
				}
			).insert(ignore_permissions=True)

	for kassa, account_type, kassa_currency in KASSALAR:
		make_kassa(company, kassa, account_type, kassa_currency or currency)

	make_moddalar(company)


def make_kassa(company: str, kassa: str, account_type: str = "Cash", currency: str | None = None):
	"""Kassa = Mode of Payment + shu firmadagi hisob (Cash yoki Bank)."""
	currency = currency or frappe.get_cached_value("Company", company, "default_currency")
	account = frappe.db.get_value(
		"Account", {"company": company, "account_name": kassa, "is_group": 0}, "name"
	)
	if not account:
		parent = frappe.db.get_value(
			"Account",
			{"company": company, "account_type": account_type, "is_group": 1},
			"name",
			order_by="lft asc",
		)
		if not parent:
			frappe.throw(_("{0} da {1} guruh hisobi topilmadi").format(company, account_type))
		account = (
			frappe.get_doc(
				{
					"doctype": "Account",
					"account_name": kassa,
					"company": company,
					"parent_account": parent,
					"account_type": account_type,
					"account_currency": currency,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	if frappe.db.exists("Mode of Payment", kassa):
		mop = frappe.get_doc("Mode of Payment", kassa)
	else:
		mop = frappe.get_doc(
			{"doctype": "Mode of Payment", "mode_of_payment": kassa, "type": account_type, "enabled": 1}
		)
	if not any(a.company == company for a in mop.accounts):
		mop.append("accounts", {"company": company, "default_account": account})
	mop.save(ignore_permissions=True)
	return mop.name


def make_moddalar(company: str):
	"""Hisoblar rejasida jadvaldagi xarajat daraxti (1-tur -> 2-tur -> modda) va daromad moddalari.
	Shu nomli hisob oldindan bo'lsa tegilmaydi."""

	def find(account_name, is_group=None):
		filters = {"company": company, "account_name": account_name}
		if is_group is not None:
			filters["is_group"] = is_group
		return frappe.db.get_value("Account", filters, "name")

	def root(root_type, preferred):
		return find(preferred, 1) or frappe.db.get_value(
			"Account", {"company": company, "root_type": root_type, "is_group": 1}, "name", order_by="lft asc"
		)

	def ensure(account_name, parent_account, root_type, is_group=0):
		name = find(account_name)
		if name:
			return name
		return (
			frappe.get_doc(
				{
					"doctype": "Account",
					"account_name": account_name,
					"company": company,
					"parent_account": parent_account,
					"is_group": is_group,
					"root_type": root_type,
					"report_type": "Profit and Loss",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def group(account_name, parent_account, root_type):
		name = ensure(account_name, parent_account, root_type, is_group=1)
		return name if frappe.db.get_value("Account", name, "is_group") else parent_account

	expense_root = root("Expense", "Indirect Expenses")
	for kategoriya, guruh_1, guruh_2, _taqsimot in XARAJAT_KATEGORIYALARI:
		ensure(kategoriya, group(guruh_2, group(guruh_1, expense_root, "Expense"), "Expense"), "Expense")

	income_root = root("Income", "Indirect Income")
	for _k, account_name in DAROMAD_KATEGORIYALARI:
		ensure(account_name, income_root, "Income")


def make_zavod(zavod: str, company: str, asosiy: str, xomashyo: str | None):
	abbr = frappe.get_cached_value("Company", company, "abbr")
	doc = frappe.get_doc("Zavod", zavod) if frappe.db.exists("Zavod", zavod) else frappe.new_doc("Zavod")
	doc.zavod = zavod
	doc.company = company
	doc.asosiy_ombor = doc.asosiy_ombor or f"{asosiy} - {abbr}"
	if xomashyo:
		doc.xomashyo_ombori = doc.xomashyo_ombori or f"{xomashyo} - {abbr}"
	doc.yoqilgi_ombori = doc.yoqilgi_ombori or f"Yoqilgi ombori - {abbr}"
	doc.kassa = doc.kassa or "Наличные"
	doc.save(ignore_permissions=True)


# ============================================================================ xodimlar
def setup_user(email: str, full_name: str, zavod: str, lavozim: str, password: str | None = None):
	"""Xodim yaratadi / yangilaydi.
	zavod: Karer | Beton | Ikkalasi;  lavozim: Operator | Kassir | Menejer.
	Beriladi: lavozim roli, faqat o'z firmasi (User Permission -> Company va Zavod), o'z bo'limi (default workspace),
	«Karer xodim» modul profili. Boshqa karer/beton rollari olib tashlanadi."""
	frappe.only_for("System Manager")
	if zavod not in ("Karer", "Beton", "Ikkalasi"):
		frappe.throw(_("zavod: Karer, Beton yoki Ikkalasi"))
	if lavozim not in ("Operator", "Kassir", "Menejer"):
		frappe.throw(_("lavozim: Operator, Kassir yoki Menejer"))
	zavodlar = ["Karer", "Beton"] if zavod == "Ikkalasi" else [zavod]
	companies = {}
	for z in zavodlar:
		company = frappe.db.get_value("Zavod", z, "company")
		if not company:
			frappe.throw(_("Zavod '{0}' topilmadi. Avval setup_karer ni ishga tushiring").format(z))
		companies[z] = company

	user = frappe.get_doc("User", email) if frappe.db.exists("User", email) else frappe.new_doc("User")
	if user.is_new():
		user.email = email
		user.send_welcome_email = 0
	first, _sep, last = full_name.partition(" ")
	user.update(
		{
			"first_name": first,
			"last_name": last,
			"enabled": 1,
			"user_type": "System User",
			"module_profile": MODULE_PROFILE,
			"default_workspace": KARER_SECTION if zavodlar[0] == "Karer" else BETON_SECTION,
		}
	)
	user.set("roles", [d for d in user.roles if d.role not in ALL_ROLES])
	for z in zavodlar:
		user.append("roles", {"role": f"{z} {lavozim}"})
	if password:
		user.new_password = password
	user.save(ignore_permissions=True)

	set_user_permissions(email, "Company", list(companies.values()))
	set_user_permissions(email, "Zavod", zavodlar)
	frappe.db.commit()
	return {
		"user": user.name,
		"roles": [f"{z} {lavozim}" for z in zavodlar],
		"companies": list(companies.values()),
	}


def set_user_permissions(user: str, allow: str, values: list[str]):
	"""Faqat shu qiymatlar (birinchisi - standart)."""
	for up in frappe.get_all("User Permission", {"user": user, "allow": allow}, ["name", "for_value"]):
		if up.for_value not in values:
			frappe.delete_doc("User Permission", up.name, ignore_permissions=True)
	for i, value in enumerate(values):
		name = frappe.db.get_value("User Permission", {"user": user, "allow": allow, "for_value": value})
		if name:
			frappe.db.set_value("User Permission", name, "is_default", int(i == 0))
			continue
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": allow,
				"for_value": value,
				"apply_to_all_doctypes": 1,
				"is_default": int(i == 0),
			}
		).insert(ignore_permissions=True)
