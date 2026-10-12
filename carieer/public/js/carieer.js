// Xodim bitta zavodga bog'langan bo'lsa (User Permission -> Zavod), yangi hujjatda firma, zavod va xarid ombori
// o'zi qo'yiladi: Beton xodimi Qabul (Purchase Receipt) ochsa - Eko Beton va uning xomashyo ombori, Karer'ga tushib
// ketmaydi. Xarita server tomonda (permissions.boot_session -> frappe.boot.carieer_form_defaults).
(function () {
	async function set_defaults(frm) {
		const defaults = (frappe.boot.carieer_form_defaults || {})[frm.doctype];
		if (!defaults) return;
		// boshqa hujjatdan yaratilgan (Qabul -> Faktura) yoki nusxa / tuzatish - firma manba hujjatdan qoladi
		if (frm.doc.amended_from || (frm.doc.items || []).some((row) => row.item_code)) return;
		// avval firma (u o'zgarganda ERPNext omborlarni tozalaydi), keyin qolganlari
		const fields = Object.keys(defaults).sort((a) => (a === "company" ? -1 : 1));
		for (const field of fields) {
			if (frm.fields_dict[field] && frm.doc[field] !== defaults[field]) {
				await frm.set_value(field, defaults[field]);
			}
		}
	}

	function register_forms() {
		Object.keys(frappe.boot.carieer_form_defaults || {}).forEach((doctype) => {
			frappe.ui.form.on(doctype, "onload", function (frm) {
				if (frm.is_new()) set_defaults(frm);
			});
		});
	}

	if (frappe.boot && frappe.ui && frappe.ui.form) {
		register_forms();
	} else {
		$(document).on("app_ready", register_forms);
	}
})();
