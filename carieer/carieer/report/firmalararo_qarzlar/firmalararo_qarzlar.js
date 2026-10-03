// Firmalararo Qarzlar: oddiy jadval. Operatsiya - rangli belgi, Qarz qoldig'i - kim qarz ekaniga qarab rang
// (yashil: ular bizdan qarz, qizil: biz qarzmiz). Yakuniy qator qalin.

const FQ_BADGE = { berdik: "green", oldik: "blue", tolov: "orange", opening: "gray" };

frappe.query_reports["Firmalararo Qarzlar"] = {
	filters: [
		{
			fieldname: "company", label: __("Firma"), fieldtype: "Link", options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "boshqa_firma", label: __("Boshqa firma"), fieldtype: "Link", options: "Company", ignore_user_permissions: 1 },
		{ fieldname: "from_date", label: __("Dan"), fieldtype: "Date", default: frappe.datetime.year_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("Gacha"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
	],
	formatter(value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);
		const kind = data.kind;
		if (column.fieldname === "summa" && !flt(data.summa)) return "";
		value = default_formatter(value, row, column, data);

		if (kind === "header") return column.fieldname === "turi" ? `<b>${frappe.utils.escape_html(data.turi)}</b>` : "";
		if (column.fieldname === "turi" && FQ_BADGE[kind]) {
			return `<span class="indicator-pill ${FQ_BADGE[kind]}">${frappe.utils.escape_html(data.turi)}</span>`;
		}
		if (column.fieldname === "qoldiq" || column.fieldname === "kim_qarz") {
			const t = data.kim_qarz || "";
			const color = t.includes("bizdan") ? "var(--green-600)" : t.includes("qarzmiz") ? "var(--red-600)" : "var(--text-muted)";
			value = `<span style="color:${color}">${value}</span>`;
		}
		if (kind === "total") value = `<b>${value}</b>`;
		return value;
	},
	get_datatable_options(options) {
		return Object.assign(options, { checkboxColumn: false, inlineFilters: false });
	},
};
