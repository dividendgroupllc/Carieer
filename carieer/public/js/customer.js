// Mijoz: INN / JShShIR bo'yicha bank rekvizitlari, direktor va manzilni Didox (soliq bazasi) dan to'ldirish.
frappe.ui.form.on("Customer", {
	refresh(frm) {
		frm.add_custom_button(__("Didox'dan to'ldirish"), () => {
			if (!frm.doc.tax_id) {
				frappe.msgprint(
					__("Avval «Rekvizitlar (Didox)» yorlig'ida INN / JShShIR ni kiriting")
				);
				frm.scroll_to_field("tax_id");
				return;
			}
			frappe
				.call({
					method: "carieer.didox.api.rekvizitlar",
					args: { inn: frm.doc.tax_id },
					freeze: true,
				})
				.then((r) => {
					const v = r.message || {};
					["bank_hisob", "mfo", "qqs_kodi", "direktor", "yuridik_manzil"].forEach(
						(f) => {
							if (v[f]) frm.set_value(f, v[f]);
						}
					);
					frappe.show_alert({
						message: __("Rekvizitlar to'ldirildi: {0}", [v.nomi || frm.doc.tax_id]),
						indicator: "green",
					});
				});
		});
	},
});
