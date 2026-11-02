// Kassa (Приход / Расход / Перемещение / Конвертация): kassada hozir qancha pul bor va yozuvdan keyin qancha bo'ladi -
// saqlashdan OLDIN ko'rinadi.
// «Тип контрагента» (Клиент, Поставщик ...) -> ERPNext doctype (yashirin party_doctype): «Контрагент» shu doctype'dan tanlanadi.
const KASSA_PARTY_DOCTYPE = { Клиент: "Customer", Поставщик: "Supplier", "Прочие лица": "Supplier", Сотрудник: "Employee" };

frappe.ui.form.on("Kassa", {
	setup(frm) {
		// kategoriya yozuv turiga mos: Приход - kirim moddalari, Расход - chiqim moddalari (aks holda hisob topilmaydi)
		frm.set_query("kategoriya", () => {
			if (!["Приход", "Расход"].includes(frm.doc.turi)) return {};
			return { filters: { turi: ["in", [frm.doc.turi, "Оба"]] } };
		});
		// schyot (Mode of Payment): faqat shu firmada hisobi bor va yoqilganlari
		const schyot_query = () => ({
			filters: [
				["Mode of Payment", "enabled", "=", 1],
				["Mode of Payment Account", "company", "=", frm.doc.company || ""],
			],
		});
		frm.set_query("mode_of_payment", schyot_query);
		frm.set_query("mode_of_payment_to", schyot_query);
		// «Статья»: faqat yozuv turiga mos hisob (Доход - Income, Статья расхода - Expense, Дивиденд / Капитал - Equity)
		frm.set_query("hisob", () => {
			const root = { "Статья расхода": "Expense", Доход: "Income", Дивиденд: "Equity", Капитал: "Equity" }[frm.doc.party_type];
			return { filters: { company: frm.doc.company, is_group: 0, ...(root ? { root_type: root } : {}) } };
		});
	},
	refresh: (frm) => kassa_intro(frm),
	amount: (frm) => kassa_intro(frm),
	mode_of_payment: (frm) => kassa_intro(frm),
	party_type(frm) {
		if (frm.doc.hisob) frm.set_value("hisob", null); // oldingi tur hisobi yangi turga mos kelmaydi
		const doctype = KASSA_PARTY_DOCTYPE[frm.doc.party_type] || null;
		if (doctype !== frm.doc.party_doctype) {
			frm.set_value("party_doctype", doctype);
			if (frm.doc.party) frm.set_value("party", null);
		}
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
			if (d.turi === "Приход") {
				text = __("На счёте «{0}» сейчас {1}. После прихода: <b>{2}</b> (+{3}).", [
					d.mode_of_payment, m(r.balance), m(r.after), m(d.amount),
				]);
				color = "green";
			} else if (d.turi !== "Приход" && r.after < -0.005) {
				text = __("На счёте «{0}» {1}, расход {2}. <b>Не хватает {3}</b>: остаток станет <b>{4}</b> (минус) и закроется следующими приходами.", [
					d.mode_of_payment, m(r.balance), m(d.amount), m(-r.after), m(r.after),
				]);
				color = "orange";
			} else {
				text = __("На счёте «{0}» сейчас {1}. После записи: <b>{2}</b>.", [d.mode_of_payment, m(r.balance), m(r.after)]);
			}
			if (r.jami !== undefined) {
				text += " " + __("Итого по всем счетам: {0} → {1}.", [
					format_currency(r.jami, r.base_currency), format_currency(r.jami_after, r.base_currency),
				]);
			}
			frm.set_intro(text, color);
		});
}
