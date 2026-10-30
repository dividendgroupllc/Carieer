frappe.provide("frappe.dashboards.chart_sources");

// Panel Karer: shu oy qazib olindi / sotildi / omborda qoldi (har bir mahsulot bo'yicha)
frappe.dashboards.chart_sources["Qazib olish va sotuv"] = {
	method: "carieer.carieer.dashboard_chart_source.qazib_olish_va_sotuv.qazib_olish_va_sotuv.get",
	filters: [
		{
			fieldname: "zavod",
			label: __("Zavod"),
			fieldtype: "Link",
			options: "Zavod",
			default: "Karer",
			reqd: 1,
		},
	],
};
