frappe.ui.form.on("Beton Ishlab Chiqarish", {
	setup(frm) {
		frm.set_query("bom", () => ({ filters: { company: frm.doc.company, is_active: 1, docstatus: 1 } }));
		["xomashyo_ombori", "tayyor_ombori"].forEach((f) =>
			frm.set_query(f, () => ({ filters: { company: frm.doc.company, is_group: 0 } }))
		);
	},
	onload(frm) {
		if (frm.is_new() && frm.doc.company && !frm.doc.xomashyo_ombori) frm.trigger("company");
	},
	company(frm) {
		if (!frm.doc.company) return;
		frappe.call("carieer.utils.get_firma_defaults", { company: frm.doc.company }).then((r) => {
			const d = r.message || {};
			if (d.beton_xomashyo_ombori) frm.set_value("xomashyo_ombori", d.beton_xomashyo_ombori);
			if (d.beton_ombori) frm.set_value("tayyor_ombori", d.beton_ombori);
		});
	},
	refresh(frm) {
		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("Stock Entry"), () => frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry), __("Ko'rish"));
		}
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Xomashyoni hisoblash"), () => frm.save());
		}
	},
});
