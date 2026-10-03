"""O'rnatish va sozlash.

after_install / after_migrate avtomatik:
  - Vehicle ga custom fieldlar (texnika turi, GPS IMEI)
  - Karer rollari uchun standart hujjatlarga (Sales Invoice, Payment Entry ...) ruxsatlar

Qo'lda (bir marta), asosiy ma'lumotlarni yaratish:
  bench --site SITE execute carieer.install.setup_firma --kwargs "{'company': 'Carieer'}"
    -> omborlar, kassalar, to'lov turlari, xarajat moddalari (Google Sheets "Диспетчер" dagi kategoriyalar)

"Эко Карьер" jadvalidagi tovarlar, tovar guruhlari va kontragent guruhlarini ham yaratish:
  bench --site SITE execute carieer.install.setup_eko_karer --kwargs "{'company': 'Carieer'}"

Sotuv posti xodimi (ikkala firma nomidan sotadi):
  bench --site SITE execute carieer.install.setup_post_user --kwargs "{'email': 'post@karer.uz', 'full_name': 'Post Operator', 'password': '...'}"

Qo'shimcha kassa (jadvaldagi "Наличные2", "Биржа счёт" kabi):
  bench --site SITE execute carieer.install.setup_kassa --kwargs "{'company': 'Carieer', 'kassa': 'Наличные2'}"
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

KARER_ROLES = ("Karer Operator", "Karer Kassir", "Karer Menejer")
# Beton zavod xodimlari alohida rollarda: karer hujjatlari (Qazib Olish, Karer Sozlamalari, Karer workspace)
# ularga umuman ko'rinmaydi, Beton Ishlab Chiqarish esa karer xodimlariga ko'rinmaydi.
BETON_ROLES = ("Beton Operator", "Beton Kassir", "Beton Menejer")
ROLES = KARER_ROLES + BETON_ROLES
# Firma rollari: qaysi workspace ko'rinishini belgilaydi (ma'lumot esa User Permission -> Company bilan
# faqat o'z firmasiniki bo'ladi)
FIRMA_ROLES = ("Karer xodimi", "Beton zavod xodimi")
# lavozim roli -> firma roli
ROLE_FIRMA = {**{r: "Karer xodimi" for r in KARER_ROLES}, **{r: "Beton zavod xodimi" for r in BETON_ROLES}}


def after_install():
	after_migrate()


def after_migrate():
	make_roles()
	make_custom_fields()
	make_standard_permissions()
	hide_item_fields()
	make_module_profile()
	set_uzs_symbol()


def set_uzs_symbol():
	"""Jadvallarda 'UZS' raqam ustiga chiqib qolmasligi uchun: 1 000 so'm ko'rinishi."""
	if frappe.db.exists("Currency", "UZS"):
		frappe.db.set_value("Currency", "UZS", {"symbol": "so'm", "symbol_on_right": 1})


# Item formasida karer uchun keraksiz maydonlar yashiriladi (Property Setter, hamma userlar uchun)
ITEM_HIDDEN_FIELDS = [
	"variant_of", "allow_alternative_item", "is_fixed_asset", "asset_category", "asset_naming_series",
	"auto_create_assets", "is_grouped_asset", "brand", "sb_barcodes", "barcodes",
	"shelf_life_in_days", "end_of_life", "warranty_period", "weight_per_unit", "weight_uom",
	"serial_nos_and_batches", "variants_section", "item_defaults", "is_customer_provided_item",
	"supplier_details", "delivered_by_supplier", "supplier_items", "foreign_trade_details",
	"customer_details", "customer_items", "max_discount", "grant_commission",
	"enable_deferred_revenue", "no_of_months", "enable_deferred_expense", "no_of_months_exp",
	"deferred_accounting_section", "item_tax_section_break", "taxes", "quality_tab",
	"inspection_required_before_purchase", "inspection_required_before_delivery", "quality_inspection_template",
	"default_item_manufacturer", "default_manufacturer_part_no", "is_sub_contracted_item",
	"purchase_tax_withholding_category", "sales_tax_withholding_category",
	"over_delivery_receipt_allowance", "over_billing_allowance", "production_capacity",
	# develop (v17) dagi yangi maydonlar
	"has_variants", "company_restrictions_section", "restrict_to_companies", "allowed_companies", "accounting",
	"reorder_section", "reorder_levels", "default_material_request_type",
	"has_batch_no", "create_new_batch", "batch_number_series", "has_expiry_date", "retain_sample", "sample_quantity",
	"has_serial_no", "serial_no_series", "use_serial_no_wise_valuation",
]


def hide_item_fields():
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	meta = frappe.get_meta("Item")
	for fieldname in ITEM_HIDDEN_FIELDS:
		if meta.get_field(fieldname):
			make_property_setter("Item", fieldname, "hidden", 1, "Check", validate_fields_for_doctype=False)


def make_module_profile():
	"""'Karer xodim' modul profili: faqat Carieer moduli ko'rinadi (boshqa ERPNext bo'limlari yashirin)."""
	name = "Karer xodim"
	doc = frappe.get_doc("Module Profile", name) if frappe.db.exists("Module Profile", name) else frappe.new_doc("Module Profile")
	doc.module_profile_name = name
	doc.set("block_modules", [])
	for module in frappe.get_all("Module Def", pluck="name"):
		if module != "Carieer":
			doc.append("block_modules", {"module": module})
	doc.save(ignore_permissions=True)


def make_roles():
	for role in ROLES + FIRMA_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def make_custom_fields():
	create_custom_fields(
		{
			"Vehicle": [
				{
					"fieldname": "karer_section",
					"fieldtype": "Section Break",
					"label": "Karer: texnika va GPS",
					"insert_after": "employee",
				},
				{
					"fieldname": "texnika_turi",
					"fieldtype": "Select",
					"label": "Texnika turi",
					"options": "\nYuk mashina (samosval)\nBetonovoz\nEkskavator\nBuldozer\nPogruzchik\nYengil mashina\nBoshqa",
					"insert_after": "karer_section",
					"in_list_view": 1,
					"in_standard_filter": 1,
				},
				{
					"fieldname": "karer_cb",
					"fieldtype": "Column Break",
					"insert_after": "texnika_turi",
				},
				{
					"fieldname": "gps_imei",
					"fieldtype": "Data",
					"label": "GPS qurilma IMEI",
					"insert_after": "karer_cb",
					"unique": 1,
					"search_index": 1,
				},
			]
		},
		update=True,
	)


# Karer rollari o'z hujjatlari orqali avtomatik yaratiladigan standart hujjatlarni ko'ra olishi va
# to'lovni kassir qabul qila olishi uchun kerakli minimal ruxsatlar.
STANDARD_PERMS = {
	"Karer Operator": {
		"Sales Invoice": ["read"],
		# postda to'lov darhol qabul qilinsa Payment Entry avtomatik yaratiladi
		"Payment Entry": ["read", "create", "submit"],
		"Account": ["read"],
		"Stock Entry": ["read"],
		"Stock Ledger Entry": ["read", "report"],  # Material Hisobot (ombor qoldig'i)
		"Customer": ["read", "write", "create"],
		"Item": ["read"],
		"Warehouse": ["read"],
		"Vehicle": ["read"],
		"BOM": ["read"],
		"Mode of Payment": ["read"],
		# Yoqilgi Hisobi: haydovchi va zapravka (link maydonlari uchun faqat tanlash)
		"Employee": ["select"],
		"Supplier": ["select"],
	},
	"Karer Kassir": {
		"Sales Invoice": ["read"],
		"Payment Entry": ["read", "write", "create", "submit", "cancel"],
		"Customer": ["read", "write", "create"],
		"Item": ["read"],
		"Warehouse": ["read"],
		"Mode of Payment": ["read"],
		"Account": ["read"],
		"GL Entry": ["read", "report"],  # DDS hisoboti uchun
		"Vehicle": ["select"],  # Sotuv.vehicle
		# Kassa / Начисление: kontragentlar, xarajat markazi va yaratilgan Journal Entry
		"Supplier": ["select"],
		"Employee": ["select"],
		"Shareholder": ["select"],
		"Cost Center": ["select"],
		"Journal Entry": ["read"],
		"Company": ["read"],
	},
	"Karer Menejer": {
		"Sales Invoice": ["read", "write", "create", "submit", "cancel"],
		"Purchase Invoice": ["read", "write", "create", "submit", "cancel"],
		"Payment Entry": ["read", "write", "create", "submit", "cancel"],
		"Stock Entry": ["read", "write", "create", "submit", "cancel"],
		"Customer": ["read", "write", "create"],
		"Supplier": ["read", "write", "create"],
		"Item": ["read", "write", "create"],
		"BOM": ["read", "write", "create", "submit"],
		"Warehouse": ["read"],
		"Vehicle": ["read", "write", "create"],
		"Employee": ["select"],
		"Price List": ["read"],  # Karer Sozlamalari.firmalararo_narx_varaqasi
		# Xarid (kirim): sotib olingan tovar omborga Purchase Receipt bilan kiradi
		"Purchase Receipt": ["read", "write", "create", "submit", "cancel"],
		"Stock Reconciliation": ["read", "write", "create", "submit", "cancel"],
		"Shareholder": ["select"],
		"Cost Center": ["select"],
		"Journal Entry": ["read"],
		"Currency Exchange": ["read", "write", "create"],
		"Company": ["read"],
		"Mode of Payment": ["read"],
		"Account": ["read"],
		"GL Entry": ["read", "report"],
		"Stock Ledger Entry": ["read", "report"],
	},
}
# Beton rollari karer rollari bilan bir xil standart ruxsatlarga ega (ma'lumot User Permission bilan ajratilgan)
STANDARD_PERMS.update({beton: STANDARD_PERMS[karer] for karer, beton in zip(KARER_ROLES, BETON_ROLES, strict=True)})


def make_standard_permissions():
	from frappe.permissions import add_permission, update_permission_property

	for role, doctypes in STANDARD_PERMS.items():
		for doctype, rights in doctypes.items():
			if not frappe.db.exists("DocType", doctype):
				continue
			if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}):
				add_permission(doctype, role, 0)
			for right in rights:
				update_permission_property(doctype, role, 0, right, 1, validate=False)


# ---------------------------------------------------------------------------------------------
@frappe.whitelist()
def setup_firma(company: str, usd_kassa: bool = True):
	"""Bitta firma uchun karer asosiy ma'lumotlarini yaratadi (qayta ishga tushirsa ham xavfsiz).

	- Omborlar: Karer ombori (sotuv va qazib olingan tovar), Beton xomashyo, Beton ombori, Yoqilgi ombori
	- Kassa hisoblari: Kassa UZS (+ Kassa USD), bank hisob raqami (Р/С), plastik karta hisobi (Карта)
	- To'lov turlari: Naqd UZS, Naqd USD, Plastik, Bank o'tkazma (har biri o'z hisobi bilan)
	- UOM: Tonne, Kg, Litre, Cubic Meter
	- Xarajat/daromad moddalari va Kassa Kategoriyalar (Google Sheets "Диспетчер" bo'yicha)
	- Karer Sozlamalari da shu firma qatori
	"""
	frappe.only_for(("System Manager", "Karer Menejer"))
	abbr = frappe.get_cached_value("Company", company, "abbr")
	currency = frappe.get_cached_value("Company", company, "default_currency")
	if not abbr:
		frappe.throw(_("Firma topilmadi: {0}").format(company))

	parent_wh = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1}, "name", order_by="lft asc")
	wh = {}
	for key, name in (
		("sotuv_ombori", "Karer ombori"),
		("qazish_ombori", "Karer ombori"),
		("beton_xomashyo_ombori", "Beton xomashyo"),
		("beton_ombori", "Beton ombori"),
		("yoqilgi_ombori", "Yoqilgi ombori"),
	):
		full = f"{name} - {abbr}"
		if not frappe.db.exists("Warehouse", full):
			frappe.get_doc(
				{"doctype": "Warehouse", "warehouse_name": name, "company": company, "parent_warehouse": parent_wh}
			).insert(ignore_permissions=True)
		wh[key] = full

	cash_parent = frappe.db.get_value(
		"Account", {"company": company, "account_type": "Cash", "is_group": 1}, "name"
	) or frappe.db.get_value("Account", {"company": company, "account_name": "Cash In Hand", "is_group": 1}, "name")
	if not cash_parent:
		frappe.throw(_("{0} da Cash guruh hisobi topilmadi").format(company))

	def ensure_account(account_name, account_currency, account_type="Cash"):
		name = frappe.db.get_value("Account", {"company": company, "account_name": account_name}, "name")
		if name:
			return name
		acc = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": account_name,
				"company": company,
				"parent_account": cash_parent,
				"account_type": account_type,
				"account_currency": account_currency,
			}
		).insert(ignore_permissions=True)
		return acc.name

	kassa_uzs = ensure_account(f"Kassa {currency}", currency)
	kassa_usd = ensure_account("Kassa USD", "USD") if (usd_kassa and currency != "USD") else None

	bank_parent = frappe.db.get_value("Account", {"company": company, "account_type": "Bank", "is_group": 1}, "name")
	bank_acc = frappe.db.get_value("Account", {"company": company, "account_type": "Bank", "is_group": 0}, "name")
	if not bank_acc and bank_parent:
		bank_acc = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": "Bank hisob raqami",
				"company": company,
				"parent_account": bank_parent,
				"account_type": "Bank",
				"account_currency": currency,
			}
		).insert(ignore_permissions=True).name

	# Jadvalda "Карта" alohida hisob (Р/С bilan aralashmasin): plastik tushumlari uchun alohida bank hisobi
	karta_acc = frappe.db.get_value("Account", {"company": company, "account_name": "Plastik karta"}, "name")
	if not karta_acc and bank_parent:
		karta_acc = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": "Plastik karta",
				"company": company,
				"parent_account": bank_parent,
				"account_type": "Bank",
				"account_currency": currency,
			}
		).insert(ignore_permissions=True).name

	mops = [
		(f"Naqd {currency}", "Cash", kassa_uzs),
		("Plastik", "Bank", karta_acc or bank_acc or kassa_uzs),
		("Bank o'tkazma", "Bank", bank_acc or kassa_uzs),
	]
	if kassa_usd:
		mops.append(("Naqd USD", "Cash", kassa_usd))
	for mop_name, mop_type, account in mops:
		if not account:
			continue
		if frappe.db.exists("Mode of Payment", mop_name):
			mop = frappe.get_doc("Mode of Payment", mop_name)
		else:
			mop = frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": mop_name, "type": mop_type, "enabled": 1})
		if not any(a.company == company for a in mop.accounts):
			mop.append("accounts", {"company": company, "default_account": account})
		mop.save(ignore_permissions=True)

	for uom, whole in (("Tonne", 0), ("Kg", 0), ("Litre", 0), ("Cubic Meter", 0)):
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": whole}).insert(ignore_permissions=True)

	make_kategoriyalar()
	make_moddalar(company)

	# UZS debitor hisobi bilan USD da ham sotish mumkin bo'lsin (Sotuv valyutasi UZS/USD)
	frappe.db.set_single_value("Accounts Settings", "allow_multi_currency_invoices_against_single_party_account", 1)

	settings = frappe.get_single("Karer Sozlamalari")
	row = next((r for r in settings.firmalar if r.company == company), None) or settings.append("firmalar", {"company": company})
	for k, v in wh.items():
		if not row.get(k):
			row.set(k, v)
	if not row.mode_of_payment:
		row.mode_of_payment = f"Naqd {currency}"
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	return {"warehouses": wh, "kassa": [kassa_uzs, kassa_usd], "mode_of_payment": [m[0] for m in mops]}


@frappe.whitelist()
def setup_tovar(item_code: str, item_group: str = "Products", stock_uom: str = "Cubic Meter", tonne: bool = True,
				is_sales_item: bool = True, is_stock_item: bool = True):
	"""Karer tovari yaratadi. Jadvalda ("Диспетчер") klines, sheben, qum va beton KUBda yuritiladi, shuning uchun
	standart birlik Cubic Meter. stock_uom="Kg" berilsa Tonne konversiyasi ham qo'shiladi (1 Tonne = 1000 Kg)."""
	frappe.only_for(("System Manager", "Karer Menejer"))
	if not frappe.db.exists("Item Group", item_group):
		item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name", order_by="lft asc")
	if frappe.db.exists("Item", item_code):
		item = frappe.get_doc("Item", item_code)
	else:
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": item_group,
				"stock_uom": stock_uom,
				"is_stock_item": 1 if is_stock_item else 0,
				"is_sales_item": 1 if is_sales_item else 0,
				"include_item_in_manufacturing": 1,
			}
		)
	if tonne and stock_uom == "Kg" and not any(u.uom == "Tonne" for u in item.uoms):
		item.append("uoms", {"uom": "Tonne", "conversion_factor": 1000})
	item.save(ignore_permissions=True)
	return item.name


