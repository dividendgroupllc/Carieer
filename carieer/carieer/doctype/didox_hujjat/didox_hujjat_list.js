frappe.listview_settings["Didox Hujjat"] = {
	get_indicator(doc) {
		const colors = {
			Imzolangan: "green",
			Qoralama: "gray",
			"Kontragent imzosini kutmoqda": "orange",
			"Bizning imzoni kutmoqda": "red",
			"Rad etilgan": "red",
		};
		return [__(doc.holat), colors[doc.holat] || "gray", "holat,=," + doc.holat];
	},
	onload(listview) {
		frappe.require("/assets/carieer/js/didox.js", () => {
			listview.page.add_inner_button(__("Sinxronlash"), () =>
				carieer.didox.ask_company(__("Didox'dan hujjatlarni tortish"), (company) =>
					carieer.didox
						.call("sinxronlash", { company })
						.then(() =>
							frappe.show_alert(
								__("Sinxron boshlandi, bir necha daqiqada ro'yxat yangilanadi")
							)
						)
				)
			);
			listview.page.add_inner_button(__("ERI bilan kirish"), () =>
				carieer.didox.ask_company(__("Didox'ga ERI bilan kirish"), (company) =>
					carieer.didox.eri_login(company)
				)
			);
		});
	},
};
