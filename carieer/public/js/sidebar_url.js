// Hisobot menyularining birinchi havolasi URL: «/desk/query-report/Balans?sidebar=Баланс Karer» - shunda menyu
// (va firma filtri) doim shu menyu bo'ladi. Desktop ikonkasi bu manzilni href sifatida ochadi, lekin menyu
// almashtirgich (frappe/ui/menu.js) uni frappe.set_route(url) ga beradi va «?sidebar=...» hisobot nomiga
// qo'shilib qoladi. Shu holda so'rov qismi route_options ga ajratiladi.

const set_route = frappe.set_route;

frappe.set_route = function (...args) {
	const [route] = args;
	if (
		args.length === 1 &&
		typeof route === "string" &&
		route.startsWith("/desk/") &&
		route.includes("?")
	) {
		const [path, search] = route.split("?");
		const { sidebar, ...filters } = Object.fromEntries(new URLSearchParams(search));
		if (sidebar && Object.keys(filters).length) {
			// Frappe «sidebar» ni ko'rsa menyuni almashtiradi va qolgan route_options ni o'chirib yuboradi
			// (ui/sidebar/sidebar.js): «ПР Срав. Общ» (?guruhlash=Наименование&sidebar=...) «Категория» bilan ochilardi
			if (frappe.app.sidebar && frappe.app.sidebar.sidebar_title !== sidebar) frappe.app.sidebar.setup(sidebar);
			frappe.route_options = filters;
		} else {
			frappe.route_options = Object.fromEntries(new URLSearchParams(search));
		}
		return set_route.call(this, path);
	}
	return set_route.apply(this, args);
};

// Bir menyuda bitta sahifaga olib boradigan bir nechta band bor («Эко Бетон»: «Производство» / «Перемещ.» -
// Stock Entry, «ГП СС» / «АВ РАС РЕЦ сум» - bitta hisobot, «ПР Срав.» / «ПР Срав. Общ» - bitta hisobot, boshqa
// guruhlash). Frappe:
//  - qaysi band ochiqligini faqat manzil bo'yicha (so'rov qismisiz) topadi va oxirgisini belgilaydi: «Производство»
//    bosilsa «Перемещ.» belgilanib qoladi - bosilmagandek ko'rinadi;
//  - ochiq turgan hisobotning boshqa bandi bosilsa hisobot qayta ochilmaydi (filtrlari ham almashmaydi).
frappe.provide("carieer");
let clicked = null;
const clean = (path) => decodeURIComponent(path || "").replace(/\/$/, "");
const href_path = (a) => clean(($(a).attr("href") || "").split("?")[0].split("#")[0]);
const href_params = (a) => new URLSearchParams(($(a).attr("href") || "").split("?")[1] || "");

window.addEventListener("popstate", () => (clicked = null));

// capture: Frappe'ning o'z havola ishlovchisidan oldin. Ctrl / Cmd / Shift bilan bosilsa - odatdagidek (yangi tab).
document.addEventListener(
	"click",
	(e) => {
		const a = e.target.closest?.(".body-sidebar a.item-anchor");
		if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
		const href = $(a).attr("href") || "";
		if (!href.startsWith("/desk/")) return;
		clicked = a;
		carieer.sidebar_list_path = href_path(a);
		if (href_path(a) === clean(location.pathname) && frappe.get_route()[0] === "query-report") {
			// shu hisobot ochiq: bandning o'z filtrlari bilan qayta ochiladi (qolganlari - odatiy qiymat)
			e.preventDefault();
			e.stopPropagation();
			frappe.query_report?.refresh_report(Object.fromEntries(href_params(a)));
		} else if ($(a).attr("target") === "_blank") {
			// URL turidagi ichki havola («Ombor qoldig'i» -> /desk/query-report/Ombor%20qoldigi) Frappe shablonida
			// target="_blank" bilan chiziladi va yangi tabda ochiladi - tizim ichidagi sahifa shu tabda ochilsin
			e.preventDefault();
			e.stopPropagation();
			frappe.set_route(href);
		}
		setTimeout(() => frappe.app.sidebar?.set_active_workspace_item(), 300);
	},
	true
);

const is_route_in_sidebar = frappe.ui.Sidebar.prototype.is_route_in_sidebar;
frappe.ui.Sidebar.prototype.is_route_in_sidebar = function () {
	const match = is_route_in_sidebar.call(this);
	if (!match) return match;
	const path = clean(location.pathname);
	const same = $(".body-sidebar .item-anchor")
		.toArray()
		.filter((a) => href_path(a) === path);
	if (same.length < 2) return match;
	// bosilgan band; bo'lmasa (sahifa yangilandi) - filtrlari joriy manzilga mos keladigani; bo'lmasa - birinchisi
	const current = new URLSearchParams(location.search);
	const best =
		(same.includes(clicked) && clicked) ||
		same.find((a) => {
			const params = [...href_params(a)].filter(([k]) => k !== "sidebar");
			return params.length && params.every(([k, v]) => current.get(k) === v);
		}) ||
		same[0];
	this.active_item?.removeClass("active-sidebar");
	this.active_item = $(best).parent();
	return match;
};
