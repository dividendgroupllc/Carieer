frappe.ui.form.on("Firmalararo Sotuv", {
	setup(frm) {
		frm.set_query("chiqish_ombori", () => ({ filters: { company: frm.doc.sotuvchi_firma, is_group: 0 } }));
		frm.set_query("kirish_ombori", () => ({ filters: { company: frm.doc.xaridor_firma, is_group: 0 } }));
		frm.set_query("xaridor_firma", () => ({ filters: { name: ["!=", frm.doc.sotuvchi_firma || ""] } }));
		frm.set_query("item_code", "items", () => ({ filters: { is_stock_item: 1, disabled: 0 } }));
	},
	sotuvchi_firma(frm) {
		frm.set_value("chiqish_ombori", "");
	},
	xaridor_firma(frm) {
		frm.set_value("kirish_ombori", "");
	},
	refresh(frm) {
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

function calc(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
	total(frm);
}

function total(frm) {
	frm.set_value("total_amount", (frm.doc.items || []).reduce((s, r) => s + flt(r.amount), 0));
}
