// Firmalararo sotuv (Click / Payme kabi): sotuvchi yuboradi -> xaridor qabul qiladi / rad etadi -> to'lov.
// Tugmalarni server hal qiladi (Sotuv.onload: can_accept, can_request_payment).
frappe.ui.form.on("Sotuv", {
	setup(frm) {
		// firma o'ziga sota olmaydi: o'z ichki mijozi (masalan Beton -> «Beton Zavod») ro'yxatda ko'rinmasin
		frm.set_query("customer", () => ({ filters: { represents_company: ["!=", frm.doc.company || ""] } }));
	},
	refresh(frm) {
		const doc = frm.doc;
		const o = doc.__onload || {};
		if (!doc.ichki_firma || doc.docstatus === 0) return;

		if (o.can_pay) {
			frm.add_custom_button(__("Qarzni to'lash"), () =>
				frappe
					.xcall("carieer.carieer.doctype.sotuv.sotuv.qarzni_tolash", { name: doc.name })
					.then((ft) => frappe.set_route("Form", "Firmalararo Tolov", ft))
			).addClass("btn-primary");
		}

		if (doc.qabul_holati === "Kutilmoqda") {
			frm.dashboard.set_headline_alert(
				o.can_accept
					? __("{0} sizga tovar yubordi. Qabul qiling (qarzga yoki shu zahoti to'lab) yoki rad eting.", [doc.company])
					: __("{0} tasdig'i kutilmoqda: qabul qilgandan keyin tovar uning omboriga kiradi va qarz yoziladi.", [doc.ichki_firma]),
				"blue"
			);
		} else if (doc.qabul_holati === "Rad etildi") {
			frm.dashboard.set_headline_alert(
				__("{0} rad etdi: {1}", [doc.ichki_firma, doc.rad_sababi || ""]),
				"red"
			);
		}

		if (o.can_accept) {
			frm.add_custom_button(__("✔ Qabul qilish"), () => accept(frm)).addClass("btn-primary");
			frm.add_custom_button(__("✖ Rad etish"), () => reject(frm));
		}
		if (o.can_request_payment) {
			frm.add_custom_button(__("To'lov so'rash"), () =>
				frappe
					.call("carieer.carieer.doctype.sotuv.sotuv.tolov_sorash", { name: doc.name })
					.then((r) => {
						frappe.show_alert({
							message: __("To'lov so'rovi yuborildi: {0}", [r.message]),
							indicator: "green",
						});
						frappe.set_route("Form", "Firmalararo Tolov", r.message);
					})
			);
		}
	},
});

function accept(frm) {
	const doc = frm.doc;
	const d = new frappe.ui.Dialog({
		title: __("Qabul qilish: {0}", [doc.name]),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p>${__("Tovar {0} omboriga kiradi, {1} ga qarz yoziladi: <b>{2}</b>", [
					doc.ichki_firma,
					doc.company,
					format_currency(doc.amount, doc.currency),
				])}</p>`,
			},
			{
				fieldname: "tolov",
				fieldtype: "Select",
				label: __("To'lov"),
				options: [__("Qarzga (keyin to'layman)"), __("Hozir to'layman")].join("\n"),
				default: __("Qarzga (keyin to'layman)"),
			},
			{
				fieldname: "kassa",
				fieldtype: "Link",
				options: "Mode of Payment",
				label: __("Qaysi kassadan"),
				depends_on: `eval:doc.tolov=="${__("Hozir to'layman")}"`,
				get_query: () => ({ filters: { firma: doc.ichki_firma, enabled: 1 } }),
			},
			{
				fieldname: "summa",
				fieldtype: "Currency",
				label: __("Summa"),
				default: doc.amount,
				depends_on: `eval:doc.tolov=="${__("Hozir to'layman")}"`,
			},
		],
		primary_action_label: __("Qabul qilish"),
		primary_action(values) {
			const pay = values.tolov === __("Hozir to'layman");
			if (pay && (!values.kassa || !values.summa)) {
				frappe.msgprint(__("Kassa va summani kiriting"));
				return;
			}
			d.hide();
			frappe
				.call({
					method: "carieer.carieer.doctype.sotuv.sotuv.qabul_qilish",
					args: { name: doc.name, kassa: pay ? values.kassa : null, summa: pay ? values.summa : 0 },
					freeze: true,
					freeze_message: __("Tovar qabul qilinmoqda..."),
				})
				.then(() => {
					frappe.show_alert({ message: __("Qabul qilindi"), indicator: "green" });
					frm.reload_doc();
				});
		},
	});
	d.show();
}

function reject(frm) {
	frappe.prompt(
		{ fieldname: "sabab", fieldtype: "Small Text", label: __("Rad etish sababi"), reqd: 1 },
		(values) =>
			frappe
				.call({
					method: "carieer.carieer.doctype.sotuv.sotuv.rad_etish",
					args: { name: frm.doc.name, sabab: values.sabab },
					freeze: true,
				})
				.then(() => frm.reload_doc()),
		__("Rad etish: {0}", [frm.doc.name]),
		__("Rad etish")
	);
}

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
