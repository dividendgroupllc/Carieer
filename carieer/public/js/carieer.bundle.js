import "./desktop_groups";
import "./sidebar_url";

// Karer / Beton xodimi: ro'yxat va hisobotlarda firma filtrida o'z firmasi turadi. Rahbar (ikkala firma) - qaysi
// bo'limdan kirgan bo'lsa (Kassa Karer / Kassa Beton ...) o'sha firma. Bo'lim almashganda filtr ham almashadi,
// aks holda xodim tanlagani qoladi. Ma'lumotni baribir User Permission cheklaydi - bu faqat qulaylik.
// Firma va bo'limlar: frappe.boot.carieer_firma (carieer.permissions.boot_firma).
frappe.provide("carieer");

carieer.firma = function () {
	const info = frappe.boot.carieer_firma;
	if (!info) return null;
	const sidebar = frappe.app?.sidebar?.sidebar_title || "";
	const bolim = Object.keys(info.bolimlar).find((b) => sidebar.includes(b));
	return info.bolimlar[bolim] || info.default;
};

// Ro'yxat: hujjatning firma maydoni - «company» (Mode of Payment'da - «firma»)
function firma_field(meta) {
	return ["company", "firma"].find((fieldname) =>
		meta?.fields?.some((df) => df.fieldname === fieldname && df.fieldtype === "Link" && df.options === "Company")
	);
}

function set_list_firma(listview) {
	const company = carieer.firma();
	const fieldname = firma_field(listview.meta);
	if (!company || !fieldname || listview.carieer_firma === company) return;
	listview.carieer_firma = company;
	const field = listview.page.fields_dict[fieldname];
	if (field) {
		if (field.get_value() !== company) field.set_value(company);
		return;
	}
	const current = listview.filter_area.get().find((f) => f[1] === fieldname);
	if (current && current[2] === "=" && current[3] === company) return;
	listview.filter_area
		.remove(fieldname)
		.then(() => listview.filter_area.add(listview.doctype, fieldname, "=", company));
}

const list_refresh = frappe.views.ListView.prototype.refresh;
frappe.views.ListView.prototype.refresh = function (...args) {
	const out = list_refresh.apply(this, args);
	Promise.resolve(out).then(() => set_list_firma(this));
	return out;
};

// Hisobot: «company» filtri. Havola orqali firma berilsa (route_options) - o'sha qoladi.
const report_setup_filters = frappe.views.QueryReport.prototype.setup_filters;
frappe.views.QueryReport.prototype.setup_filters = function (...args) {
	const out = report_setup_filters.apply(this, args);
	const company = carieer.firma();
	const filter = company && this.get_filter("company", false);
	if (filter) {
		filter.set_input(company);
		this.carieer_firma = company;
	}
	return out;
};

const report_load = frappe.views.QueryReport.prototype.load;
frappe.views.QueryReport.prototype.load = function (...args) {
	// shu hisobotga boshqa bo'limdan qaytildi (hisobot qayta yuklanmaydi) - firma almashadi
	const company = carieer.firma();
	const same = this.report_name === frappe.get_route()[1] && !frappe.has_route_options();
	if (same && company && this.carieer_firma && this.carieer_firma !== company) {
		this.carieer_firma = company;
		if (this.get_filter("company", false)) this.set_filter_value("company", company);
	}
	return report_load.apply(this, args);
};
