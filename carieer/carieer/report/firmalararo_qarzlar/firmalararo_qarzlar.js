// ERPNext General Ledger uslubi: har firma juftligi - sarlavha, Бошланғич қолдиқ, hujjatlar, Жами, Якуний қолдиқ.
// Filtrlar - hisobot JSON'ida.
frappe.query_reports["Firmalararo Qarzlar"] = {
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "holat" && data && data.holat) {
			const color = data.holat.startsWith("⚠") ? "var(--orange-600)" : "var(--green-600)";
			value = `<span style="color:${color}">${value}</span>`;
		}
		return value;
	},
};
