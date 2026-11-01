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
	// «Эко Бетон» (jadval varaqlari nomi bilan) menyusi ham Beton bo'limi
	const ru = { Karer: "Карьер", Beton: "Бетон" };
	const bolim = Object.keys(info.bolimlar).find((b) => sidebar.includes(b) || sidebar.includes(ru[b]));
	return info.bolimlar[bolim] || info.default;
};

// Hujjat boshqa firmaniki bo'lsa (masalan «Panel Beton» menyusidan Karer sotuvi ochildi), menyu o'sha firmaning
// shu nomli bo'limiga almashadi: «Panel Beton» -> «Panel Karer». Aks holda ro'yxat va hisobotlar noto'g'ri firma
// bilan ochiladi. `prefer` - shu firmaning aynan qaysi bo'limi kerakligi («Kassa», «Ombor»).
carieer.sidebar_for_company = function (company, prefer) {
	const info = frappe.boot.carieer_firma;
	const sidebar = frappe.app?.sidebar;
	if (!info || !sidebar || !company) return;
	const bolim = Object.keys(info.bolimlar).find((b) => info.bolimlar[b] === company);
	if (!bolim) return;
	const title = sidebar.sidebar_title || "";
	const current = Object.keys(info.bolimlar).find((b) => title.endsWith(" " + b));
	let target = prefer ? `${prefer} ${bolim}` : null;
	if (!target && current && current !== bolim) target = title.slice(0, -current.length) + bolim;
	if (target && target !== title && frappe.boot.workspace_sidebar_item[target.toLowerCase()]) {
		sidebar.setup(target);
		frappe.breadcrumbs.update();
	}
};

// Sahifa yangilanganda (F5) Frappe menyuni o'zi tanlaydi: eslab qolgan narsasi menyu bandi nomi bo'yicha
// («Sotuvlar»), qidirgani hujjat turi bo'yicha («Sotuv») - mos kelmaydi va shu hujjat bor birinchi menyu
// (masalan «Panel Beton») ochiladi, firma filtri ham o'sha firmaga o'tib ketadi. Shu tab'da oxirgi turgan
// menyu saqlanadi va u shu sahifani o'z ichiga olsa - o'sha menyu qaytadi.
const SIDEBAR_KEY = "carieer_sidebar";
$(window).on("beforeunload", () => {
	try {
		sessionStorage.setItem(SIDEBAR_KEY, frappe.app?.sidebar?.sidebar_title || "");
	} catch (e) {
		// sessionStorage yo'q (maxfiy rejim) - Frappe'ning o'z tanlovi qoladi
	}
});
// Menyuda sahifa URL band bilan berilgan («/desk/query-report/Balans?sidebar=...», «Ombor qoldig'i» ->
// /desk/query-report/Ombor%20qoldigi): Frappe faqat link_to bo'yicha qidiradi va bunday menyuni topmaydi.
function sidebar_has_url(title, entity) {
	return (frappe.boot.workspace_sidebar_item[(title || "").toLowerCase()]?.items || []).some(
		(item) => item.url && decodeURIComponent(item.url.split("?")[0]).endsWith("/" + entity)
	);
}

const resolve_sidebar = frappe.ui.Sidebar.prototype.resolve_sidebar;
frappe.ui.Sidebar.prototype.resolve_sidebar = function (entity, module) {
	const candidates = this.get_workspace_sidebars(entity);
	const current = this.sidebar_title;
	if (current && !candidates.includes(current) && sidebar_has_url(current, entity)) {
		// joriy menyudagi URL band bosildi - menyu o'zgarmaydi
		this.preferred_sidebars = [current, ...candidates];
		return current;
	}
	if (!current) {
		let saved = null;
		try {
			saved = sessionStorage.getItem(SIDEBAR_KEY);
		} catch (e) {
			saved = null;
		}
		if (saved && (candidates.includes(saved) || sidebar_has_url(saved, entity))) {
			this.preferred_sidebars = candidates.includes(saved) ? candidates : [saved, ...candidates];
			return saved;
		}
	}
	return resolve_sidebar.call(this, entity, module);
};

$(document).on("form-refresh", (e, frm) => {
	if (frm?.doc?.company && !frm.is_new()) carieer.sidebar_for_company(frm.doc.company);
});

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
