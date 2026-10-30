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

// Tasdiqlangan sotuv: to'lov qabul qilish, ERPNext hujjatlari (hisob-faktura, ombor harakati), Didox
frappe.ui.form.on("Sotuv", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		if (!frm.doc.korrektirovka && flt(frm.doc.outstanding_amount) > 0) {
			frm.add_custom_button(__("To'lov qabul qilish"), () => sotuv_tolov_dialog(frm)).addClass(
				"btn-primary"
			);
		}
		if (frm.doc.sales_invoice) {
			// menyu shu firmaning Kassa / Ombor bo'limi bo'ladi (boshqa firma menyusi qolib ketmasin)
			frm.add_custom_button(
				__("Sales Invoice (qarz va to'lovlar)"),
				() => {
					carieer.sidebar_for_company(frm.doc.company, "Kassa");
					frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
				},
				__("ERPNext")
			);
			frm.add_custom_button(
				__("Ombor harakati"),
				() => {
					carieer.sidebar_for_company(frm.doc.company, "Ombor");
					frappe.set_route("query-report", "Stock Ledger", {
						company: frm.doc.company,
						from_date: frm.doc.posting_date,
						to_date: frm.doc.posting_date,
						voucher_no: frm.doc.sales_invoice,
					});
				},
				__("ERPNext")
			);
		}
		if (frm.doc.korrektirovka) return;
		frappe.require("/assets/carieer/js/didox.js", () => sotuv_didox_buttons(frm));
	},
});

// «Оплаты» jadvaliga qator qo'shib «Update» qilish bilan bir xil: to'lov Payment Entry bo'lib o'tadi.
// Summa kassa valyutasida: USD kassa tanlansa qarz kurs bilan dollarga o'tkaziladi.
function sotuv_tolov_nima_uchun(frm) {
	const qatorlar = [
		...(frm.doc.items || []).map((r) => [r.item_name || r.item_code, r.qty, r.uom, r.rate]),
		...(frm.doc.xizmatlar || []).map((r) => [r.xizmat, r.qty, "", r.rate]),
	];
	return qatorlar
		.map(
			([nomi, qty, uom, rate]) =>
				`<li>${frappe.utils.escape_html(nomi)}: ${flt(qty)} ${frappe.utils.escape_html(
					uom || ""
				)} × ${format_currency(rate, frm.doc.currency)}</li>`
		)
		.join("");
}

function sotuv_tolov_dialog(frm) {
	let info = null;
	const summa_hint = () => {
		if (!info) return;
		const summa = flt(d.get_value("summa"));
		const kurs = info.currency === info.sotuv_currency ? 1 : flt(d.get_value("kurs"));
		let jami = summa * kurs;
		// dollarda to'liq yopilganda 1 sentdan kam yaxlitlash farqi hisobga olinmaydi (server ham shunday)
		if (jami > flt(info.qarz) && jami - flt(info.qarz) <= kurs * 0.01) jami = flt(info.qarz);
		const qolgan = flt(info.qarz) - jami;
		d.set_df_property(
			"summa",
			"description",
			info.currency === info.sotuv_currency
				? __("To'lovdan keyin qarz: {0}", [format_currency(Math.max(qolgan, 0), info.sotuv_currency)])
				: __("= {0}. To'lovdan keyin qarz: {1}", [
						format_currency(jami, info.sotuv_currency),
						format_currency(Math.max(qolgan, 0), info.sotuv_currency),
				  ])
		);
	};
	const d = new frappe.ui.Dialog({
		title: __("To'lov qabul qilish: {0}", [frm.doc.customer_name || frm.doc.customer]),
		fields: [
			{
				fieldname: "qarz",
				fieldtype: "HTML",
				options: `<p>${__("Qarz")}: <b>${format_currency(
					frm.doc.outstanding_amount,
					frm.doc.currency
				)}</b> ${__("(jami {0})", [format_currency(frm.doc.amount, frm.doc.currency)])}</p>
				<p class="text-muted small">${__("Nima uchun")}:</p>
				<ul class="small">${sotuv_tolov_nima_uchun(frm)}</ul>`,
			},
			{
				fieldname: "mode_of_payment",
				fieldtype: "Link",
				options: "Mode of Payment",
				label: __("Kassa (Счёт)"),
				reqd: 1,
				get_query: () => ({ filters: { firma: frm.doc.company, enabled: 1 } }),
				onchange() {
					const kassa = d.get_value("mode_of_payment");
					if (!kassa) return;
					frappe
						.call("carieer.api.tolov_malumoti", { sotuv: frm.doc.name, mode_of_payment: kassa })
						.then((r) => {
							info = r.message;
							const boshqa = info.currency !== info.sotuv_currency;
							d.set_df_property("summa", "label", __("Summa ({0})", [info.currency]));
							d.set_df_property("kurs", "hidden", !boshqa);
							d.set_df_property(
								"kurs",
								"label",
								__("Kurs (1 {0} necha {1})", [info.currency, info.sotuv_currency])
							);
							if (boshqa) d.set_value("kurs", flt(info.kurs, 2));
							d.set_value("summa", flt(info.qarz_kassada, 2)).then(summa_hint);
						});
				},
			},
			{
				fieldname: "summa",
				fieldtype: "Float",
				label: __("Summa"),
				reqd: 1,
				description: __("Avval kassani tanlang: summa o'sha kassa valyutasida yoziladi"),
				onchange: summa_hint,
			},
			{ fieldname: "kurs", fieldtype: "Float", hidden: 1, onchange: summa_hint },
			{ fieldname: "sana", fieldtype: "Date", label: __("Sana"), default: frappe.datetime.get_today() },
			{ fieldname: "izoh", fieldtype: "Data", label: __("Izoh") },
		],
		primary_action_label: __("To'lovni saqlash"),
		primary_action(v) {
			frappe
				.call({
					method: "carieer.api.sotuv_tolov",
					args: {
						sotuv: frm.doc.name,
						mode_of_payment: v.mode_of_payment,
						summa: v.summa,
						kurs: v.kurs,
						sana: v.sana,
						izoh: v.izoh,
					},
					freeze: true,
				})
				.then(() => {
					d.hide();
					frappe.show_alert({ message: __("To'lov saqlandi"), indicator: "green" });
					frm.reload_doc();
				});
		},
	});
	d.show();
}

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
