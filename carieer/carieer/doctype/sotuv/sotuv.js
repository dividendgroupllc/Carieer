// Sotuv - sotuv posti (AppSheet "Ввод продажи"): Тип, Валюта, Доставка, Клиент, Номер машины,
// Товары, Услуги, Оплаты. Tugmalar: Добавить услугу, Оплата, Завершить.

frappe.ui.form.on("Sotuv", {
	setup(frm) {
		frm.set_query("customer", () => ({ filters: { disabled: 0 } }));
		frm.set_query("item_code", "items", () => ({ filters: { is_stock_item: 1, disabled: 0, is_sales_item: 1 } }));
		frm.set_query("xizmat", "xizmatlar", () => ({ filters: { is_stock_item: 0, disabled: 0, is_sales_item: 1 } }));
		frm.set_query("warehouse", "items", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("vehicle", () => ({ filters: { company: frm.doc.company } }));
		frm.set_query("uom", "items", (doc, cdt, cdn) => ({
			query: "erpnext.controllers.queries.get_item_uom_query",
			filters: { item_code: locals[cdt][cdn].item_code },
		}));
	},

	onload(frm) {
		// Xodim faqat o'z zavodi nomidan sotadi: beton xodimi -> Beton, karer xodimi -> Karer
		const firma = frappe.boot.carieer_firma;
		if (firma) {
			frm.set_df_property("tip", "read_only", 1);
			if (frm.is_new() && frm.doc.tip !== firma) return frm.set_value("tip", firma);
		}
		if (frm.is_new()) frm.trigger("tip");
	},

	refresh(frm) {
		frm.page.set_indicator(__(frm.doc.status), status_color(frm.doc.status));
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Добавить услугу"), () => {
				frm.add_child("xizmatlar", { qty: 1 });
				frm.refresh_field("xizmatlar");
				frm.scroll_to_field("xizmatlar");
			});
			if (!frm.is_new()) frm.page.set_primary_action(__("Завершить"), () => frm.savesubmit());
		}
		if (frm.doc.docstatus === 1 && flt(frm.doc.outstanding_amount) > 0) {
			frm.add_custom_button(__("Оплата"), () => payment_dialog(frm)).addClass("btn-primary");
		}
		if (frm.doc.sales_invoice) {
			frm.add_custom_button(__("Sales Invoice"), () => frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice), __("Ko'rish"));
			frm.add_custom_button(__("Akt sverka"), () => frappe.set_route("query-report", "Akt Sverka", {
				company: frm.doc.company, party_type: "Customer", party: frm.doc.customer,
			}), __("Ko'rish"));
		}
	},

	// Тип: Karer yoki Beton -> qaysi firma nomidan sotiladi
	tip(frm) {
		if (!frm.doc.tip || frm.doc.docstatus !== 0) return;
		frappe.call("carieer.carieer.doctype.sotuv.sotuv.get_tip_company", { tip: frm.doc.tip }).then((r) => {
			const company = r.message;
			if (!company) return;
			if (company === frm.doc.company) return;
			frm.set_value("company", company);
			(frm.doc.items || []).forEach((r) => frappe.model.set_value(r.doctype, r.name, "warehouse", ""));
			(frm.doc.items || []).forEach((r) => r.item_code && set_warehouse(frm, r));
			if (!frm.doc.currency) frm.set_value("currency", erpnext.get_currency(company));
			frm.trigger("currency");
		});
	},

	currency(frm) {
		const cc = frm.doc.company && erpnext.get_currency(frm.doc.company);
		if (!frm.doc.currency || !cc) return;
		if (frm.doc.currency === cc) return frm.set_value("conversion_rate", 1);
		frappe.call("carieer.utils.get_exchange_rate_for", { from_currency: frm.doc.currency, to_currency: cc, date: frm.doc.posting_date })
			.then((r) => frm.set_value("conversion_rate", r.message));
	},

	conversion_rate: (frm) => calc_totals(frm),
});

frappe.ui.form.on("Sotuv Tovar", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) return;
		frappe.db.get_value("Item", row.item_code, ["stock_uom", "sales_uom"]).then((r) => {
			const it = r.message || {};
			frappe.model.set_value(cdt, cdn, "uom", it.sales_uom || it.stock_uom);
		});
		set_warehouse(frm, row);
	},
	qty: (frm, cdt, cdn) => calc_row(frm, cdt, cdn),
	rate: (frm, cdt, cdn) => calc_row(frm, cdt, cdn),
	items_remove: (frm) => calc_totals(frm),
});

