// Kassa (kirim / chiqim / o'tkazma): kassada hozir qancha pul bor va yozuvdan keyin qancha bo'ladi - saqlashdan OLDIN ko'rinadi.
frappe.ui.form.on("Kassa", {
	setup(frm) {
		// o'zimizning firmalar (Karer <-> Beton) bilan hisob-kitob faqat «Firmalararo to'lov» orqali: kontragent ro'yxatida ko'rinmaydi
		frm.set_query("party", () => {
			if (frm.doc.party_type === "Customer") return { filters: { is_internal_customer: 0 } };
			if (frm.doc.party_type === "Supplier") return { filters: { is_internal_supplier: 0 } };
		});
	},
	refresh: (frm) => kassa_intro(frm),
	amount: (frm) => kassa_intro(frm),
	mode_of_payment: (frm) => kassa_intro(frm),
	turi: (frm) => kassa_intro(frm),
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
				text = __("{0} kassasida hozir {1}. Kirimdan keyin: <b>{2}</b> (+{3} qo'shiladi). Faqat <b>{4}</b> kitobiga yoziladi - boshqa firmaga hech narsa yozilmaydi.", [
					d.mode_of_payment, m(r.balance), m(r.after), m(d.amount), d.company,
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
			frm.set_intro(text, color);
		});
}
