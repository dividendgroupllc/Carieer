app_name = "carieer"
app_title = "Carier"
app_publisher = "ismoil"
app_description = "Eko Karer va Eko Beton: sotuv, kassa, nachislenie, ombor, beton ishlab chiqarish va hisobotlar (ERPNext ustida)"
app_email = "devpy2869@gmail.com"
app_license = "mit"

# ERPNext (buxgalteriya, ombor) va HRMS (xodimlar) ustida ishlaydi
required_apps = ["erpnext", "hrms"]

add_to_apps_screen = [
	{
		"name": "carieer",
		"logo": "/assets/carieer/icons/desktop_icons/solid/karer.svg",
		"title": "Carier",
		"route": "/desk",
		"has_permission": "carieer.permissions.has_app_permission",
	}
]

# Formalar, ro'yxatlar va hisobotlar Frappe / ERPNext'ning o'z UI'si bilan ishlaydi.
# Ro'yxat va hisobotlarda firma filtri - xodimning o'z firmasi (Karer / Beton bo'limiga qarab)
app_include_js = "carieer.bundle.js"
# Bo'limlar (desktop ikonkasi + chap menyu): carieer/desktop_icon, carieer/workspace_sidebar

# Menyuni tozalash: Karer xodimi (ERPNext'ning boshqa rollari bo'lmasa) faqat Carieer ikonkalarini ko'radi
extend_bootinfo = ["carieer.permissions.hide_foreign_icons", "carieer.permissions.boot_firma"]

# O'rnatish / migrate
after_install = "carieer.install.after_install"
after_migrate = "carieer.install.after_migrate"

doc_events = {
	# Tashqaridan (Kassa, Payment Entry) kiritilgan to'lovlar ham Sotuv'dagi qarz va holatni yangilasin
	"Payment Entry": {
		"validate": "carieer.utils.validate_payment_kassa",
		"on_submit": "carieer.carieer.doctype.sotuv.sotuv.on_payment_entry_change",
		"on_cancel": "carieer.carieer.doctype.sotuv.sotuv.on_payment_entry_change",
	},
	# Yangi xarajat / daromad kategoriyasi -> firmada shu modda hisobi
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
	# GPS IMEI yozilganda eski nuqtalarga ham mashina raqami qo'yiladi
	"Vehicle": {
		"on_update": "carieer.api.sync_vehicle_gps",
	},
}

# Didox: firmalarning kiruvchi / chiquvchi elektron hujjatlari tarixi «Didox Hujjat» jurnaliga tortiladi.
# GPS Malumot jadvali cheksiz o'smasin: eski nuqtalar har kuni o'chiriladi.
scheduler_events = {
	"daily": ["carieer.api.cleanup_gps"],
	"cron": {
		"*/30 * * * *": ["carieer.didox.sync.sync_all"],
	},
}
