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
		frappe.route_options = Object.fromEntries(new URLSearchParams(search));
		return set_route.call(this, path);
	}
	return set_route.apply(this, args);
};
