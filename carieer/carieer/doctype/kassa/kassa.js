// Kassa (kirim / chiqim / o'tkazma): kassada hozir qancha pul bor va yozuvdan keyin qancha bo'ladi - saqlashdan OLDIN ko'rinadi.
frappe.ui.form.on("Kassa", {
	setup(frm) {
		// o'zimizning firmalar (Karer <-> Beton) bilan hisob-kitob faqat «Firmalararo to'lov» orqali: kontragent ro'yxatida ko'rinmaydi
		// kategoriya yozuv turiga mos: Kirim / Daromad - kirim moddalari, Chiqim / Xarajat - chiqim moddalari (aks holda hisob topilmaydi)
		frm.set_query("kategoriya", () => {
			const kirim = frm.doc.turi === "Kirim";
			const chiqim = frm.doc.turi === "Chiqim";
			if (!kirim && !chiqim) return {};
			return { filters: { turi: ["in", [kirim ? "Kirim" : "Chiqim", "Ikkalasi"]] } };
		});
		// «Hisob (modda)»: faqat yozuv turiga mos hisob (Daromad - Income, Xarajat - Expense, Dividend - Equity)
		frm.set_query("hisob", () => {
			const root = { Xarajat: "Expense", Daromad: "Income", Dividend: "Equity" }[frm.doc.party_type];
			return { filters: { company: frm.doc.company, is_group: 0, ...(root ? { root_type: root } : {}) } };
		});
		frm.set_query("party", () => {
			if (frm.doc.party_type === "Customer") return { filters: { is_internal_customer: 0 } };
			if (frm.doc.party_type === "Supplier") return { filters: { is_internal_supplier: 0 } };
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
				text = __("{0} kassasida hozir {1}. Kirimdan keyin: <b>{2}</b> (+{3} qo'shiladi). Faqat <b>{4}</b> kitobiga yoziladi - boshqa firmaga hech narsa yozilmaydi.", [
					d.mode_of_payment, m(r.balance), m(r.after), m(d.amount), d.company,
				]);
				color = "green";
			} else if (d.turi === "Chiqim" && r.after < -0.005 && !r.minus_ruxsat) {
				const have = Math.max(r.balance, 0);
				text = __("{0} kassasida {1} bor, {2} chiqarilmoqda - <b>pul yetmaydi</b>. Summani {1} gacha kamaytiring: qolgan <b>{3}</b> qarz bo'lib qoladi (Qarzlar bo'limidan keyin to'laysiz) yoki avval kassaga kirim qiling.", [
					d.mode_of_payment, m(have), m(d.amount), m(d.amount - have),
				]);
				color = "red";
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
