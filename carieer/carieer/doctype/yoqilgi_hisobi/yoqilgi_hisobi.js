frappe.ui.form.on("Yoqilgi Hisobi", {
	setup(frm) {
		frm.set_query("vehicle", () => ({ filters: { company: frm.doc.company } }));
		frm.set_query("warehouse", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("item_code", () => ({ filters: { is_stock_item: 1, disabled: 0 } }));
	},
	onload(frm) {
		if (frm.is_new() && frm.doc.company && !frm.doc.warehouse) frm.trigger("company");
	},
	company(frm) {
		if (!frm.doc.company) return;
		frappe.call("carieer.utils.get_firma_defaults", { company: frm.doc.company }).then((r) => {
			const d = r.message || {};
			if (d.yoqilgi_ombori) frm.set_value("warehouse", d.yoqilgi_ombori);
		});
	},
	qty: (frm) => frm.set_value("amount", flt(frm.doc.qty) * flt(frm.doc.rate)),
	rate: (frm) => frm.set_value("amount", flt(frm.doc.qty) * flt(frm.doc.rate)),
	item_code(frm) {
		if (!frm.doc.item_code) return;
		frappe.db.get_value("Item", frm.doc.item_code, "valuation_rate").then((r) => {
			if (r.message && !frm.doc.rate) frm.set_value("rate", r.message.valuation_rate);
		});
	},
	refresh(frm) {
		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("Stock Entry"), () => frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry), __("Ko'rish"));
		}
	},
});
