"""O'rnatish va sozlash.

after_install / after_migrate avtomatik:
  - Vehicle ga custom fieldlar (texnika turi, GPS IMEI)
  - Karer rollari uchun standart hujjatlarga (Sales Invoice, Payment Entry ...) ruxsatlar

Qo'lda (bir marta), asosiy ma'lumotlarni yaratish:
  bench --site SITE execute carieer.install.setup_firma --kwargs "{'company': 'Carieer'}"
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

ROLES = ("Karer Operator", "Karer Kassir", "Karer Menejer")


def after_install():
	after_migrate()


def after_migrate():
	make_roles()
	make_custom_fields()
	make_standard_permissions()
	hide_item_fields()
	make_module_profile()


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
	for role in ROLES:
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
		"Customer": ["read", "write", "create"],
		"Item": ["read"],
		"Warehouse": ["read"],
		"Vehicle": ["read"],
		"BOM": ["read"],
		"Mode of Payment": ["read"],
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
		"Mode of Payment": ["read"],
		"Account": ["read"],
		"GL Entry": ["read", "report"],
		"Stock Ledger Entry": ["read", "report"],
	},
}


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

	- Omborlar: Karer ombori, Qazib olingan, Beton xomashyo, Beton ombori, Yoqilg'i ombori
	- Kassa hisoblari: Kassa UZS (+ Kassa USD)
	- To'lov turlari: Naqd UZS, Naqd USD, Plastik, Bank o'tkazma (hisoblari bilan)
	- UOM Tonne va Kg
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

	mops = [
		(f"Naqd {currency}", "Cash", kassa_uzs),
		("Plastik", "Bank", bank_acc or kassa_uzs),
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

	# UZS debitor hisobi bilan USD da ham sotish mumkin bo'lsin (Karer Sotuv valyutasi UZS/USD)
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
def setup_tovar(item_code: str, item_group: str = "Products", stock_uom: str = "Kg", tonne: bool = True,
				is_sales_item: bool = True):
	"""Karer tovari yaratadi (bo'lsa, UOM konversiyasini qo'shadi). 1 Tonne = 1000 Kg."""
	frappe.only_for(("System Manager", "Karer Menejer"))
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
				"is_stock_item": 1,
				"is_sales_item": 1 if is_sales_item else 0,
				"include_item_in_manufacturing": 1,
			}
		)
	if tonne and stock_uom == "Kg" and not any(u.uom == "Tonne" for u in item.uoms):
		item.append("uoms", {"uom": "Tonne", "conversion_factor": 1000})
	item.save(ignore_permissions=True)
	return item.name
