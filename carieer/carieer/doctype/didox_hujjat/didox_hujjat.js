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
}
