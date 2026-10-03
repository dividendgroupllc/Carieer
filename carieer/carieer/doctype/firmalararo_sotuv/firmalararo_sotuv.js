frappe.ui.form.on("Firmalararo Sotuv", {
	setup(frm) {
		frm.set_query("chiqish_ombori", () => ({ filters: { company: frm.doc.sotuvchi_firma, is_group: 0 } }));
		frm.set_query("kirish_ombori", () => ({ filters: { company: frm.doc.xaridor_firma, is_group: 0 } }));
		frm.set_query("xaridor_firma", () => ({ filters: { name: ["!=", frm.doc.sotuvchi_firma || ""] } }));
		frm.set_query("item_code", "items", () => ({ filters: { is_stock_item: 1, disabled: 0 } }));
		// Darhol to'lov: har bir firmaning o'z kassalari
		for (const [kassa, firma] of [["xaridor_kassa", "xaridor_firma"], ["sotuvchi_kassa", "sotuvchi_firma"]]) {
			frm.set_query(kassa, () => ({
				query: "carieer.carieer.doctype.firmalararo_tolov.firmalararo_tolov.kassa_query",
				filters: { company: frm.doc[firma] },
			}));
		}
	},
	onload(frm) {
		// Firma xodimi: odatda o'z firmasi xaridor (boshqa firmadan tovar oladi)
		if (frm.is_new() && !frm.doc.sotuvchi_firma && !frm.doc.xaridor_firma) {
			const company = frappe.defaults.get_user_default("Company");
			if (company && frappe.boot.carieer_firma) frm.set_value("xaridor_firma", company);
		}
	},
	sotuvchi_firma: (frm) => set_omborlar(frm, "chiqish_ombori"),
	xaridor_firma: (frm) => set_omborlar(frm, "kirish_ombori"),
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.dashboard.set_headline(
				__("Diqqat: hujjat <b>Submit</b> qilinmaguncha tovar ham, qarz ham yozilmaydi."), "orange"
			);
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Firmalararo Qarzlar"), () => frappe.set_route("query-report", "Firmalararo Qarzlar"), __("Ko'rish"));
		}
		if (frm.doc.sales_invoice) {
			frm.add_custom_button(__("Sales Invoice"), () => frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice), __("Ko'rish"));
		}
		if (frm.doc.purchase_invoice) {
			frm.add_custom_button(__("Purchase Invoice"), () => frappe.set_route("Form", "Purchase Invoice", frm.doc.purchase_invoice), __("Ko'rish"));
		}
	},
});

frappe.ui.form.on("Firmalararo Sotuv Tovar", {
	qty: (frm, cdt, cdn) => calc(frm, cdt, cdn),
	rate: (frm, cdt, cdn) => calc(frm, cdt, cdn),
	items_remove: (frm) => total(frm),
});

function set_omborlar(frm, field) {
	frm.set_value(field, "");
	frappe.call("carieer.carieer.doctype.firmalararo_sotuv.firmalararo_sotuv.get_omborlar", {
		sotuvchi_firma: frm.doc.sotuvchi_firma, xaridor_firma: frm.doc.xaridor_firma,
	}).then((r) => {
		const d = r.message || {};
		if (d[field]) frm.set_value(field, d[field]);
	});
}

function calc(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
	total(frm);
}

function total(frm) {
	frm.set_value("total_amount", (frm.doc.items || []).reduce((s, r) => s + flt(r.amount), 0));
}
