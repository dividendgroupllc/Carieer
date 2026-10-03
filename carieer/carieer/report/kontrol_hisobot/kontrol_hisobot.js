frappe.query_reports["Kontrol Hisobot"] = {
	filters: [
		{ fieldname: "company", label: __("Firma"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("Dan"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("Gacha"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "customer", label: __("Mijoz"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "item_code", label: __("Tovar"), fieldtype: "Link", options: "Item" },
		{ fieldname: "tip", label: __("Тип"), fieldtype: "Select", options: "\nKarer\nBeton" },
		{ fieldname: "mashina_raqami", label: __("Mashina raqami"), fieldtype: "Data" },
		{ fieldname: "currency", label: __("Valyuta"), fieldtype: "Link", options: "Currency" },
		{ fieldname: "status", label: __("Holat"), fieldtype: "Select", options: "\nTo'lanmagan\nQisman to'langan\nTo'langan" },
		{ fieldname: "group_by", label: __("Guruhlash"), fieldtype: "Select", options: "\nMijoz\nTovar\nKun\nMashina\nValyuta" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "outstanding_amount" && data && flt(data.outstanding_amount) > 0) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
