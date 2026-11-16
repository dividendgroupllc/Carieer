frappe.ui.form.on("Didox Hujjat", {
	refresh(frm) {
		frappe.require("/assets/carieer/js/didox.js", () => didox_hujjat_buttons(frm));
	},
});

function didox_hujjat_buttons(frm) {
	const doc = frm.doc;
	frm.add_custom_button(__("Yangilash"), () =>
		carieer.didox.call("yangilash", { hujjat: doc.name }).then(() => frm.reload_doc())
	);
	frm.add_custom_button(__("PDF"), () =>
		carieer.didox.call("pdf_yuklash", { hujjat: doc.name }).then((url) => {
			frm.reload_doc();
			window.open(url);
		})
	);
	if (doc.yonalish === "Chiquvchi" && doc.status_kod === 0) {
		frm.add_custom_button(__("Imzolab yuborish"), async () => {
			await carieer.didox.imzolash(doc.name, doc.company);
			frm.reload_doc();
		}).addClass("btn-primary");
		frm.add_custom_button(__("Qoralamani o'chirish"), () =>
			frappe.confirm(__("Didox'dagi qoralama o'chiriladi. Davom etasizmi?"), () =>
				carieer.didox
					.call("qoralamani_ochirish", { hujjat: doc.name })
					.then(() => frm.reload_doc())
			)
		);
	}

	// kiruvchi hujjat bizning imzoni kutmoqda (TTN va yangi ishonchnoma boshqa tartibda - common.py)
	const kutmoqda = [1, 2].includes(doc.status_kod) && !["041", "062"].includes(doc.hujjat_kodi);
	if (doc.yonalish === "Kiruvchi" && kutmoqda) {
		frm.add_custom_button(__("Qabul qilish (imzolash)"), async () => {
			await carieer.didox.qabul_qilish(doc.name, doc.company);
			frm.reload_doc();
		}).addClass("btn-primary");
		frm.add_custom_button(__("Rad etish"), async () => {
			await carieer.didox.rad_etish(doc.name, doc.company);
			frm.reload_doc();
		});
	}

	// kiruvchi hisob-faktura -> Приход (Purchase Invoice); shartlar prixod.py da ham tekshiriladi
	if (doc.yonalish === "Kiruvchi" && doc.hujjat_kodi === "002" && [1, 2, 3].includes(doc.status_kod)) {
		if (doc.purchase_invoice) {
			frm.add_custom_button(__("Приход"), () =>
				frappe.set_route("Form", "Purchase Invoice", doc.purchase_invoice)
			);
		} else {
			frm.add_custom_button(__("Приход yaratish"), () => carieer.didox.prixod(frm));
		}
	}

	if (doc.yonalish === "Chiquvchi" && doc.status_kod === 1) {
		frm.add_custom_button(__("Bekor qilish"), () =>
			frappe.confirm(
				__("Yuborilgan hujjat Didox'da bekor qilinadi (ERI bilan imzolanadi). Davom etasizmi?"),
				async () => {
					await carieer.didox.bekor_qilish(doc.name, doc.company);
					frm.reload_doc();
				}
			)
		);
	}
}
