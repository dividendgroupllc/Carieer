// Prixod OS ("Приход ОС"): asosiy vositalar kirimi

frappe.ui.form.on("Prixod OS", {
	setup(frm) {
		frm.set_query("hisob", () => ({
			filters: { company: frm.doc.company, is_group: 0, root_type: "Asset", account_type: "Fixed Asset" },
		}));
		frm.set_query("kredit_hisob", () => ({
			filters: { company: frm.doc.company, is_group: 0, root_type: ["in", ["Equity", "Liability"]] },
		}));
	},

	onload(frm) {
		if (frm.is_new() && frm.doc.company) frm.trigger("company");
	},

	refresh(frm) {
		if (frm.doc.journal_entry) {
			frm.add_custom_button(__("Journal Entry"), () =>
				frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry), __("Ko'rish"));
		}
	},

	company(frm) {
		if (!frm.doc.company || frm.doc.docstatus !== 0) return;
		if (!frm.doc.currency) frm.set_value("currency", erpnext.get_currency(frm.doc.company));
		frappe.call("carieer.carieer.doctype.prixod_os.prixod_os.get_default_accounts", { company: frm.doc.company })
			.then((r) => {
				const d = r.message || {};
				if (!frm.doc.hisob) frm.set_value("hisob", d.hisob || "");
				if (!frm.doc.supplier && !frm.doc.kredit_hisob) frm.set_value("kredit_hisob", d.kredit_hisob || "");
			});
	},

	supplier(frm) {
		if (frm.doc.supplier) frm.set_value("kredit_hisob", "");
		else frm.trigger("company");
	},

	currency(frm) {
		const cc = frm.doc.company && erpnext.get_currency(frm.doc.company);
		if (!frm.doc.currency || !cc) return;
		if (frm.doc.currency === cc) return frm.set_value("kurs", 1);
		frappe.call("carieer.utils.get_exchange_rate_for", { from_currency: frm.doc.currency, to_currency: cc, date: frm.doc.sana })
			.then((r) => frm.set_value("kurs", r.message));
	},

	qty: (frm) => calc(frm),
	rate: (frm) => calc(frm),
	kurs: (frm) => calc(frm),
});

function calc(frm) {
	const amount = flt(frm.doc.qty) * flt(frm.doc.rate);
	frm.set_value("amount", amount);
	frm.set_value("base_amount", amount * flt(frm.doc.kurs || 1));
}
