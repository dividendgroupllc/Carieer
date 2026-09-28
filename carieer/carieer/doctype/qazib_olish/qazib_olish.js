frappe.ui.form.on("Qazib Olish", {
	setup(frm) {
		frm.set_query("warehouse", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("texnika", () => ({ filters: { company: frm.doc.company } }));
		frm.set_query("item_code", "items", () => ({ filters: { is_stock_item: 1, disabled: 0 } }));
	},
	onload(frm) {
		if (frm.is_new() && frm.doc.company && !frm.doc.warehouse) frm.trigger("company");
	},
	company(frm) {
		if (!frm.doc.company) return;
		frappe.call("carieer.utils.get_firma_defaults", { company: frm.doc.company }).then((r) => {
			const d = r.message || {};
			if (d.qazish_ombori) frm.set_value("warehouse", d.qazish_ombori);
		});
	},
	refresh(frm) {
		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("Stock Entry"), () => frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry), __("Ko'rish"));
		}
	},
});

frappe.ui.form.on("Qazib Olish Tovar", {
	qty(frm) {
		frm.set_value("total_qty", (frm.doc.items || []).reduce((s, r) => s + flt(r.qty), 0));
	},
	items_remove(frm) {
		frm.set_value("total_qty", (frm.doc.items || []).reduce((s, r) => s + flt(r.qty), 0));
	},
});
