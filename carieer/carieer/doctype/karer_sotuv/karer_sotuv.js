// Karer Sotuv - karer postidagi sotuv formasi

frappe.ui.form.on("Karer Sotuv", {
	setup(frm) {
		frm.set_query("warehouse", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("item_code", () => ({ filters: { is_stock_item: 1, disabled: 0, is_sales_item: 1 } }));
		frm.set_query("vehicle", () => ({ filters: { company: frm.doc.company } }));
		frm.set_query("uom", () => {
			if (!frm.doc.item_code) return {};
			return {
				query: "erpnext.controllers.queries.get_item_uom_query",
				filters: { item_code: frm.doc.item_code },
			};
		});
	},

	onload(frm) {
		if (frm.is_new() && frm.doc.company && !frm.doc.warehouse) {
			frm.trigger("company");
		}
	},

	refresh(frm) {
		frm.page.set_indicator(__(frm.doc.status), status_color(frm.doc.status));

		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.page.set_primary_action(__("Yakunlash (Submit)"), () => frm.savesubmit());
		}

		if (frm.doc.docstatus === 1 && flt(frm.doc.outstanding_amount) > 0) {
			frm.add_custom_button(__("To'lov qabul qilish"), () => payment_dialog(frm)).addClass("btn-primary");
		}
		if (frm.doc.sales_invoice) {
			frm.add_custom_button(__("Sales Invoice"), () => frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice), __("Ko'rish"));
			frm.add_custom_button(__("To'lovlar"), () =>
				frappe.set_route("List", "Payment Entry", { reference_no: frm.doc.name }), __("Ko'rish"));
		}
	},

	company(frm) {
		if (!frm.doc.company) return;
		frappe.call("carieer.utils.get_firma_defaults", { company: frm.doc.company }).then((r) => {
			const d = r.message || {};
			if (d.sotuv_ombori) frm.set_value("warehouse", d.sotuv_ombori);
			if (d.mode_of_payment && !frm.doc.mode_of_payment) frm.set_value("mode_of_payment", d.mode_of_payment);
			frm.trigger("currency");
		});
	},

	item_code(frm) {
		if (!frm.doc.item_code) return;
		frappe.db.get_value("Item", frm.doc.item_code, ["stock_uom", "sales_uom"]).then((r) => {
			const it = r.message || {};
			frm.set_value("uom", it.sales_uom || it.stock_uom);
		});
	},

	currency(frm) {
		const cc = frm.doc.company && erpnext.get_currency(frm.doc.company);
		if (!frm.doc.currency || !cc) return;
		if (frm.doc.currency === cc) {
			frm.set_value("conversion_rate", 1);
		} else {
			frappe.call("carieer.utils.get_exchange_rate_for", {
				from_currency: frm.doc.currency,
				to_currency: cc,
				date: frm.doc.posting_date,
			}).then((r) => frm.set_value("conversion_rate", r.message));
		}
	},

	brutto: (frm) => calc_net(frm),
	tara: (frm) => calc_net(frm),
	qty: (frm) => calc_amount(frm),
	rate: (frm) => calc_amount(frm),
	conversion_rate: (frm) => calc_amount(frm),

	paid_amount(frm) {
		if (flt(frm.doc.paid_amount) > flt(frm.doc.amount)) {
			frappe.msgprint(__("To'lov jami summadan katta bo'lishi mumkin emas"));
			frm.set_value("paid_amount", frm.doc.amount);
		}
	},
});

function calc_net(frm) {
	if (flt(frm.doc.brutto) && flt(frm.doc.tara)) {
		frm.set_value("qty", flt(frm.doc.brutto) - flt(frm.doc.tara));
	}
}

function calc_amount(frm) {
	const amount = flt(frm.doc.qty) * flt(frm.doc.rate);
	frm.set_value("amount", amount);
	frm.set_value("base_amount", amount * flt(frm.doc.conversion_rate || 1));
	frm.set_value("outstanding_amount", amount - flt(frm.doc.total_paid));
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
		title: __("To'lov qabul qilish"),
		fields: [
			{ fieldname: "mode_of_payment", fieldtype: "Link", options: "Mode of Payment", label: __("To'lov turi (kassa)"), reqd: 1, default: frm.doc.mode_of_payment },
			{ fieldname: "amount", fieldtype: "Currency", label: __("Summa") + ` (${frm.doc.currency})`, reqd: 1, default: frm.doc.outstanding_amount },
			{ fieldtype: "HTML", options: `<p class="text-muted">${__("Qarz")}: <b>${format_currency(frm.doc.outstanding_amount, frm.doc.currency)}</b></p>` },
		],
		primary_action_label: __("Qabul qilish"),
		primary_action(values) {
			frappe.call({
				method: "carieer.carieer.doctype.karer_sotuv.karer_sotuv.tolov_qabul_qilish",
				args: { name: frm.doc.name, amount: values.amount, mode_of_payment: values.mode_of_payment },
				freeze: true,
				callback(r) {
					if (!r.exc) {
						d.hide();
						frappe.show_alert({ message: __("To'lov qabul qilindi: {0}", [r.message]), indicator: "green" });
						frm.reload_doc();
					}
				},
			});
		},
	});
	d.show();
}
