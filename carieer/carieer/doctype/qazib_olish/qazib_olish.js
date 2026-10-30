// Qazib olish (jadvaldagi «Производство»): firma va ombor o'zi qo'yiladi,
// tovar tanlanganda birligi va цех o'zi to'ladi.
function qazib_olish_total(frm) {
	frm.set_value(
		"total_qty",
		(frm.doc.items || []).reduce((t, r) => t + flt(r.qty), 0)
	);
}

frappe.ui.form.on("Qazib Olish", {
	setup(frm) {
		frm.set_query("warehouse", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("company", () => ({
			filters: frm.carieer_companies ? { name: ["in", frm.carieer_companies] } : {},
		}));
		frm.set_query("item_code", "items", () => ({
			filters: {
				is_stock_item: 1,
				disabled: 0,
				// beton retsept (BOM) bo'yicha Sotuv'da chiqariladi - bu yerda faqat karer mahsuloti
				default_bom: ["is", "not set"],
				...(frm.carieer_guruhlar ? { item_group: ["in", frm.carieer_guruhlar] } : {}),
			},
		}));
	},
	onload(frm) {
		frappe
			.xcall("carieer.carieer.doctype.qazib_olish.qazib_olish.get_defaults", {
				company: frm.doc.company || carieer.firma(),
			})
			.then((v) => {
				frm.carieer_companies = v.companies;
				frm.carieer_guruhlar = v.tovar_guruhlari;
				if (!frm.is_new() || frm.doc.docstatus !== 0) return;
				if (v.company && v.company !== frm.doc.company) frm.set_value("company", v.company);
				if (!frm.doc.warehouse && v.warehouse) frm.set_value("warehouse", v.warehouse);
			});
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.stock_entry) {
			frm.add_custom_button(__("Ombor harakati"), () => {
				carieer.sidebar_for_company(frm.doc.company, "Ombor");
				frappe.set_route("query-report", "Stock Ledger", {
					company: frm.doc.company,
					from_date: frm.doc.posting_date,
					to_date: frm.doc.posting_date,
					voucher_no: frm.doc.stock_entry,
				});
			});
		}
	},
	company(frm) {
		if (!frm.doc.company) return;
		frappe
			.xcall("carieer.carieer.doctype.qazib_olish.qazib_olish.get_defaults", {
				company: frm.doc.company,
			})
			.then((v) => v.company === frm.doc.company && frm.set_value("warehouse", v.warehouse));
	},
	items_remove: qazib_olish_total,
});

frappe.ui.form.on("Qazib Olish Tovar", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) return;
		frappe.db.get_value("Item", row.item_code, ["item_name", "stock_uom"]).then((r) => {
			const v = r.message || {};
			const sex = `${v.item_name} цех`;
			const options = (frappe.meta.get_docfield(cdt, "sex").options || "").split("\n");
			frappe.model.set_value(cdt, cdn, {
				item_name: v.item_name,
				uom: v.stock_uom,
				...(!row.sex && options.includes(sex) ? { sex } : {}),
			});
		});
	},
	qty: qazib_olish_total,
});
