app_name = "carieer"
app_title = "Carieer"
app_publisher = "ismoil"
app_description = "Eko Karer: sotuv, kassa, nachislenie, ombor va hisobotlar (ERPNext ustida)"
app_email = "devpy2869@gmail.com"
app_license = "mit"

# ERPNext (buxgalteriya, ombor) va HRMS (xodimlar) ustida ishlaydi
required_apps = ["erpnext", "hrms"]

# Formalar, ro'yxatlar va hisobotlar Frappe / ERPNext'ning o'z UI'si bilan ishlaydi (custom JS yo'q).
# Bo'limlar (desktop ikonkasi + chap menyu): carieer/desktop_icon, carieer/<modul>/sidebar

# Menyuni tozalash: Karer xodimi (ERPNext'ning boshqa rollari bo'lmasa) faqat Carieer ikonkalarini ko'radi
extend_bootinfo = "carieer.permissions.hide_foreign_icons"

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
}

# Didox: firmalarning kiruvchi / chiquvchi elektron hujjatlari tarixi «Didox Hujjat» jurnaliga tortiladi
scheduler_events = {
	"cron": {
		"*/30 * * * *": ["carieer.didox.sync.sync_all"],
	},
}