frappe.ui.form.on("Sotuv Xizmat", {
	qty: (frm, cdt, cdn) => calc_row(frm, cdt, cdn),
	rate: (frm, cdt, cdn) => calc_row(frm, cdt, cdn),
	xizmatlar_remove: (frm) => calc_totals(frm),
});

frappe.ui.form.on("Sotuv Tolov", {
	mode_of_payment(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.mode_of_payment || !frm.doc.company) return;
		frappe.call("carieer.carieer.doctype.kassa.kassa.get_kassa_info", { mode_of_payment: row.mode_of_payment, company: frm.doc.company })
			.then((r) => {
				const d = r.message || {};
				frappe.model.set_value(cdt, cdn, "valyuta", d.currency || "");
				if (d.currency && d.currency === frm.doc.currency) return frappe.model.set_value(cdt, cdn, "kurs", 1);
				if (d.currency) {
					frappe.call("carieer.utils.get_exchange_rate_for", { from_currency: d.currency, to_currency: frm.doc.currency, date: frm.doc.posting_date })
						.then((x) => frappe.model.set_value(cdt, cdn, "kurs", x.message));
				}
			});
	},
	summa: (frm, cdt, cdn) => calc_payment(frm, cdt, cdn),
	kurs: (frm, cdt, cdn) => calc_payment(frm, cdt, cdn),
	tolovlar_add(frm, cdt, cdn) {
		// Qarzni avtomatik taklif qiladi
		frappe.model.set_value(cdt, cdn, "summa", Math.max(flt(frm.doc.outstanding_amount), 0));
	},
	tolovlar_remove: (frm) => calc_totals(frm),
});

function set_warehouse(frm, row) {
	if (!frm.doc.company || !row.item_code) return;
	frappe.call("carieer.utils.get_item_warehouse", { item_code: row.item_code, company: frm.doc.company }).then((r) => {
		if (r.message) frappe.model.set_value(row.doctype, row.name, "warehouse", r.message);
	});
}

function calc_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
	calc_totals(frm);
}

function calc_payment(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "sotuv_summa", flt(row.summa) * flt(row.kurs || 1));
	calc_totals(frm);
}

function calc_totals(frm) {
	const sum = (rows, f) => (rows || []).reduce((s, r) => s + flt(r[f]), 0);
	const itog = sum(frm.doc.items, "amount");
	const xizmat = sum(frm.doc.xizmatlar, "amount");
	const total = itog + xizmat;
	frm.set_value({
		itog,
		xizmat_jami: xizmat,
		amount: total,
		base_amount: total * flt(frm.doc.conversion_rate || 1),
	});
	if (frm.doc.docstatus === 0) {
		const paid = sum(frm.doc.tolovlar, "sotuv_summa");
		frm.set_value({ total_paid: paid, outstanding_amount: total - paid });
	}
}

function status_color(status) {
	return {
		"Draft": "red",
		"To'lanmagan": "orange",
		"Qisman to'langan": "yellow",
		"To'langan": "green",
		"Cancelled": "gray",
	}[status] || "blue";
}

function payment_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Оплата"),
		fields: [
			{ fieldname: "mode_of_payment", fieldtype: "Link", options: "Mode of Payment", label: __("Счёт (kassa)"), reqd: 1 },
			{ fieldname: "valyuta", fieldtype: "Data", label: __("Валюта"), read_only: 1 },
			{ fieldname: "amount", fieldtype: "Float", label: __("Сумма (kassa valyutasida)"), reqd: 1, default: frm.doc.outstanding_amount },
			{ fieldname: "kim", fieldtype: "Data", label: __("Кто оплатил") },
			{ fieldname: "izoh", fieldtype: "Data", label: __("Примечание") },
			{ fieldtype: "HTML", options: `<p class="text-muted">${__("Долг")}: <b>${format_currency(frm.doc.outstanding_amount, frm.doc.currency)}</b></p>` },
		],
		primary_action_label: __("Сохранить"),
		primary_action(values) {
			frappe.call({
				method: "carieer.carieer.doctype.sotuv.sotuv.tolov_qabul_qilish",
				args: { name: frm.doc.name, ...values },
				freeze: true,
			}).then((r) => {
				d.hide();
				frappe.show_alert({ message: __("To'lov qabul qilindi: {0}", [r.message]), indicator: "green" });
				frm.reload_doc();
			});
		},
	});
	d.fields_dict.mode_of_payment.df.onchange = () => {
		const mop = d.get_value("mode_of_payment");
		if (!mop) return;
		frappe.call("carieer.carieer.doctype.kassa.kassa.get_kassa_info", { mode_of_payment: mop, company: frm.doc.company })
			.then((r) => d.set_value("valyuta", (r.message || {}).currency || ""));
	};
	d.show();
}
