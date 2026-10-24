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
				bom: v.bom,
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
	onload(frm) {
		// «Тип» (zavod): Beton xodimi - Beton, Karer xodimi - Karer. Ikkala zavodi bor (rahbar) - o'zi tanlaydi.
		const zavodlar = (frappe.defaults.get_user_permissions().Zavod || []).map((p) => p.doc);
		frm.toggle_display("tip", zavodlar.length > 1);
		if (!frm.is_new()) return;
		frappe
			.xcall("carieer.carieer.doctype.sotuv.sotuv.get_user_zavod", { tip: frm.doc.tip })
			.then((tip) => tip && tip !== frm.doc.tip && frm.set_value("tip", tip));
	},
	items_remove: (frm) => sotuv_calc(frm),
	xizmatlar_remove: (frm) => sotuv_calc(frm),
});

// Didox hisob-faktura (tasdiqlangan sotuv)
frappe.ui.form.on("Sotuv", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.korrektirovka) return;
		frappe.require("/assets/carieer/js/didox.js", () => sotuv_didox_buttons(frm));
	},
});

function sotuv_didox_buttons(frm) {
	const ochirilgan = ["O'chirilgan", "Qoralama o'chirilgan"].includes(frm.doc.didox_holati);
	if (frm.doc.didox_hujjat && !ochirilgan) {
		frm.add_custom_button(
			__("Hisob-faktura"),
			() => frappe.set_route("Form", "Didox Hujjat", frm.doc.didox_hujjat),
			__("Didox")
		);
		return;
	}
	frm.add_custom_button(
		__("Hisob-faktura yaratish"),
		async () => {
			const hujjat = await carieer.didox.call("sotuvdan_faktura", { sotuv: frm.doc.name });
			await frm.reload_doc();
			frappe.confirm(
				__("Qoralama Didox'da yaratildi. Hozir ERI bilan imzolab yuborasizmi?"),
				async () => {
					await carieer.didox.imzolash(hujjat, frm.doc.company);
					frm.reload_doc();
				}
			);
		},
		__("Didox")
	);
}
