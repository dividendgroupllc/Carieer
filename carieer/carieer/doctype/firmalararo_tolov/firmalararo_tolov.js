// Firmalararo To'lov: bir firma ikkinchisiga qarzini to'laydi. Submit -> ikkala firmada Payment Entry.
// To'lov USD da bo'lsa: summa × kurs = so'm; so'm kassadan ayriladi, qarz so'mda kamayadi.

frappe.ui.form.on("Firmalararo Tolov", {
	setup(frm) {
		frm.set_query("tolovchi_firma", () => ({ filters: { name: ["!=", frm.doc.oluvchi_firma || ""] } }));
		frm.set_query("oluvchi_firma", () => ({ filters: { name: ["!=", frm.doc.tolovchi_firma || ""] } }));
		for (const [kassa, firma] of [["tolovchi_kassa", "tolovchi_firma"], ["oluvchi_kassa", "oluvchi_firma"]]) {
			frm.set_query(kassa, () => ({
				query: "carieer.carieer.doctype.firmalararo_tolov.firmalararo_tolov.kassa_query",
				filters: { company: frm.doc[firma] },
			}));
		}
	},
	onload(frm) {
		if (!frm.is_new()) return;
		// Firma xodimi odatda o'z firmasi qarzini to'laydi
		if (!frm.doc.tolovchi_firma && frappe.boot.carieer_firma) {
			frm.set_value("tolovchi_firma", frappe.defaults.get_user_default("Company"));
		}
		if (!frm.doc.valyuta) frm.set_value("valyuta", "UZS");
	},
	refresh: (frm) => show_qarz(frm),
	tolovchi_firma(frm) {
		frm.set_value("tolovchi_kassa", "");
		show_qarz(frm);
	},
	oluvchi_firma(frm) {
		frm.set_value("oluvchi_kassa", "");
		show_qarz(frm);
	},
	tolovchi_kassa: (frm) => recalc(frm),
	oluvchi_kassa: (frm) => recalc(frm),
	summa: (frm) => recalc(frm),
	kurs: (frm) => recalc(frm),
	posting_date: (frm) => recalc(frm),
	valyuta(frm) {
		frm.set_value("kurs", 0);
		recalc(frm);
	},
});

function recalc(frm) {
	const d = frm.doc;
	if (d.docstatus !== 0 || !d.tolovchi_firma || !d.oluvchi_firma || !d.tolovchi_kassa || !d.oluvchi_kassa || !d.valyuta) return;
	frappe.call({
		method: "carieer.carieer.doctype.firmalararo_tolov.firmalararo_tolov.get_summalar",
		args: {
			tolovchi_firma: d.tolovchi_firma, tolovchi_kassa: d.tolovchi_kassa,
			oluvchi_firma: d.oluvchi_firma, oluvchi_kassa: d.oluvchi_kassa,
			valyuta: d.valyuta, summa: flt(d.summa), kurs: flt(d.kurs), posting_date: d.posting_date,
		},
	}).then((r) => {
		const v = r.message || {};
		// set_value kurs -> recalc qayta chaqirilmasin
		frappe.model.set_value(d.doctype, d.name, v, null, true);
		frm.refresh_fields();
	});
}

function show_qarz(frm) {
	const wrapper = frm.get_field("qarz_html").$wrapper;
	wrapper.empty();
	if (!frm.doc.tolovchi_firma || !frm.doc.oluvchi_firma) return;
	frappe.call("carieer.carieer.doctype.firmalararo_tolov.firmalararo_tolov.get_qarz", {
		tolovchi_firma: frm.doc.tolovchi_firma, oluvchi_firma: frm.doc.oluvchi_firma,
	}).then((r) => {
		const d = r.message || {};
		let text;
		if (flt(d.qarz) > 0) {
			text = __("{0} {1}dan <b>{2}</b> qarz", [frm.doc.tolovchi_firma, frm.doc.oluvchi_firma, d.text]);
		} else if (flt(d.qarz) < 0) {
			text = __("{0} {1}dan qarz emas, aksincha {1} {0}dan <b>{2}</b> qarz", [frm.doc.tolovchi_firma, frm.doc.oluvchi_firma, d.text]);
		} else {
			text = __("Qarz yo'q");
		}
		wrapper.html(`<div style="font-size:14px;padding:6px 0">${text}
			<a class="ml-3" href="/desk/query-report/Firmalararo Qarzlar">${__("Batafsil")}</a></div>`);
	});
}
