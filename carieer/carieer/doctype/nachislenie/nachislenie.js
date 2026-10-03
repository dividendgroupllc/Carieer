// Nachislenie ("Начисление карьер"): xizmat sotish / sotib olish bo'yicha hisoblash

frappe.ui.form.on("Nachislenie", {
	setup(frm) {
		frm.set_query("hisob", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				root_type: frm.doc.turi === "Закуп услуга" ? "Expense" : "Income",
			},
		}));
		frm.set_query("cost_center", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
	},

	onload(frm) {
		if (frm.is_new()) {
			if (!frm.doc.currency && frm.doc.company) frm.set_value("currency", erpnext.get_currency(frm.doc.company));
			frm.trigger("turi");
		}
	},

	refresh(frm) {
		if (frm.doc.journal_entry) {
			frm.add_custom_button(__("Journal Entry"), () => frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry), __("Ko'rish"));
			frm.add_custom_button(__("Akt sverka"), () => frappe.set_route("query-report", "Akt Sverka", {
				company: frm.doc.company, party_type: frm.doc.party_type, party: frm.doc.party,
			}), __("Ko'rish"));
		}
	},

	company(frm) {
		if (frm.doc.company) frm.set_value("currency", erpnext.get_currency(frm.doc.company));
		frm.trigger("turi");
	},

	turi(frm) {
		frm.set_value("party_type", frm.doc.turi === "Закуп услуга" ? "Supplier" : "Customer");
		frm.trigger("set_hisob");
	},

	// Kategoriya tanlansa shu kategoriya hisobi (modda) qo'yiladi, bo'lmasa firmaning standart hisobi
	kategoriya: (frm) => frm.trigger("set_hisob"),

	set_hisob(frm) {
		if (!frm.doc.company || !frm.doc.turi || frm.doc.docstatus !== 0) return;
		frappe.call("carieer.carieer.doctype.nachislenie.nachislenie.get_default_account", {
			company: frm.doc.company, turi: frm.doc.turi, kategoriya: frm.doc.kategoriya || null,
		}).then((r) => frm.set_value("hisob", r.message || ""));
	},

	party_type(frm) {
		frm.set_value({ party: "", party_name: "" });
	},

	party(frm) {
		const f = { Customer: "customer_name", Supplier: "supplier_name" }[frm.doc.party_type];
		if (!frm.doc.party || !f) return frm.set_value("party_name", "");
		frappe.db.get_value(frm.doc.party_type, frm.doc.party, f).then((r) =>
			frm.set_value("party_name", (r.message && r.message[f]) || frm.doc.party));
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
