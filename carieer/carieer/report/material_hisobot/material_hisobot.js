frappe.query_reports["Material Hisobot"] = {
	filters: [
		{ fieldname: "company", label: __("Firma"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("Dan"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("Gacha"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{
			fieldname: "warehouse", label: __("Ombor"), fieldtype: "Link", options: "Warehouse",
			get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company") } }),
		},
		{ fieldname: "item_code", label: __("Tovar"), fieldtype: "Link", options: "Item" },
		{ fieldname: "show_zero", label: __("Nol qatorlarni ko'rsatish"), fieldtype: "Check" },
	],
};
