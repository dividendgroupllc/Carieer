frappe.query_reports["Texnika Xarajatlari"] = {
	filters: [
		{ fieldname: "company", label: __("Firma"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("Dan"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("Gacha"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "vehicle", label: __("Texnika"), fieldtype: "Link", options: "Vehicle" },
	],
};
