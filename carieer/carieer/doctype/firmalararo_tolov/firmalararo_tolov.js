// Firmalararo to'lov: to'lovchi to'laydi -> oluvchi firma pul qaysi kassaga tushganini tanlab tasdiqlaydi -> qarz yopiladi.
frappe.ui.form.on("Firmalararo Tolov", {
	setup(frm) {
		// faqat o'zimizning firmalar (Karer <-> Beton)
		frappe.call("carieer.api.internal_companies").then((r) => {
			const names = r.message || [];
			["tolovchi_firma", "oluvchi_firma"].forEach((f) =>
				frm.set_query(f, () => ({ filters: { name: ["in", names] } }))
			);
		});
		// aniq sotuv uchun to'lov: faqat shu to'lovchi firma qabul qilgan, hali qarzi bor sotuvlar
		frm.set_query("sotuv", () => ({
			filters: {
				ichki_firma: frm.doc.tolovchi_firma,
				company: frm.doc.oluvchi_firma,
				qabul_holati: "Qabul qilindi",
				outstanding_amount: [">", 0],
				docstatus: 1,
			},
		}));
		["tolovchi_kassa", "oluvchi_kassa"].forEach((f) => {
			const company_field = f === "tolovchi_kassa" ? "tolovchi_firma" : "oluvchi_firma";
			frm.set_query(f, () => ({
				query: "carieer.api.kassa_query",
				filters: { company: frm.doc[company_field] },
			}));
		});
	},

	sotuv(frm) {
		if (!frm.doc.sotuv) return;
		frappe.db.get_value("Sotuv", frm.doc.sotuv, ["outstanding_amount", "currency"]).then((r) => {
			const v = r.message || {};
			frm.set_value({ summa: v.outstanding_amount, valyuta: v.currency });
		});
	},
	summa: (frm) => show_kassa(frm),
	valyuta: (frm) => show_kassa(frm),
	tolovchi_kassa: (frm) => show_kassa(frm),

	refresh(frm) {
		const doc = frm.doc;
		if (doc.docstatus === 0) show_kassa(frm);
		if (doc.docstatus !== 1) return;
		if (doc.tasdiq_holati === "Kutilmoqda") {
			const can = (doc.__onload || {}).can_confirm;
			frm.dashboard.set_headline_alert(
				can
					? __("{0} to'ladi. Pul tushganini tekshiring va «Pulni qabul qildim» bosing - qarz shundan keyin yopiladi.", [doc.tolovchi_firma])
					: __("{0} pulni tasdiqlashi kutilmoqda: tasdiqlangandan keyin qarz yopiladi.", [doc.oluvchi_firma]),
				can ? "blue" : "orange"
			);
			if (can) {
				frm.add_custom_button(__("Pulni qabul qildim"), () => confirm_receipt(frm)).addClass("btn-primary");
			}
		} else if (doc.tasdiq_holati === "Tasdiqlandi") {
			frm.dashboard.set_headline_alert(
				__("{0} pulni qabul qildi: {1}", [doc.oluvchi_firma, doc.oluvchi_kassa]),
				"green"
			);
		}
	},
});

function confirm_receipt(frm) {
	const doc = frm.doc;
	const d = new frappe.ui.Dialog({
		title: __("Pul tushganini tasdiqlash"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p>${__("To'lovchi:")} <b>${doc.tolovchi_firma}</b><br>${__("Summa:")} <b>${format_currency(
					doc.summa,
					doc.valyuta
				)}</b><br>${__("Pul qaysi kassaga tushdi? (naqd UZS / naqd USD / karta / bank)")}</p>`,
			},
			{
				fieldname: "kassa",
				fieldtype: "Link",
				options: "Mode of Payment",
				label: __("Qaysi kassaga tushdi"),
				reqd: 1,
				default: doc.oluvchi_kassa,
				get_query: () => ({ query: "carieer.api.kassa_query", filters: { company: doc.oluvchi_firma } }),
				onchange() {
					const kassa = d.get_value("kassa");
					if (!kassa) return;
					frappe
						.xcall("carieer.carieer.doctype.firmalararo_tolov.firmalararo_tolov.kassa_preview", {
							company: doc.oluvchi_firma, kassa, summa: doc.summa, valyuta: doc.valyuta, kirim: 1,
						})
						.then((r) => {
							const m = (v) => format_currency(v, r.currency);
							d.set_df_property("info", "options", r.balance === undefined ? "" :
								`<p>${__("Kassada hozir")}: <b>${m(r.balance)}</b> &rarr; ${__("tasdiqdan keyin")}: <b style="color:green">${m(r.after)}</b> (+${m(r.amount)})</p>`);
						});
				},
			},
			{ fieldname: "info", fieldtype: "HTML" },
		],
		primary_action_label: __("Tasdiqlash"),
		primary_action(values) {
			d.hide();
			frm.call("tasdiqlash", { kassa: values.kassa }).then(() => frm.reload_doc());
		},
	});
	d.show();
	d.fields_dict.kassa.df.onchange();
}

// Kassada hozir qancha pul bor va to'lovdan keyin qancha qoladi - to'lashdan OLDIN ko'rinadi
function show_kassa(frm) {
	const d = frm.doc;
	if (d.docstatus !== 0 || !d.tolovchi_firma || !d.tolovchi_kassa || !flt(d.summa)) return;
	frappe
		.xcall("carieer.carieer.doctype.firmalararo_tolov.firmalararo_tolov.kassa_preview", {
			company: d.tolovchi_firma,
			kassa: d.tolovchi_kassa,
			summa: d.summa,
			valyuta: d.valyuta,
			posting_date: d.posting_date,
		})
		.then((r) => {
			if (!r || r.balance === undefined) return;
			const money = (v) => format_currency(v, r.currency);
			const minus = r.after < -0.005;
			frm.set_intro(
				minus && !r.minus_ruxsat
					? __("{0} kassasida {1} bor, {2} to'lanmoqda - <b>pul yetmaydi</b>. Summani {1} gacha kamaytiring: qolgan <b>{3}</b> qarz bo'lib qoladi (keyin Qarzlar bo'limidan to'laysiz).", [
							d.tolovchi_kassa, money(Math.max(r.balance, 0)), money(r.amount), money(r.amount - Math.max(r.balance, 0)),
					  ])
					: minus
					? __("{0} kassasida {1} bor, {2} to'lanmoqda. <b>{3} qarzga kiradi</b>: kassa <b>{4}</b> (minus) bo'ladi.", [
							d.tolovchi_kassa, money(r.balance), money(r.amount), money(-r.after), money(r.after),
					  ])
					: __("{0} kassasida {1} bor. To'lovdan keyin: <b>{2}</b>.", [d.tolovchi_kassa, money(r.balance), money(r.after)]),
				minus ? "red" : "blue"
			);
		});
}
