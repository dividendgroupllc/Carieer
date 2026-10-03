frappe.query_reports["DDS"] = {
	filters: [
		{ fieldname: "company", label: __("Firma"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("Сана дан"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("Сана гача"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "mode_of_payment", label: __("Касса (способ оплаты)"), fieldtype: "Link", options: "Mode of Payment" },
		{
			fieldname: "party_type", label: __("Контрагент тури"), fieldtype: "Select",
			options: "\nCustomer\nSupplier\nEmployee\nShareholder",
			on_change: () => { frappe.query_report.set_filter_value("party", ""); },
		},
		{
			fieldname: "party", label: __("Контрагент"), fieldtype: "Dynamic Link",
			get_options: () => frappe.query_report.get_filter_value("party_type"),
		},
		{
			fieldname: "category", label: __("Категория"), fieldtype: "Select",
			options: "\nПокупатели\nПоставщики\nСотрудники\nУчредители\nДивиденды\nРасходы\nПрочие доходы\nПеремещения\nПрочие",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "summa" && data) {
			const color = data.direction === "Кирим" ? "#1b5e20" : "#b71c1c";
			value = `<span style="color:${color};font-weight:600">${value}</span>`;
		}
		return value;
	},
};
