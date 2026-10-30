// Посещение: «Xodimlarni qo'shish» - firmaning faol xodimlari jadvalga qo'shiladi (borlari takrorlanmaydi)
frappe.ui.form.on("Posesheniye", {
	refresh(frm) {
		frm.add_custom_button(__("Xodimlarni qo'shish"), () => {
			if (!frm.doc.company) {
				frappe.msgprint(__("Avval firmani tanlang"));
				return;
			}
			frappe
				.call("carieer.carieer.doctype.posesheniye.posesheniye.get_active_employees", {
					company: frm.doc.company,
				})
				.then((r) => {
					const have = new Set((frm.doc.xodimlar || []).map((d) => d.employee));
					let added = 0;
					(r.message || []).forEach((e) => {
						if (have.has(e.employee)) return;
						frm.add_child("xodimlar", e);
						added++;
					});
					frm.refresh_field("xodimlar");
					frappe.show_alert({ message: __("{0} ta xodim qo'shildi", [added]), indicator: "green" });
				});
		});
	},
});