# ---------------------------------------------------------------------------------------------
# Google Sheets "Эко Карьер" -> "Диспетчер" / "P&L Разбитый": xarajat kategoriyalari 3 darajali.
#   Категория 1 типа -> Категория 2 типа -> kategoriya (modda)
# Hisoblar rejasida xuddi shu daraxt yaratiladi, shunda ERPNext'ning standart "Profit and Loss Statement"
# hisoboti jadvaldagi "P&L Разбитый" ko'rinishida chiqadi, DDS esa kategoriyalar kesimida.
# taqsimot: jadvaldagi "Произв" (ishlab chiqarish tan narxiga) / "Прибыль" (foydadan) / "На ОС" (asosiy vositaga).
# (kategoriya, 1-tur, 2-tur, taqsimot). "*" bilan belgilanganlari jadvalning "P&L Разбитый" varag'ida guruhlanmagan
# (faqat "Диспетчер" / "Cash Flow" da bor) - guruhi mazmuniga qarab qo'yildi, buxgalter bilan tekshirib oling.
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
	("Хоз.расход", ADM, "Прочие расходы", "Произв"),  # *
	("Документация", ADM, "Административные услуги", "Прибыль"),
	("Геология услуга", ADM, "Административные услуги", "Прибыль"),
	("Экология услуга", ADM, "Административные услуги", "Прибыль"),
	("Услуги GPS", ADM, "Административные услуги", "Прибыль"),
	("Камера установка", ADM, "Административные услуги", "Прибыль"),  # *
	("Молларга йем", INV, "Прочие продовольственные расходы", "Прибыль"),
	("Материалы и Строительство", INV, "Расходы на О/С", "На ОС"),
	("Бетон завод кредит", INV, "Расходы на О/С", "На ОС"),
	("Капитальный ремонт/стройка", INV, "Расходы на О/С", "На ОС"),  # *
	("Аренда цеха", OPR, "Аренда и Лизинг", "Произв"),
	("Аренда офиса", OPR, "Аренда и Лизинг", "Прибыль"),
	("Аренда Бетоно Миксер", OPR, "Аренда и Лизинг", "Произв"),
	("Аренда поляк", OPR, "Аренда и Лизинг", "Произв"),
	("Прочие произв расх", PRO, "Нематериальные производственные расходы", "Произв"),
	("Зарплата Производства", PRO, "Нематериальные производственные расходы", "Произв"),
	("Коммуналка", PRO, "Нематериальные производственные расходы", "Произв"),
	("Экскаватор услуга", PRO, "Нематериальные производственные расходы", "Произв"),  # *
	("Топливо и ГСМ", PRO, "Топливо и Газ", "Произв"),
	("Кислород", PRO, "Топливо и Газ", "Произв"),
	("Пропан", PRO, "Топливо и Газ", "Произв"),  # *
	("Питание", PRO, "Ремонт и Обслуживание", "Произв"),
	("Ремонт техники", PRO, "Ремонт и Обслуживание", "Произв"),
	("Запчасти техники", PRO, "Ремонт и Обслуживание", "Произв"),
	("Масло для техники", PRO, "Ремонт и Обслуживание", "Произв"),
	("Погрузчик", PRO, "Ремонт и Обслуживание", "Произв"),
	("Масло для завода", PRO, "Ремонт и Обслуживание", "Произв"),
	("Запчасти завода", PRO, "Ремонт и Обслуживание", "Произв"),
	("Ремонт завода", PRO, "Ремонт и Обслуживание", "Произв"),
	("Электрик", PRO, "Ремонт и Обслуживание", "Произв"),  # *
	("Кран услуга", PRO, "Логистика и Транспорт", "Произв"),
	("Доставка", PRO, "Логистика и Транспорт", "Прибыль"),
	("Миксер доставка", PRO, "Логистика и Транспорт", "Произв"),
	("Самосвал услуга", PRO, "Логистика и Транспорт", "Произв"),
	("Дорожные расходы", PRO, "Логистика и Транспорт", "Произв"),  # *
	("Хова транспортировка", PRO, "Логистика и Транспорт", "Произв"),  # *
	("Коммиссия банка", FIN, "Штрафы, Налоги, Коммисионные", "Прибыль"),
	("Налог", FIN, "Штрафы, Налоги, Коммисионные", "Прибыль"),
	("Штраф", FIN, "Штрафы, Налоги, Коммисионные", "Прибыль"),  # *
	("Клик услуга", FIN, "Штрафы, Налоги, Коммисионные", "Прибыль"),  # *
	("Электросеть демонтаж", FIN, "Штрафы, Налоги, Коммисионные", "Произв"),
	("Откат", FIN, "Финансовые операции", "Прибыль"),
	("Оборудования", FIN, "Финансовые операции", "На ОС"),
	("Брокер", FIN, "Финансовые операции", "Прибыль"),
	("Обнал", FIN, "Финансовые операции", "Прибыль"),  # *
	("Финансовая услуга", FIN, "Финансовые операции", "Прибыль"),  # *
]
# Daromad moddalari: (kategoriya, hisob nomi). Jadval P&L: "Выручка от реализации услуг", "Прочие доходы"
DAROMAD_KATEGORIYALARI = [
	("Прочие доходы", "Прочие доходы"),
]
XIZMAT_DAROMAD_HISOBI = "Выручка от реализации услуг"


