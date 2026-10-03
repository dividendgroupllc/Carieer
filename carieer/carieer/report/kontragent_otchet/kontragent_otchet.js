frappe.query_reports["Kontragent Otchet"] = {
	filters: [
		{ fieldname: "company", label: __("Firma"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("Сана дан"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("Сана гача"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{
			fieldname: "party_type", label: __("Контрагент тури"), fieldtype: "Select",
			options: "\nCustomer\nSupplier\nEmployee\nShareholder",
			on_change: () => { frappe.query_report.set_filter_value("party", ""); },
		},
		{
			fieldname: "party", label: __("Контрагент"), fieldtype: "Dynamic Link",
			get_options: () => frappe.query_report.get_filter_value("party_type"),
		},
		{ fieldname: "show_zero", label: __("Нол қолдиқларни кўрсатиш"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "party" && data.party_name && data.party_name !== data.party) {
			value += ` <span class="text-muted">${frappe.utils.escape_html(data.party_name)}</span>`;
		}
		if (column.fieldname === "akt_sverka" && data.party && !data.is_total_row) {
			const q = new URLSearchParams({
				company: frappe.query_report.get_filter_value("company"),
				party_type: data.party_type,
				party: data.party,
				from_date: frappe.query_report.get_filter_value("from_date"),
				to_date: frappe.query_report.get_filter_value("to_date"),
			});
			value = `<a href="/desk/query-report/Akt Sverka?${q}">📊 ${__("Акт сверка")}</a>`;
		}
		if (data.is_total_row) value = `<b>${value}</b>`;
		return value;
	},
};
