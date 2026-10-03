// GPS Malumot ro'yxati: nuqtalarni tez o'chirish (qurilma va/yoki sana bo'yicha)

frappe.listview_settings["GPS Malumot"] = {
	onload(listview) {
		if (!frappe.user.has_role(["System Manager", "Karer Menejer", "Beton Menejer"])) return;
		listview.page.add_inner_button(__("Tozalash"), () => {
			const d = new frappe.ui.Dialog({
				title: __("GPS nuqtalarni o'chirish"),
				fields: [
					{ fieldname: "gps_imei", fieldtype: "Data", label: __("GPS IMEI"),
						description: __("Bo'sh bo'lsa, barcha qurilmalar") },
					{ fieldname: "to_date", fieldtype: "Date", label: __("Shu sanagacha (shu kun ham)"),
						description: __("Bo'sh bo'lsa, barcha sanalar") },
				],
				primary_action_label: __("O'chirish"),
				primary_action(values) {
					frappe.confirm(__("Tanlangan GPS nuqtalar butunlay o'chiriladi. Davom etasizmi?"), () => {
						frappe.call({
							method: "carieer.api.delete_gps_points",
							args: values,
							freeze: true,
						}).then((r) => {
							d.hide();
							frappe.show_alert({ message: __("{0} ta nuqta o'chirildi", [r.message]), indicator: "green" });
							listview.refresh();
						});
					});
				},
			});
			d.show();
		});
	},
};