def make_kategoriyalar():
	"""Kassa Kategoriya yozuvlarini yaratadi (bor bo'lsa faqat bo'sh guruh maydonlarini to'ldiradi)."""
	rows = [
		{"kategoriya": k, "turi": "Chiqim", "guruh_1": g1, "guruh_2": g2, "taqsimot": t}
		for k, g1, g2, t in XARAJAT_KATEGORIYALARI
	] + [{"kategoriya": k, "turi": "Kirim", "hisob_nomi": h} for k, h in DAROMAD_KATEGORIYALARI]
	for row in rows:
		name = frappe.db.exists("Kassa Kategoriya", row["kategoriya"])
		if not name:
			frappe.get_doc({"doctype": "Kassa Kategoriya", **row}).insert(ignore_permissions=True)
			continue
		doc = frappe.get_doc("Kassa Kategoriya", name)
		changed = False
		for field in ("guruh_1", "guruh_2", "taqsimot", "hisob_nomi"):
			if row.get(field) and not doc.get(field):
				doc.set(field, row[field])
				changed = True
		if changed:
			doc.save(ignore_permissions=True)


def make_moddalar(company: str):
	"""Hisoblar rejasida jadvaldagi xarajat daraxtini (1-tur -> 2-tur -> modda) va daromad moddalarini yaratadi.
	Shu nomli hisob oldindan bo'lsa tegilmaydi (qo'lda yaratilgan hisoblar joyida qoladi)."""

	def find(account_name, is_group=None):
		filters = {"company": company, "account_name": account_name}
		if is_group is not None:
			filters["is_group"] = is_group
		return frappe.db.get_value("Account", filters, "name")

	def root(root_type, preferred):
		"""Standart hisoblar rejasida "Indirect Expenses"/"Indirect Income", bo'lmasa shu turdagi ildiz guruh."""
		return (
			find(preferred, 1)
			or frappe.db.get_value(
				"Account",
				{"company": company, "root_type": root_type, "is_group": 1, "parent_account": ["is", "not set"]},
				"name",
			)
			or frappe.db.get_value(
				"Account", {"company": company, "root_type": root_type, "is_group": 1}, "name", order_by="lft asc"
			)
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
		"""Guruh hisob. Shu nomli oddiy (guruh bo'lmagan) hisob bo'lsa - uning ostiga hisob ochib bo'lmaydi,
		shuning uchun yuqoridagi guruh qaytariladi."""
		name = ensure(account_name, parent_account, root_type, is_group=1)
		return name if frappe.db.get_value("Account", name, "is_group") else parent_account

	expense_root = root("Expense", "Indirect Expenses")
	if expense_root:
		for kategoriya, guruh_1, guruh_2, _taqsimot in XARAJAT_KATEGORIYALARI:
			parent = group(guruh_2, group(guruh_1, expense_root, "Expense"), "Expense")
			ensure(kategoriya, parent, "Expense")

	income_root = root("Income", "Indirect Income")
	if income_root:
		for account_name in [XIZMAT_DAROMAD_HISOBI] + [h for _k, h in DAROMAD_KATEGORIYALARI]:
			ensure(account_name, income_root, "Income")


@frappe.whitelist()
def setup_kassa(company: str, kassa: str, currency: str | None = None, bank: bool = False):
	"""Qo'shimcha kassa: jadvaldagi "Наличные2", "Наличка-3", "Биржа счёт", "Дивиденд-счёт" kabi.
	Shu nomli hisob (Cash yoki Bank) va shu nomli to'lov turi (Mode of Payment) yaratiladi."""
	frappe.only_for(("System Manager", "Karer Menejer"))
	currency = currency or frappe.get_cached_value("Company", company, "default_currency")
	account_type = "Bank" if bank else "Cash"
	account = frappe.db.get_value("Account", {"company": company, "account_name": kassa}, "name")
	if not account:
		parent = frappe.db.get_value(
			"Account", {"company": company, "account_type": account_type, "is_group": 1}, "name", order_by="lft asc"
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
		mop = frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": kassa, "type": account_type, "enabled": 1})
	if not any(a.company == company for a in mop.accounts):
		mop.append("accounts", {"company": company, "default_account": account})
	mop.save(ignore_permissions=True)
	return {"mode_of_payment": mop.name, "account": account}


# ---------------------------------------------------------------------------------------------
# Google Sheets "Диспетчер": tovarlar (nomi, ombor birligi, turi). Услуга ombor tovari emas.
TOVAR_GURUHLARI = ["Сырьё", "Полуфабрикат", "Готовый продукт", "Расходник", "Услуга"]
EKO_KARER_TOVARLARI = [
	("Клинец", "Cubic Meter", "Полуфабрикат"),
	("Шебень", "Cubic Meter", "Полуфабрикат"),
	("Қум", "Cubic Meter", "Полуфабрикат"),
	("Тош", "Cubic Meter", "Готовый продукт"),
	("Цемент", "Tonne", "Полуфабрикат"),
	("Бетон М100", "Cubic Meter", "Готовый продукт"),
	("Бетон М150", "Cubic Meter", "Готовый продукт"),
	("Бетон М200", "Cubic Meter", "Готовый продукт"),
	("Бетон М250", "Cubic Meter", "Готовый продукт"),
	("Бетон М300", "Cubic Meter", "Готовый продукт"),
	("Бетон М350", "Cubic Meter", "Готовый продукт"),
	("Бетон М400", "Cubic Meter", "Готовый продукт"),
	("Шлакоблок", "Nos", "Готовый продукт"),
	("Сув", "Litre", "Сырьё"),
	("Металл", "Nos", "Сырьё"),
	("Хим.добавка", "Kg", "Сырьё"),
	("Антимороз", "Kg", "Сырьё"),
	("Солярка", "Litre", "Расходник"),
	("Услуга", "Nos", "Услуга"),  # "Приход" varag'idagi xizmatlar (ombor tovari emas)
]
# Jadvaldagi "Тип Контрагента": Клиент -> Customer, Поставщик -> Supplier, Сотрудник -> Employee.
# "Прочие лица" va "Налог" uchun alohida hujjat turi yo'q - ular Supplier bo'lib, shu guruhlarga qo'yiladi.
KONTRAGENT_GURUHLARI = ["Прочие лица", "Налог"]


@frappe.whitelist()
def setup_eko_karer(company: str):
	""""Эко Карьер" jadvalidagi asosiy ma'lumotlar: setup_firma + tovar guruhlari, tovarlar, kontragent guruhlari.
	Qayta ishga tushirsa ham xavfsiz (borlari o'zgartirilmaydi)."""
	frappe.only_for(("System Manager", "Karer Menejer"))
	result = setup_firma(company)

	parent_group = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ["is", "not set"]}, "name")
	for group in TOVAR_GURUHLARI:
		if not frappe.db.exists("Item Group", group):
			frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": group, "parent_item_group": parent_group, "is_group": 0}
			).insert(ignore_permissions=True)

	if not frappe.db.exists("UOM", "Nos"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Nos", "must_be_whole_number": 0}).insert(ignore_permissions=True)
	tovarlar = []
	for item_code, uom, group in EKO_KARER_TOVARLARI:
		if not frappe.db.exists("Item", item_code):
			setup_tovar(
				item_code,
				item_group=group,
				stock_uom=uom,
				tonne=False,
				is_sales_item=group != "Расходник",
				is_stock_item=group != "Услуга",
			)
			tovarlar.append(item_code)

	parent_supplier_group = frappe.db.get_value(
		"Supplier Group", {"is_group": 1, "parent_supplier_group": ["is", "not set"]}, "name"
	)
	for group in KONTRAGENT_GURUHLARI:
		if not frappe.db.exists("Supplier Group", group):
			frappe.get_doc(
				{"doctype": "Supplier Group", "supplier_group_name": group, "parent_supplier_group": parent_supplier_group}
			).insert(ignore_permissions=True)
	frappe.db.commit()
	return {**result, "yangi_tovarlar": tovarlar}


@frappe.whitelist()
def setup_firma_user(
	email: str,
	full_name: str,
	company: str,
	role: str,
	firma_role: str | None = None,
	workspace: str | None = None,
	password: str | None = None,
):
	"""Firma xodimini yaratadi (bor bo'lsa yangilaydi): lavozim roli (Karer/Beton Operator, Kassir, Menejer)
	+ firma roli + faqat shu firma (User Permission) + standart workspace + "Karer xodim" modul profili
	(boshqa ERPNext bo'limlari yashirin). Boshqa firmaning rollari olib tashlanadi."""
	frappe.only_for("System Manager")
	firma_role = firma_role or ROLE_FIRMA.get(role)
	if role not in ROLES or firma_role != ROLE_FIRMA[role]:
		frappe.throw(_("Noto'g'ri rol: {0} / {1}").format(role, firma_role))
	workspace = workspace or ("Beton Zavod" if firma_role == "Beton zavod xodimi" else "Karer")
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
			"module_profile": "Karer xodim",
			"default_workspace": workspace,
		}
	)
	# Faqat bitta lavozim + o'z firmasi roli: masalan beton menejerda "Karer Menejer" qolib ketmasin
	user.set("roles", [d for d in user.roles if d.role not in ROLES + FIRMA_ROLES])
	for r in (role, firma_role):
		user.append("roles", {"role": r})
	if password:
		user.new_password = password
	user.save(ignore_permissions=True)

	# Faqat o'z firmasi: hujjatlar, omborlar, hisoblar, hisobotlar, texnikalar
	for up in frappe.get_all("User Permission", {"user": email, "allow": "Company"}, ["name", "for_value"]):
		if up.for_value != company:
			frappe.delete_doc("User Permission", up.name, ignore_permissions=True)
	if not frappe.db.exists("User Permission", {"user": email, "allow": "Company", "for_value": company}):
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": email,
				"allow": "Company",
				"for_value": company,
				"apply_to_all_doctypes": 1,
				"is_default": 1,
			}
		).insert(ignore_permissions=True)
	return user.name


