app_name = "carieer"
app_title = "Carieer"
app_publisher = "ismoil"
app_description = "Karer, beton, texnika va hisobotlar (ERPNext ustida)"
app_email = "devpy2869@gmail.com"
app_license = "mit"

required_apps = ["erpnext"]

# Bosh sahifadagi (Desktop) "Karer" ikonkasi -> Karer bo'limi (barcha shortcut'lar shu yerda)
add_to_apps_screen = [
	{
		"name": "carieer",
		"logo": "/assets/carieer/karer-logo.svg",
		"title": "Karer",
		"route": "/desk/karer",
		"has_permission": "carieer.utils.has_app_permission",
	}
]

# O'rnatish / migrate
after_install = "carieer.install.after_install"
after_migrate = "carieer.install.after_migrate"

# Tashqaridan (masalan Payment Entry formasidan) kiritilgan to'lovlar ham Karer Sotuv statusini yangilasin
doc_events = {
	"Payment Entry": {
		"on_submit": "carieer.carieer.doctype.karer_sotuv.karer_sotuv.on_payment_entry_change",
		"on_cancel": "carieer.carieer.doctype.karer_sotuv.karer_sotuv.on_payment_entry_change",
	},
	"Vehicle": {
		"on_update": "carieer.api.sync_vehicle_gps",
	},
}

# Vehicle ga qo'shilgan custom fieldlar install.py da yaratiladi (fixtures shart emas)

# GPS Malumot jadvali cheksiz o'smasin: 90 kundan eski nuqtalar har kuni o'chiriladi
scheduler_events = {
	"daily": ["carieer.api.cleanup_gps"],
}
