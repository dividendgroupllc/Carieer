frappe.query_reports["Foyda Zarar"] = {
	filters: [
		{ fieldname: "company", label: __("Firma"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("Сана дан"), fieldtype: "Date", default: frappe.datetime.year_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("Сана гача"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
	],
	formatter: (value, row, column, data, default_formatter) =>
		carieer_moliya_formatter(value, row, column, data, default_formatter),
};

// Oyma-oy moliyaviy hisobotlar uchun umumiy ko'rinish: daraxt chekinishi, qalin yig'ma qatorlar,
// foiz qatorlari va manfiy summalar qizil rangda
function carieer_moliya_formatter(value, row, column, data, default_formatter) {
	if (!data) return default_formatter(value, row, column, data);
	if (column.fieldname === "label") {
		value = frappe.utils.escape_html(data.label || "");
		if (data.indent) value = `<span style="padding-left:${data.indent * 18}px">${value}</span>`;
	} else if (data.is_percent) {
		value = value === null || value === undefined || value === "" ? "" : `${format_number(value, null, 1)} %`;
		value = `<div style="text-align:right">${value}</div>`;
	} else {
		const raw = flt(value);
		value = data.is_header ? "" : default_formatter(value, row, column, data);
		if (raw < 0) value = `<span style="color:var(--red-600)">${value}</span>`;
	}
	if (data.bold || data.total_row) value = `<b>${value}</b>`;
	return value;
}
