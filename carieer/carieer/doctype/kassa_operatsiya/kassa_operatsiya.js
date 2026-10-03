const OTKAZMA = "Kassalar orasida o'tkazma";

frappe.ui.form.on("Kassa Operatsiya", {
	setup(frm) {
		frm.set_query("modda", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				root_type: frm.doc.turi && frm.doc.turi.startsWith("Kirim") ? "Income" : "Expense",
			},
		}));
		frm.set_query("vehicle", () => ({ filters: { company: frm.doc.company } }));
	},

	onload(frm) {
		if (frm.is_new() && frm.doc.company && !frm.doc.mode_of_payment) {
			frappe.call("carieer.utils.get_firma_defaults", { company: frm.doc.company }).then((r) => {
				if (r.message && r.message.mode_of_payment) frm.set_value("mode_of_payment", r.message.mode_of_payment);
			});
		}
	},

	refresh(frm) {
		if (frm.doc.journal_entry) {
			frm.add_custom_button(__("Journal Entry"), () =>
				frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry), __("Ko'rish"));
		}
		frm.toggle_reqd("modda", frm.doc.turi !== OTKAZMA);
		frm.toggle_reqd("qabul_kassa", frm.doc.turi === OTKAZMA);
	},

	turi(frm) {
		frm.set_value("modda", "");
		frm.toggle_reqd("modda", frm.doc.turi !== OTKAZMA);
		frm.toggle_reqd("qabul_kassa", frm.doc.turi === OTKAZMA);
	},

	company: (frm) => load_kassa(frm),
	mode_of_payment: (frm) => load_kassa(frm),
	posting_date: (frm) => load_kassa(frm),
});

function load_kassa(frm) {
	if (!frm.doc.company || !frm.doc.mode_of_payment || frm.doc.docstatus !== 0) return;
	frappe
		.call("carieer.carieer.doctype.kassa_operatsiya.kassa_operatsiya.get_kassa_info", {
			mode_of_payment: frm.doc.mode_of_payment,
			company: frm.doc.company,
			date: frm.doc.posting_date,
		})
		.then((r) => {
			const d = r.message || {};
			frm.set_value("kassa_hisobi", d.account);
			frm.set_value("currency", d.currency);
			frm.set_value("kassa_qoldigi", d.balance);
		});
}
