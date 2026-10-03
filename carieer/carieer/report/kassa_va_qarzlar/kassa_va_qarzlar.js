// Kassa va Qarzlar: kassalarda qancha pul bor, kim bizdan qarz, biz kimdan qarzmiz.
// Bo'lim sarlavhalari va jami qatorlar qalin; qarzdorlar yashil, biz qarz bo'lganlar qizil.

frappe.query_reports["Kassa va Qarzlar"] = {
	filters: [
		{
			fieldname: "company", label: __("Firma"), fieldtype: "Link", options: "Company", reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "to_date", label: __("Sana holatiga"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
	],
	formatter(value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);
		const kind = data.kind;
		if (kind === "section") {
			return column.fieldname === "nomi"
				? `<b style="font-size:13px;text-transform:uppercase;letter-spacing:.03em">${frappe.utils.escape_html(data.nomi)}</b>`
				: "";
		}
		if (kind === "empty") return column.fieldname === "nomi" ? `<span class="text-muted">${__("Yo'q")}</span>` : "";
		if (["summa", "somda"].includes(column.fieldname) && !flt(data[column.fieldname]) && kind !== "total") return "";
		value = default_formatter(value, row, column, data);
		if (kind === "total") return `<b>${value}</b>`;
		if (["summa", "somda"].includes(column.fieldname)) {
			if (kind === "debitor") value = `<span style="color:var(--green-600)">${value}</span>`;
			if (kind === "kreditor") value = `<span style="color:var(--red-600)">${value}</span>`;
		}
		return value;
	},
	get_datatable_options(options) {
		return Object.assign(options, { checkboxColumn: false, inlineFilters: false });
	},
};
