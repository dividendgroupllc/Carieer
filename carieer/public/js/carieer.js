// Bo'lim (Karer / Beton Zavod) ichida ishlaganda hamma narsa shu bo'lim firmasida bo'lsin.
// Ikkala firmaga ruxsati bor foydalanuvchida (Administrator, menejer) aks holda standart firma (masalan Eko Karer)
// qo'yiladi: Beton Zavod -> Qabul -> tovar Karer omboriga tushib qoladi, hisobotda Karer raqamlari chiqadi.
//   1. menyudan hisobot ochilganda «Firma» filtri = bo'lim firmasi
//   2. menyudan hujjat ro'yxati ochilganda filtr = bo'lim firmasi / zavodi (yangi hujjat shu qiymatni oladi)
//   3. bo'lim ichida har qanday YANGI forma (qidiruv, «New», havola orqali ham) - firma, zavod va xarid ombori
// Xarita server tomonda (permissions.boot_session -> frappe.boot.carieer_bolim, carieer_route_options,
// carieer_form_defaults).
(function () {
	function bolim_title() {
		const sidebar = frappe.app && frappe.app.sidebar;
		return ((sidebar && sidebar.sidebar_title) || "").toLowerCase();
	}

	function doctype_options(href) {
		// "/desk/purchase-receipt" yoki "/desk/purchase-receipt/view/list?..." -> "Purchase Receipt" qiymatlari
		const path = (href || "").split("?")[0].replace(/^\/(desk|app)\//, "");
		const slug = decodeURIComponent(path.split("/")[0] || "");
		const map = frappe.boot.carieer_route_options || {};
		const doctype = Object.keys(map).find((d) => frappe.router.slug(d) === slug);
		return doctype && map[doctype][bolim_title()];
	}

	// capture: Frappe router havolani ochishidan oldin ishlaydi
	document.addEventListener(
		"click",
		function (e) {
			if (!e.target.closest) return;
			const a = e.target.closest(".body-sidebar a.item-anchor");
			const href = (a && a.getAttribute("href")) || "";
			const report_link = href.includes("/query-report/");
			// bosh sahifadagi «Tezkor kirish» (Kunlik otchet, Akt sverka, Qarzdorlik, Sotuvlar ...)
			const shortcut = e.target.closest(".shortcut-widget-box");
			if (report_link || shortcut) {
				const company = (frappe.boot.carieer_bolim || {})[bolim_title()];
				if (company) frappe.route_options = Object.assign({}, frappe.route_options, { company });
				return;
			}
			const options = a && doctype_options(href);
			if (options) frappe.route_options = Object.assign({}, frappe.route_options, options);
		},
		true
	);

	async function set_section_values(frm) {
		const section = bolim_title();
		const options = ((frappe.boot.carieer_route_options || {})[frm.doctype] || {})[section];
		const defaults = ((frappe.boot.carieer_form_defaults || {})[frm.doctype] || {})[section];
		if (!options && !defaults) return;
		// boshqa hujjatdan yaratilgan (Qabul -> Faktura) yoki nusxa / tuzatish - firma manba hujjatdan qoladi
		if (frm.doc.amended_from || (frm.doc.items || []).some((row) => row.item_code)) return;
		// avval firma (u o'zgarganda ERPNext omborlarni tozalaydi), keyin ombor
		for (const values of [options, defaults]) {
			for (const [field, value] of Object.entries(values || {})) {
				if (frm.fields_dict[field] && frm.doc[field] !== value) {
					await frm.set_value(field, value);
				}
			}
		}
	}

	function register_forms() {
		const doctypes = new Set([
			...Object.keys(frappe.boot.carieer_route_options || {}),
			...Object.keys(frappe.boot.carieer_form_defaults || {}),
		]);
		doctypes.forEach((doctype) => {
			frappe.ui.form.on(doctype, "onload", function (frm) {
				if (frm.is_new()) set_section_values(frm);
			});
		});
	}

	if (frappe.boot && frappe.ui && frappe.ui.form) {
		register_forms();
	} else {
		$(document).on("app_ready", register_forms);
	}
})();
