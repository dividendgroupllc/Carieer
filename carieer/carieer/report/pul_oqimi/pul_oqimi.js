frappe.query_reports["Pul Oqimi"] = {
	filters: [
		{ fieldname: "company", label: __("Firma"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("Сана дан"), fieldtype: "Date", default: frappe.datetime.year_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("Сана гача"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "mode_of_payment", label: __("Касса (способ оплаты)"), fieldtype: "Link", options: "Mode of Payment" },
	],
	formatter: (value, row, column, data, default_formatter) =>
		carieer_moliya_formatter(value, row, column, data, default_formatter),
};

// Oyma-oy moliyaviy hisobotlar uchun umumiy ko'rinish (Google Sheets'dagi jadval kabi):
// summalar valyuta belgisisiz, minglik ajratgich bilan; nol katakchalar bo'sh; manfiy summalar qizil;
// bo'lim sarlavhalari (АКТИВЫ, ПАССИВЫ) rangli; yig'ma qatorlar qalin; "Разница" 0 bo'lsa yashil, aks holda qizil.
function carieer_moliya_formatter(value, row, column, data, default_formatter) {
	if (!data) return default_formatter(value, row, column, data);
	if (column.fieldname === "label") {
		let label = frappe.utils.escape_html(data.label || "");
		if (data.is_header) {
			return `<span style="font-weight:700;letter-spacing:.04em;color:var(--primary)">${label}</span>`;
		}
		if (data.indent) label = `<span style="padding-left:${data.indent * 18}px">${label}</span>`;
		return data.bold || data.total_row ? `<b>${label}</b>` : label;
	}
	if (data.is_header) return "";
	if (data.is_percent) {
		if (value === null || value === undefined || value === "") return "";
		return `<div style="text-align:right;color:var(--text-muted)"><i>${format_number(value, null, 1)} %</i></div>`;
	}
	const raw = flt(value);
	if (Math.abs(raw) < 0.005) {
		const zero = data.is_check ? `<span style="color:var(--green-600)">0</span>` : data.total_row ? "0" : "";
		return `<div style="text-align:right">${zero}</div>`;
	}
	let color = raw < 0 ? "var(--red-600)" : "";
	if (data.is_check) color = "var(--red-600)";
	let html = format_number(raw, null, 0);
	if (color) html = `<span style="color:${color}">${html}</span>`;
	if (data.bold || data.total_row) html = `<b>${html}</b>`;
	return `<div style="text-align:right">${html}</div>`;
}
