frappe.query_reports["Qarzdorlik"] = {
	filters: [
		{ fieldname: "company", label: __("Firma"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "to_date", label: __("Сана (шу кунга)"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "customer", label: __("Мижоз"), fieldtype: "Link", options: "Customer" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (data.is_total_row) return `<b>${value}</b>`;
		if (column.fieldname === "d15" && flt(data.d15) > 0) value = `<span style="color: var(--red-600)">${value}</span>`;
		if (column.fieldname === "d8_14" && flt(data.d8_14) > 0) value = `<span style="color: var(--orange-600)">${value}</span>`;
		return value;
	},
};
