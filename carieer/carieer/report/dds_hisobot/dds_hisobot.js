frappe.query_reports["DDS Hisobot"] = {
	filters: [
		{ fieldname: "company", label: __("Firma"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("Dan"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("Gacha"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{
			fieldname: "account", label: __("Kassa / bank hisobi"), fieldtype: "Link", options: "Account",
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company"), account_type: ["in", ["Cash", "Bank"]], is_group: 0 },
			}),
		},
		{ fieldname: "moddalar", label: __("Moddalar bilan"), fieldtype: "Check", default: 1 },
		{ fieldname: "show_zero", label: __("Harakatsiz hisoblar ham"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.bold) value = `<b>${value}</b>`;
		return value;
	},
};