@frappe.whitelist()
def setup_post_user(email: str, full_name: str, password: str | None = None, default_company: str | None = None):
	"""Sotuv posti xodimi: ikkala firma nomidan sotadi (Sotuv'da Tip = Karer / Beton).
	Karer Operator + Beton Operator rollari, ikkala firmaga User Permission, standart workspace "Sotuv operator".
	Firma rollari (Karer xodimi / Beton zavod xodimi) berilmaydi: post faqat sotuv qiladi, Qazib Olish va
	boshqa bo'limlar unga kerak emas."""
	frappe.only_for("System Manager")
	companies = [
		c
		for c in (
			frappe.db.get_single_value("Karer Sozlamalari", "karer_firma"),
			frappe.db.get_single_value("Karer Sozlamalari", "beton_firma"),
		)
		if c
	]
	if len(companies) < 2:
		frappe.throw(_("Karer Sozlamalari -> Sotuv posti: Karer va Beton firmalarini ko'rsating"))
	default_company = default_company or companies[0]

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
			"module_profile": "Karer xodim",
			"default_workspace": "Sotuv operator",
		}
	)
	user.set("roles", [d for d in user.roles if d.role not in ROLES + FIRMA_ROLES])
	for r in ("Karer Operator", "Beton Operator"):
		user.append("roles", {"role": r})
	if password:
		user.new_password = password
	user.save(ignore_permissions=True)

	for up in frappe.get_all("User Permission", {"user": email, "allow": "Company"}, ["name", "for_value"]):
		if up.for_value not in companies:
			frappe.delete_doc("User Permission", up.name, ignore_permissions=True)
	for company in companies:
		name = frappe.db.get_value("User Permission", {"user": email, "allow": "Company", "for_value": company})
		if name:
			frappe.db.set_value("User Permission", name, "is_default", int(company == default_company))
			continue
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": email,
				"allow": "Company",
				"for_value": company,
				"apply_to_all_doctypes": 1,
				"is_default": int(company == default_company),
			}
		).insert(ignore_permissions=True)
	return user.name
