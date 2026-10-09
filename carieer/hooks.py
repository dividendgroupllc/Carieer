import os as _os

app_name = "carieer"
app_title = "Carieer"
app_publisher = "ismoil"
app_description = (
	"Karer va beton zavod: sotuv posti, kassa, nachislenie, ombor, texnika va hisobotlar (ERPNext ustida)"
)
app_email = "devpy2869@gmail.com"
app_license = "mit"

# ERPNext (buxgalteriya, ombor) va HRMS (xodimlar) ustida ishlaydi
required_apps = ["erpnext", "hrms"]

# Formalar, ro'yxatlar va hisobotlar Frappe / ERPNext'ning o'z UI'si bilan ishlaydi. Yagona kichik JS:
# bo'lim (Karer / Beton Zavod) ichida ochilgan hisobot va yangi hujjatga shu bo'lim firmasini qo'yadi (build talab qilmaydi).
# Server faylni 12 soat keshlashga ruxsat beradi (max-age=43200): fayl o'zgarsa manzil ham o'zgarsin (?v=...),
# aks holda brauzer eski kodni ishlataveradi. Fayl yangilangandan keyin: bench --site SITE clear-cache
_js = _os.path.join(_os.path.dirname(__file__), "public", "js", "carieer.js")
app_include_js = f"/assets/carieer/js/carieer.js?v={int(_os.path.getmtime(_js))}"
# Bo'limlar (desktop ikonkasi + chap menyu): carieer/desktop_icon, carieer/workspace_sidebar, carieer/carieer/workspace

# Menyuni tozalash: Karer xodimi faqat «Karer», beton xodimi faqat «Beton Zavod» bo'limini ko'radi
boot_session = "carieer.permissions.boot_session"

# O'rnatish / migrate
after_install = "carieer.install.after_install"
after_migrate = "carieer.install.after_migrate"

doc_events = {
	# Tashqaridan (Kassa, Payment Entry) kiritilgan to'lovlar ham Sotuv'dagi qarz va holatni yangilasin
	"Payment Entry": {
		# ichki firmaga to'lov faqat Firmalararo To'lov orqali (ikkala kitobga)
		"validate": "carieer.utils.validate_internal_payment",
		"on_submit": "carieer.carieer.doctype.sotuv.sotuv.on_payment_entry_change",
		"on_cancel": "carieer.carieer.doctype.sotuv.sotuv.on_payment_entry_change",
	},
	# Firmalararo oldi-sotdi faqat Sotuv orqali (ikkala firma kitobiga birdan) - qo'lda kiritilgan hujjat bloklanadi
	"Sales Invoice": {"before_validate": "carieer.utils.validate_inter_company_document"},
	"Delivery Note": {"before_validate": "carieer.utils.validate_inter_company_document"},
	"Purchase Invoice": {"before_validate": "carieer.utils.validate_inter_company_document"},
	"Purchase Receipt": {"before_validate": "carieer.utils.validate_inter_company_document"},
	# GPS IMEI yozilganda eski nuqtalarga ham mashina raqami qo'yiladi
	"Vehicle": {
		"on_update": "carieer.api.sync_vehicle_gps",
	},
	# Karer / Beton roli berilsa - faqat o'z firmasi va zavodi ko'rinadi (User Permission o'zi qo'yiladi)
	"User": {
		"on_update": "carieer.permissions.sync_user_companies",
	},
	# Yangi xarajat / daromad kategoriyasi -> ikkala firmada shu modda hisobi
	"Kassa Kategoriya": {
		"on_update": "carieer.install.make_kategoriya_accounts",
	},
	# Kassa nazorati: har bir kassaning o'z hisobi va to'g'ri valyutasi bo'lsin
	"Mode of Payment": {
		"validate": "carieer.utils.validate_mode_of_payment",
	},
	# Teskari kiritilgan valyuta kursi (UZS -> USD = 11 900) bloklanadi
	"Currency Exchange": {
		"validate": "carieer.utils.validate_currency_exchange",
	},
	# Инвентаризация: karer tovari tan narxi 0 bo'lishi mumkin
	"Stock Reconciliation": {
		"before_validate": "carieer.events.stock_reconciliation_before_validate",
	},
}

# Firmalararo To'lov ikkala firmaga (to'lovchi va oluvchi) ko'rinadi
permission_query_conditions = {
	"Firmalararo Tolov": "carieer.carieer.doctype.firmalararo_tolov.firmalararo_tolov.get_permission_query_conditions",
	# firmalararo sotuv xaridor firmaga ham ko'rinadi (u qabul qiladi / rad etadi)
	"Sotuv": "carieer.carieer.doctype.sotuv.sotuv.get_permission_query_conditions",
}
has_permission = {
	"Firmalararo Tolov": "carieer.carieer.doctype.firmalararo_tolov.firmalararo_tolov.has_permission",
	"Sotuv": "carieer.carieer.doctype.sotuv.sotuv.has_permission",
}

# GPS Malumot jadvali cheksiz o'smasin: eski nuqtalar har kuni o'chiriladi
scheduler_events = {
	"daily": ["carieer.api.cleanup_gps"],
}
