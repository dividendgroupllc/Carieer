// Firmalararo sotuv (Click / Payme kabi): sotuvchi yuboradi -> xaridor qabul qiladi / rad etadi -> to'lov.
// Tugmalarni server hal qiladi (Sotuv.onload: can_accept, can_request_payment).
frappe.ui.form.on("Sotuv", {
	refresh(frm) {
		const doc = frm.doc;
		const o = doc.__onload || {};
		if (!doc.ichki_firma || doc.docstatus === 0) return;

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
