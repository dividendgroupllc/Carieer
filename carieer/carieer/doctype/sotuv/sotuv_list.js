frappe.listview_settings["Sotuv"] = {
	add_fields: ["status", "outstanding_amount", "currency"],
	get_indicator(doc) {
		const colors = {
			"Draft": "red",
			"To'lanmagan": "orange",
			"Qisman to'langan": "yellow",
			"To'langan": "green",
			"Cancelled": "gray",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
