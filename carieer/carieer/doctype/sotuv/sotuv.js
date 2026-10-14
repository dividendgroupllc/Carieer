// Summa forma ichida darhol hisoblansin (Save'ni kutmasdan): tovar tanlanganda birlik, narx va ombor o'zi qo'yiladi.
function sotuv_calc(frm) {
	const sum = (rows) => (rows || []).reduce((t, r) => t + flt(r.qty) * flt(r.rate), 0);
	frm.set_value("itog", sum(frm.doc.items));
	frm.set_value("xizmat_jami", sum(frm.doc.xizmatlar));
	frm.set_value("amount", sum(frm.doc.items) + sum(frm.doc.xizmatlar));
}

function sotuv_row_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
	sotuv_calc(frm);
}

frappe.ui.form.on("Sotuv Tovar", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code || !frm.doc.tip) return;
		frappe.call({
			method: "carieer.carieer.doctype.sotuv.sotuv.get_item_defaults",
			args: { item_code: row.item_code, tip: frm.doc.tip, currency: frm.doc.currency },
		}).then((r) => {
			const v = r.message || {};
			frappe.model.set_value(cdt, cdn, {
				item_name: v.item_name,
				uom: v.uom,
				warehouse: v.warehouse,
				qty: flt(row.qty) || 1,
				rate: flt(row.rate) || v.rate,
			});
			sotuv_row_amount(frm, cdt, cdn);
		});
	},
	qty: sotuv_row_amount,
	rate: sotuv_row_amount,
});

frappe.ui.form.on("Sotuv Xizmat", {
	qty: sotuv_row_amount,
	rate: sotuv_row_amount,
});

frappe.ui.form.on("Sotuv", {
	items_remove: (frm) => sotuv_calc(frm),
	xizmatlar_remove: (frm) => sotuv_calc(frm),
});
