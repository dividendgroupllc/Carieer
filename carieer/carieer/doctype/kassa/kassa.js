// Kassa: kirim / chiqim / o'tkazma (Armada loyihasidagi Kassa andozasi)

frappe.ui.form.on("Kassa", {
	setup(frm) {
		frm.set_query("mode_of_payment_to", () => ({
			filters: frm.doc.mode_of_payment ? { name: ["!=", frm.doc.mode_of_payment] } : {},
		}));
		frm.set_query("hisob", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				root_type: { Dividend: "Equity", Daromad: "Income" }[frm.doc.party_type] || "Expense",
			},
		}));
		frm.set_query("cost_center", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("kategoriya", () => ({
			filters: { turi: ["in", ["Ikkalasi", frm.doc.turi === "Kirim" ? "Kirim" : "Chiqim"]] },
		}));
	},

	onload(frm) {
		if (frm.is_new() && frm.doc.company && !frm.doc.mode_of_payment) frm.trigger("company");
	},

	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.linked_entry) {
			frm.add_custom_button(__(frm.doc.linked_doctype), () =>
				frappe.set_route("Form", frm.doc.linked_doctype, frm.doc.linked_entry), __("Ko'rish"));
		}
		if (frm.doc.docstatus === 0) {
			frm.trigger("update_kassa");
			frm.trigger("update_kassa_to");
		}
		frm.trigger("party_type_options");
	},

	company(frm) {
		if (!frm.doc.company) return;
		frappe.call("carieer.utils.get_firma_defaults", { company: frm.doc.company }).then((r) => {
			const d = r.message || {};
			if (d.mode_of_payment) frm.set_value("mode_of_payment", d.mode_of_payment);
			else frm.trigger("update_kassa");
		});
		frm.set_value({ party: "", hisob: "", cost_center: "" });
	},

	turi(frm) {
		frm.set_value({ party_type: "", party: "", party_name: "", hisob: "", mode_of_payment_to: "" });
		frm.trigger("party_type_options");
	},

	// Dividend faqat chiqim bo'ladi
	party_type_options(frm) {
		const opts = ["", "Customer", "Supplier", "Employee", "Shareholder", "Xarajat"];
		if (frm.doc.turi === "Kirim") opts.push("Daromad"); // boshqa tushum (Прочие доходы)
		if (frm.doc.turi === "Chiqim") opts.push("Dividend");
		frm.set_df_property("party_type", "options", opts.join("\n"));
	},

	mode_of_payment: (frm) => frm.trigger("update_kassa"),
	mode_of_payment_to: (frm) => frm.trigger("update_kassa_to"),

	update_kassa(frm) {
		kassa_info(frm, frm.doc.mode_of_payment, ["kassa_hisobi", "kassa_valyutasi", "qoldiq"]);
	},

	update_kassa_to(frm) {
		kassa_info(frm, frm.doc.mode_of_payment_to, ["kassa_hisobi_to", "kassa_valyutasi_to", "qoldiq_to"]);
	},

	party_type(frm) {
		frm.set_value({ party: "", party_name: "", hisob: "", cost_center: "" }).then(() => {
			if (["Xarajat", "Daromad"].includes(frm.doc.party_type)) frm.trigger("kategoriya");
		});
		if (frm.doc.party_type === "Dividend" && frm.doc.company) {
			// Standart dividend hisobi
			frappe.db.get_value("Account", { company: frm.doc.company, account_name: "Dividends Paid", is_group: 0 }, "name")
				.then((r) => r.message && r.message.name && frm.set_value("hisob", r.message.name));
		}
	},

	// Jadvaldagi kabi: kategoriya tanlansa hisob (modda) o'zi qo'yiladi
	kategoriya(frm) {
		const root_type = { Xarajat: "Expense", Daromad: "Income" }[frm.doc.party_type];
		if (!frm.doc.kategoriya || !frm.doc.company || !root_type) return;
		frappe.call("carieer.utils.get_kategoriya_account", {
			kategoriya: frm.doc.kategoriya, company: frm.doc.company, root_type,
		}).then((r) => {
			if (r.message) frm.set_value("hisob", r.message);
			else frappe.show_alert({ message: __("{0} uchun hisob topilmadi, qo'lda tanlang", [frm.doc.kategoriya]), indicator: "orange" });
		});
	},

	party(frm) {
		const fields = { Customer: "customer_name", Supplier: "supplier_name", Employee: "employee_name", Shareholder: "title" };
		const f = fields[frm.doc.party_type];
		if (!frm.doc.party || !f) return frm.set_value("party_name", "");
		frappe.db.get_value(frm.doc.party_type, frm.doc.party, f).then((r) =>
			frm.set_value("party_name", (r.message && r.message[f]) || frm.doc.party));
	},
});

function kassa_info(frm, mode_of_payment, [account_f, currency_f, balance_f]) {
	if (!mode_of_payment || !frm.doc.company) {
		frm.set_value({ [account_f]: "", [currency_f]: "", [balance_f]: 0 });
		return;
	}
	frappe.call("carieer.carieer.doctype.kassa.kassa.get_kassa_info", {
		mode_of_payment, company: frm.doc.company,
	}).then((r) => {
		const d = r.message || {};
		if (!d.account) {
			frappe.msgprint(__("{0} to'lov turida {1} firmasi uchun kassa hisobi yo'q", [mode_of_payment, frm.doc.company]));
		}
		frm.set_value({ [account_f]: d.account || "", [currency_f]: d.currency || "", [balance_f]: d.balance || 0 });
	});
}
