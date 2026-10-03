app_name = "carieer"
app_title = "Carieer"
app_publisher = "ismoil"
app_description = "Karer, beton, texnika va hisobotlar (ERPNext ustida)"
app_email = "devpy2869@gmail.com"
app_license = "mit"

required_apps = ["erpnext"]

# Bosh sahifadagi "Karer" ikonkasi (Frappe bitta ilovaga bitta ikonka ko'rsatadi): carieer-home sahifasi
# xodimni o'z firmasining bo'limiga yuboradi (Beton zavod xodimi -> Beton Zavod, qolganlar -> Karer)
add_to_apps_screen = [
	{
		"name": "carieer",
		"logo": "/assets/carieer/karer-logo.svg",
		"title": "Karer",
		"route": "/desk/carieer-home",
		"has_permission": "carieer.utils.has_app_permission",
	},
]

# Beton xodimi ilovani "Beton Zavod", karer xodimi "Karer" nomi bilan ko'radi
boot_session = "carieer.utils.boot_session"

# O'rnatish / migrate
after_install = "carieer.install.after_install"
after_migrate = "carieer.install.after_migrate"

# Tashqaridan (masalan Payment Entry formasidan) kiritilgan to'lovlar ham Sotuv statusini yangilasin
doc_events = {
	"Payment Entry": {
		"on_submit": "carieer.carieer.doctype.sotuv.sotuv.on_payment_entry_change",
		"on_cancel": "carieer.carieer.doctype.sotuv.sotuv.on_payment_entry_change",
	},
	"Vehicle": {
		"on_update": "carieer.api.sync_vehicle_gps",
	},
}

# Firmalararo Sotuv / To'lov ikkala firmaga (sotuvchi va xaridor) ko'rinadi
permission_query_conditions = {
	"Firmalararo Sotuv": "carieer.carieer.doctype.firmalararo_sotuv.firmalararo_sotuv.get_permission_query_conditions",
	"Firmalararo Tolov": "carieer.carieer.doctype.firmalararo_tolov.firmalararo_tolov.get_permission_query_conditions",
}
has_permission = {
	"Firmalararo Sotuv": "carieer.carieer.doctype.firmalararo_sotuv.firmalararo_sotuv.has_permission",
	"Firmalararo Tolov": "carieer.carieer.doctype.firmalararo_tolov.firmalararo_tolov.has_permission",
}

# Vehicle ga qo'shilgan custom fieldlar install.py da yaratiladi (fixtures shart emas)

# GPS Malumot jadvali cheksiz o'smasin: 90 kundan eski nuqtalar har kuni o'chiriladi
scheduler_events = {
	"daily": ["carieer.api.cleanup_gps"],
}
