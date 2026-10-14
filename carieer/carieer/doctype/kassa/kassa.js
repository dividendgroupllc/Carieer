// Kassa (kirim / chiqim / o'tkazma / konvertatsiya): kassada hozir qancha pul bor va yozuvdan keyin qancha bo'ladi - saqlashdan OLDIN ko'rinadi.
frappe.ui.form.on("Kassa", {
	setup(frm) {
		// kategoriya yozuv turiga mos: Kirim / Daromad - kirim moddalari, Chiqim / Xarajat - chiqim moddalari (aks holda hisob topilmaydi)
		frm.set_query("kategoriya", () => {
			const kirim = frm.doc.turi === "Kirim";
			const chiqim = frm.doc.turi === "Chiqim";
			if (!kirim && !chiqim) return {};
			return { filters: { turi: ["in", [kirim ? "Kirim" : "Chiqim", "Ikkalasi"]] } };
		});
		// «Hisob (modda)»: faqat yozuv turiga mos hisob (Daromad - Income, Xarajat - Expense, Dividend - Equity)
		frm.set_query("hisob", () => {
			const root = { Xarajat: "Expense", Daromad: "Income", Dividend: "Equity", Kapital: "Equity" }[frm.doc.party_type];
			return { filters: { company: frm.doc.company, is_group: 0, ...(root ? { root_type: root } : {}) } };
		});
	},
	refresh: (frm) => kassa_intro(frm),
	amount: (frm) => kassa_intro(frm),
	mode_of_payment: (frm) => kassa_intro(frm),
	party_type(frm) {
		if (frm.doc.hisob) frm.set_value("hisob", null); // oldingi tur hisobi yangi turga mos kelmaydi
	},
	kategoriya(frm) {
		if (frm.doc.hisob) frm.set_value("hisob", null); // hisob kategoriyadan o'zi topiladi
	},
	turi(frm) {
		if (frm.doc.hisob) frm.set_value("hisob", null);
		if (frm.doc.kategoriya) frm.set_value("kategoriya", null); // oldingi tur kategoriyasi yangi turga mos kelmaydi
		kassa_intro(frm);
	},
	company: (frm) => kassa_intro(frm),
});

function kassa_intro(frm) {
	const d = frm.doc;
	if (d.docstatus !== 0 || !d.company || !d.mode_of_payment || !flt(d.amount)) return;
	frappe
		.xcall("carieer.carieer.doctype.kassa.kassa.kassa_holati", {
			company: d.company,
			kassa: d.mode_of_payment,
			summa: d.amount,
			turi: d.turi,
		})
		.then((r) => {
			if (!r || r.balance === undefined) return;
			const m = (v) => format_currency(v, r.currency);
			let text, color = "blue";
			if (d.turi === "Kirim") {
				text = __("{0} kassasida hozir {1}. Kirimdan keyin: <b>{2}</b> (+{3} qo'shiladi).", [
					d.mode_of_payment, m(r.balance), m(r.after), m(d.amount),
				]);
				color = "green";
			} else if (d.turi === "Chiqim" && r.after < -0.005) {
				text = __("{0} kassasida {1} bor, {2} chiqarilmoqda. <b>{3} qarzga kiradi</b>: kassa <b>{4}</b> (minus) bo'ladi. Keyingi kirimlar bilan yopiladi.", [
					d.mode_of_payment, m(r.balance), m(d.amount), m(-r.after), m(r.after),
				]);
				color = "orange";
			} else {
				text = __("{0} kassasida hozir {1}. Yozuvdan keyin: <b>{2}</b>.", [d.mode_of_payment, m(r.balance), m(r.after)]);
			}
			if (r.jami !== undefined) {
				text += " " + __("Barcha kassalar jami: {0} → {1}.", [
					format_currency(r.jami, r.base_currency), format_currency(r.jami_after, r.base_currency),
				]);
			}
			frm.set_intro(text, color);
		});
}
