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

# Custom JS yo'q: barcha formalar, ro'yxatlar va hisobotlar Frappe / ERPNext'ning o'z UI'si bilan ishlaydi.
# Bo'limlar (desktop ikonkasi + chap menyu): carieer/desktop_icon, carieer/workspace_sidebar, carieer/carieer/workspace

# Menyuni tozalash: Karer xodimi faqat «Karer», beton xodimi faqat «Beton Zavod» bo'limini ko'radi
boot_session = "carieer.permissions.boot_session"

# O'rnatish / migrate
after_install = "carieer.install.after_install"
after_migrate = "carieer.install.after_migrate"

doc_events = {
	# Tashqaridan (Kassa, Payment Entry) kiritilgan to'lovlar ham Sotuv'dagi qarz va holatni yangilasin
	"Payment Entry": {
		"on_submit": "carieer.carieer.doctype.sotuv.sotuv.on_payment_entry_change",
		"on_cancel": "carieer.carieer.doctype.sotuv.sotuv.on_payment_entry_change",
	},
	# GPS IMEI yozilganda eski nuqtalarga ham mashina raqami qo'yiladi
	"Vehicle": {
		"on_update": "carieer.api.sync_vehicle_gps",
	},
	# Инвентаризация: karer tovari tan narxi 0 bo'lishi mumkin
	"Stock Reconciliation": {
		"before_validate": "carieer.events.stock_reconciliation_before_validate",
	},
}

# Firmalararo To'lov ikkala firmaga (to'lovchi va oluvchi) ko'rinadi
permission_query_conditions = {
	"Firmalararo Tolov": "carieer.carieer.doctype.firmalararo_tolov.firmalararo_tolov.get_permission_query_conditions",
}
has_permission = {
	"Firmalararo Tolov": "carieer.carieer.doctype.firmalararo_tolov.firmalararo_tolov.has_permission",
}

# GPS Malumot jadvali cheksiz o'smasin: eski nuqtalar har kuni o'chiriladi
scheduler_events = {
	"daily": ["carieer.api.cleanup_gps"],
}
