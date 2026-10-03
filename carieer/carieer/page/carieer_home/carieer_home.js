// Bosh sahifadagi ilova ikonkasi shu sahifaga keladi va xodimni o'z zavodining bo'limiga yuboradi:
// Beton xodimi -> Beton Zavod, qolganlar (karer xodimi, admin) -> Karer.
// (Frappe bitta ilovaga bosh sahifada faqat bitta ikonka ko'rsatadi.)

function carieer_home_redirect() {
	window.location.replace(frappe.boot.carieer_firma === "Beton" ? "/desk/beton-zavod" : "/desk/karer");
}

frappe.pages["carieer-home"].on_page_load = carieer_home_redirect;
frappe.pages["carieer-home"].on_page_show = carieer_home_redirect;
