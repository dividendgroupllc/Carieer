// Bosh sahifadagi ilova ikonkasi shu sahifaga keladi va xodimni o'z zavodining bo'limiga yuboradi:
// Beton xodimi -> Beton Zavod, post operatori (ikkala firma) -> Sotuv operator, qolganlar (karer xodimi, admin) -> Karer.
// (Frappe bitta ilovaga bosh sahifada faqat bitta ikonka ko'rsatadi.)

function carieer_home_redirect() {
	const route = frappe.boot.carieer_post
		? "/desk/sotuv-operator"
		: frappe.boot.carieer_firma === "Beton"
		? "/desk/beton-zavod"
		: "/desk/karer";
	window.location.replace(route);
}

frappe.pages["carieer-home"].on_page_load = carieer_home_redirect;
frappe.pages["carieer-home"].on_page_show = carieer_home_redirect;
