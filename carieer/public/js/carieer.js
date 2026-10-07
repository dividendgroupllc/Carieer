// Bo'lim (Karer / Beton Zavod) menyusidan hisobot ochilganda «Firma» filtri shu bo'lim firmasi bilan to'ladi.
// Aks holda hisobot foydalanuvchining standart firmasini oladi va Beton Zavod bo'limida Karer raqamlari chiqadi.
// Firma xaritasi server tomonda (permissions.boot_session -> frappe.boot.carieer_bolim).
(function () {
	function bolim_company() {
		const sidebar = frappe.app && frappe.app.sidebar;
		const title = ((sidebar && sidebar.sidebar_title) || "").toLowerCase();
		return (frappe.boot.carieer_bolim || {})[title];
	}

	// capture: Frappe router havolani ochishidan oldin ishlaydi
	document.addEventListener(
		"click",
		function (e) {
			if (!e.target.closest) return;
			const a = e.target.closest(".body-sidebar a.item-anchor");
			const report_link = a && (a.getAttribute("href") || "").includes("/query-report/");
			// bosh sahifadagi «Tezkor kirish» (Kunlik otchet, Akt sverka, Qarzdorlik, Sotuvlar ...)
			const shortcut = e.target.closest(".shortcut-widget-box");
			if (!report_link && !shortcut) return;
			const company = bolim_company();
			if (company) frappe.route_options = Object.assign({}, frappe.route_options, { company });
		},
		true
	);
})();
