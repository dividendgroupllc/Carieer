frappe.query_reports["Akt Sverka"] = {
	filters: [
		{ fieldname: "company", label: __("Firma"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("Сана дан"), fieldtype: "Date", default: frappe.datetime.year_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("Сана гача"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{
			fieldname: "party_type", label: __("Контрагент тури"), fieldtype: "Select",
			options: "Customer\nSupplier\nEmployee\nShareholder", default: "Customer", reqd: 1,
			on_change: () => { frappe.query_report.set_filter_value("party", ""); },
		},
		{
			fieldname: "party", label: __("Контрагент"), fieldtype: "Dynamic Link", reqd: 1,
			get_options: () => frappe.query_report.get_filter_value("party_type"),
		},
		{ fieldname: "currency", label: __("Валюта (бўш = ўзи)"), fieldtype: "Link", options: "Currency" },
	],
	onload(report) {
		report.page.add_inner_button(__("Контрагент отчёт"), () => {
			frappe.set_route("query-report", "Kontragent Otchet", {
				company: report.get_filter_value("company"),
				from_date: report.get_filter_value("from_date"),
				to_date: report.get_filter_value("to_date"),
				party_type: report.get_filter_value("party_type"),
			});
		});
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.is_bold) value = `<b>${value}</b>`;
		return value;
	},
};
