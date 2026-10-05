// Texnikalar xaritasi: GPS (Traccar Client yoki GPS provayder) orqali kelgan oxirgi joylashuvlar,
// realtime yangilanish (carieer.api -> publish_realtime "karer_gps"), tanlangan kundagi yurgan yo'l,
// to'xtashlar, holat bo'yicha hisoblagich, qidiruv va bugun yurgan masofa.
// Leaflet Frappe v16 da desk bilan birga yuklanadi (libs.bundle.js) -> alohida yuklash shart emas.

frappe.pages["texnika-xarita"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Texnikalar xaritasi"),
		single_column: true,
	});
	wrapper.xarita = new KarerXarita(page);
};

frappe.pages["texnika-xarita"].on_page_show = function (wrapper) {
	wrapper.xarita && wrapper.xarita.on_show();
};

const KX_DEFAULT_CENTER = [41.3111, 69.2797]; // Toshkent
// Ikki nuqta orasida shundan ko'p vaqt va masofa bo'lsa - uzilish (telefon yubormagan)
const KX_GAP_SECONDS = 120;
const KX_GAP_METERS = 300;
const KX_SNAP_MAX_METERS = 50000; // bundan uzoq uzilishga taxminiy yo'l qidirilmaydi
const KX_OSRM_URL = "https://router.project-osrm.org/route/v1/driving/";
// Mashina shu radius ichida shuncha daqiqadan ko'p tursa - to'xtash (telefon GPS'i joyida ham 20-50 m "sakraydi")
const KX_STOP_MINUTES = 5;
const KX_STOP_METERS = 60;
const KX_STATUS = {
	moving: { color: "#16a34a", label: __("Harakatda") },
	stopped: { color: "#f59e0b", label: __("To'xtagan") },
	offline: { color: "#6b7280", label: __("Aloqa yo'q") },
	none: { color: "#d1d5db", label: __("Ma'lumot yo'q") },
};

class KarerXarita {
	constructor(page) {
		this.page = page;
		this.points = {}; // gps_imei -> oxirgi nuqta
		this.markers = {}; // gps_imei -> L.circleMarker
		this.track = null; // {imei, date, layer, line, end}
		this.search = "";

		this.add_style();
		this.make_filters();
		this.make_layout();

		const ready = window.L ? Promise.resolve() : frappe.require("libs.bundle.js");
		ready.then(() => {
			this.make_map();
			this.load(true);
			frappe.realtime.on("karer_gps", (p) => this.on_point(p));
		});
		// "necha daqiqa oldin" va holat rangi vaqt o'tishi bilan o'zgaradi
		setInterval(() => this.render_all(), 30 * 1000);
		// Realtime (socket) uzilib qolsa ham xarita eskirib qolmasin
		setInterval(() => this.map && this.refresh_live(), 60 * 1000);
		// Bugungi km har 5 daqiqada qayta hisoblanadi
		setInterval(() => this.map && this.load(false), 5 * 60 * 1000);
	}

	on_show() {
		if (!this.map) return;
		setTimeout(() => this.map.invalidateSize(), 150);
		this.load(false);
	}

	// ------------------------------------------------------------------ UI
	make_filters() {
		this.company_field = this.page.add_field({
			fieldname: "company",
			label: __("Firma"),
			fieldtype: "Link",
			options: "Company",
			change: () => {
				this.clear_track();
				Object.values(this.markers).forEach((m) => this.map && this.map.removeLayer(m));
				this.markers = {};
				this.load(true);
			},
		});
		this.date_field = this.page.add_field({
			fieldname: "sana",
			label: __("Sana"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		});
		this.device_field = this.page.add_field({
			fieldname: "qurilma",
			label: __("Texnika"),
			fieldtype: "Select",
			options: [""],
		});
		this.page.set_primary_action(__("Yo'lni ko'rsatish"), () => this.show_track(), "map");
		this.page.set_secondary_action(__("Tozalash"), () => this.clear_track());
		this.page.add_menu_item(__("Yangilash"), () => this.load(true));
		this.page.add_menu_item(__("Texnikalar ro'yxati"), () => frappe.set_route("List", "Vehicle"));
		this.page.add_menu_item(__("GPS nuqtalar ro'yxati"), () => frappe.set_route("List", "GPS Malumot"));
		this.page.add_menu_item(__("GPS sozlamalari (token)"), () => frappe.set_route("Form", "Karer Sozlamalari"));
	}

	make_layout() {
		this.$body = $(`
			<div class="texnika-xarita">
				<div class="kx-side">
					<div class="kx-stats"></div>
					<input type="search" class="form-control input-xs kx-search" placeholder="${__("Qidirish: raqam, turi, haydovchi")}">
					<div class="kx-summary"></div>
					<div class="kx-list"></div>
				</div>
				<div class="kx-map"></div>
			</div>
		`).appendTo(this.page.main);
		this.$list = this.$body.find(".kx-list");
		this.$stats = this.$body.find(".kx-stats");
		this.$body.find(".kx-search").on("input", (e) => {
			this.search = (e.target.value || "").toLowerCase().trim();
			this.render_list();
		});
		this.$stats.on("click", ".kx-stat[data-status]", (e) => {
			const key = $(e.currentTarget).attr("data-status");
			this.status_filter = this.status_filter === key ? null : key;
			this.render_list();
		});
		this.$summary = this.$body.find(".kx-summary");
		this.$map = this.$body.find(".kx-map");

		this.$list.on("click", ".kx-item", (e) => this.focus($(e.currentTarget).attr("data-imei")));
		this.$summary.on("click", ".kx-stop-row", (e) => {
			const $r = $(e.currentTarget);
			this.focus_place($r.attr("data-kind"), cint($r.attr("data-idx")));
		});
		this.$map.on("click", ".kx-track-btn", (e) => {
			const imei = $(e.currentTarget).attr("data-imei");
			this.device_field.set_value(imei);
			this.show_track({ imei });
		});
	}

	make_map() {
		const tiles = frappe.utils.map_defaults.tiles;
		const osm = L.tileLayer(tiles.default_tile.url, tiles.default_tile.options);
		const sat = L.tileLayer(tiles.satellite_tile.url, tiles.satellite_tile.options);
		this.map = L.map(this.$map.get(0), { layers: [osm] }).setView(KX_DEFAULT_CENTER, 11);
		L.control.layers({ [__("Xarita")]: osm, [__("Sun'iy yo'ldosh")]: sat }).addTo(this.map);
		setTimeout(() => this.map.invalidateSize(), 150);
	}

	add_style() {
		if (document.getElementById("texnika-xarita-style")) return;
		$(`<style id="texnika-xarita-style">
			.texnika-xarita { display: flex; gap: 12px; height: calc(100vh - 200px); min-height: 440px; }
			.kx-side { width: 290px; flex-shrink: 0; display: flex; flex-direction: column; gap: 8px; min-height: 0; }
			.kx-summary:empty { display: none; }
			.kx-stats { display: flex; gap: 6px; flex-wrap: wrap; }
			.kx-stat { flex: 1; min-width: 60px; padding: 6px 8px; border: 1px solid var(--border-color); border-radius: var(--border-radius-md);
				background: var(--card-bg); cursor: pointer; text-align: center; }
			.kx-stat.active { border-color: var(--text-color); box-shadow: 0 0 0 1px var(--text-color); }
			.kx-stat b { display: block; font-size: 18px; line-height: 1.2; }
			.kx-stat span { font-size: 11px; color: var(--text-muted); }
			.kx-km { float: right; font-weight: 600; color: var(--text-color); }
			.kx-summary { padding: 10px 12px; border: 1px solid var(--border-color); border-radius: var(--border-radius-md);
				background: var(--card-bg); font-size: var(--text-sm); max-height: 55%; overflow: auto; flex-shrink: 0; }
			.kx-stops { margin-top: 6px; border-top: 1px solid var(--border-color); padding-top: 6px; }
			.kx-stop-row { display: flex; gap: 8px; padding: 4px 2px; cursor: pointer; border-radius: 4px; font-size: var(--text-xs); }
			.kx-stop-row:hover { background: var(--fg-hover-color); }
			.kx-badge { flex-shrink: 0; width: 20px; height: 20px; border-radius: 50%; color: #fff; font-weight: 700;
				font-size: 11px; display: flex; align-items: center; justify-content: center; border: 2px solid #fff;
				box-shadow: 0 0 0 1px rgba(0,0,0,.25); }
			.kx-badge.stop { background: #f59e0b; }
			.kx-badge.start { background: #2563eb; }
			.kx-badge.end { background: #dc2626; }
			.kx-icon { background: none; border: none; }
			.kx-icon .kx-badge { width: 24px; height: 24px; font-size: 12px; }
			.kx-list { flex: 1; overflow: auto; border: 1px solid var(--border-color); border-radius: var(--border-radius-md);
				background: var(--card-bg); }
			.kx-map { flex: 1; border: 1px solid var(--border-color); border-radius: var(--border-radius-md); overflow: hidden; z-index: 0; }
			.kx-item { padding: 10px 12px; border-bottom: 1px solid var(--border-color); cursor: pointer; }
			.kx-item:hover, .kx-item.active { background: var(--fg-hover-color); }
			.kx-item .kx-title { font-weight: 600; color: var(--text-color); }
			.kx-item .kx-meta { font-size: var(--text-xs); color: var(--text-muted); margin-top: 2px; }
			.kx-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
			.kx-empty { padding: 16px; color: var(--text-muted); font-size: var(--text-sm); }
			.leaflet-tooltip.kx-tip { font-weight: 600; padding: 1px 6px; }
			.kx-popup td { padding: 1px 8px 1px 0; }
			.kx-popup td:first-child { color: #6b7280; }
			@media (max-width: 768px) {
				.texnika-xarita { flex-direction: column; height: auto; }
				.kx-side { width: 100%; }
				.kx-list { max-height: 220px; }
				.kx-map { height: 60vh; flex: none; }
			}
		</style>`).appendTo("head");
	}

	// ------------------------------------------------------------------ ma'lumot
	load(fit) {
		frappe.call({
			method: "carieer.api.get_live_positions",
			args: { company: this.company_field.get_value() || null, with_km: 1 },
			type: "GET",
		}).then((r) => {
			this.points = {};
			(r.message || []).forEach((p) => (this.points[p.gps_imei] = p));
			this.update_device_options();
			this.render_all();
			if (!fit) return;
			// Bitta texnika faol bo'lsa - uning bugungi yo'li darhol ko'rsatiladi
			const active = Object.values(this.points).filter((p) => p.vaqt && this.status(p) !== KX_STATUS.offline);
			if (active.length === 1 && !this.track) this.focus(active[0].gps_imei);
			else this.fit_all();
		});
	}

	refresh_live() {
		// Realtime o'tkazib yuborgan nuqtalarni ham olib keladi (on_point eski/takroriy nuqtani o'tkazib yuboradi)
		frappe.call({
			method: "carieer.api.get_live_positions",
			args: { company: this.company_field.get_value() || null },
			type: "GET",
		}).then((r) => {
			(r.message || []).forEach((p) => {
				const old = this.points[p.gps_imei];
				if (!old || p.vaqt !== old.vaqt) this.on_point(p, true);
			});
			// Kuzatilayotgan yo'lga ham oraliqdagi nuqtalar qo'shilsin
			const t = this.track;
			if (t && t.date === frappe.datetime.get_today()) this.sync_track(t);
		});
	}

	sync_track(t) {
		frappe.call({ method: "carieer.api.get_track", args: { gps_imei: t.imei, date: t.date }, type: "GET" }).then((r) => {
			const last = t.pts[t.pts.length - 1];
			(r.message || [])
				.filter((p) => p.lat != null && (!last || p.vaqt > last.vaqt))
				.forEach((p) => this.extend_track({ ...p, gps_imei: t.imei, vaqt: String(p.vaqt) }));
		});
	}

	on_point(p, from_server = false) {
		// Realtime hamma texnikani yuboradi. Ro'yxatda yo'q yangi qurilma bo'lsa server so'raladi:
		// u xodimning firmasi bo'yicha filtrlab beradi (boshqa firma texnikasi ko'rinmaydi)
		if (!from_server && !this.points[p.gps_imei]) {
			if (!this.refresh_pending) {
				this.refresh_pending = true;
				setTimeout(() => {
					this.refresh_pending = false;
					this.refresh_live();
				}, 2000);
			}
			return;
		}
		const old = this.points[p.gps_imei] || {};
		// Telefon oflayn bufer'dagi eski nuqtalarni keyinroq yuboradi -> ular joriy joylashuvni almashtirmaydi
		if (old.vaqt && p.vaqt < old.vaqt) return;
		// texnika_turi/model faqat get_live_positions da keladi -> saqlab qolamiz
		const keep = {};
		["vehicle", "texnika_turi", "model", "haydovchi", "bugun_km", "company"].forEach((k) => {
			if (p[k] == null && old[k] != null) keep[k] = old[k];
		});
		this.points[p.gps_imei] = { ...old, ...p, ...keep };
		if (!old.gps_imei) this.update_device_options();
		this.render_point(this.points[p.gps_imei]);
		this.render_list();
		this.extend_track(p);
	}

	// ------------------------------------------------------------------ chizish
	status(p) {
		if (!p.vaqt || p.lat == null) return KX_STATUS.none;
		const mins = moment().diff(this.to_moment(p.vaqt), "minutes");
		if (mins <= 5 && flt(p.tezlik) >= 3) return KX_STATUS.moving;
		if (mins <= 30) return KX_STATUS.stopped;
		return KX_STATUS.offline;
	}

	to_moment(vaqt) {
		const tz = frappe.boot.time_zone && frappe.boot.time_zone.system;
		return tz ? moment.tz(vaqt, tz) : moment(vaqt);
	}

	label(p) {
		return p.vehicle || p.gps_imei;
	}

	coord_text(lat, lon) {
		return `${flt(lat, 6).toFixed(6)}, ${flt(lon, 6).toFixed(6)}`;
	}

	// Koordinata + Google Maps havolasi (telefonda bosilsa navigatsiya ochiladi)
	coord_html(lat, lon) {
		const q = `${flt(lat, 6)},${flt(lon, 6)}`;
		return `<a href="https://www.google.com/maps?q=${q}" target="_blank" rel="noopener">${this.coord_text(lat, lon)}</a>`;
	}

	hhmm(vaqt) {
		return this.to_moment(vaqt).format("HH:mm");
	}

	duration_text(mins) {
		mins = Math.round(mins);
		const h = Math.floor(mins / 60);
		return h ? __("{0} soat {1} daq", [h, mins % 60]) : __("{0} daq", [mins]);
	}

	render_all() {
		Object.values(this.points).forEach((p) => this.render_point(p));
		this.render_list();
	}

	render_point(p) {
		if (!this.map || p.lat == null || p.lon == null || !p.vaqt) return;
		const st = this.status(p);
		let m = this.markers[p.gps_imei];
		if (!m) {
			m = L.circleMarker([p.lat, p.lon], { radius: 9, color: "#fff", weight: 2, fillOpacity: 1 })
				.bindTooltip("", { permanent: true, direction: "right", offset: [10, 0], className: "kx-tip" })
				.bindPopup("")
				.addTo(this.map);
			this.markers[p.gps_imei] = m;
		}
		m.setLatLng([p.lat, p.lon]);
		m.setStyle({ fillColor: st.color });
		m.setTooltipContent(frappe.utils.escape_html(this.label(p)));
		m.setPopupContent(this.popup_html(p, st));
	}

	popup_html(p, st) {
		const esc = frappe.utils.escape_html;
		const rows = [
			[__("Holat"), `<span class="kx-dot" style="background:${st.color}"></span>${st.label}`],
			[__("Tezlik"), `${flt(p.tezlik, 1)} ${__("km/soat")}`],
			[__("Vaqt"), `${frappe.datetime.str_to_user(p.vaqt)} (${this.to_moment(p.vaqt).fromNow()})`],
			[__("Koordinata"), this.coord_html(p.lat, p.lon)],
		];
		if (p.texnika_turi || p.model) rows.push([__("Turi"), esc([p.texnika_turi, p.model].filter(Boolean).join(", "))]);
		if (p.haydovchi) rows.push([__("Haydovchi"), esc(p.haydovchi)]);
		if (p.bugun_km != null) rows.push([__("Bugun yurdi"), `${flt(p.bugun_km, 1)} km`]);
		if (p.batareya != null) rows.push([__("Batareya"), `${cint(p.batareya)}%`]);
		if (p.yoqilgi_darajasi) rows.push([__("Yoqilg'i"), `${flt(p.yoqilgi_darajasi, 1)} l`]);
		if (p.qurilma) rows.push([__("Signal"), esc(p.qurilma)]);
		rows.push([__("Qurilma ID"), esc(p.gps_imei)]);

		const title = p.vehicle
			? `<a href="/desk/vehicle/${encodeURIComponent(p.vehicle)}">${esc(p.vehicle)}</a>`
			: `${esc(p.gps_imei)} <div class="text-muted small">${__("Vehicle ga bog'lanmagan")}</div>`;
		return `<div class="kx-popup">
			<div style="font-weight:600;font-size:14px;margin-bottom:4px">${title}</div>
			<table>${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("")}</table>
			<button class="btn btn-xs btn-default kx-track-btn" style="margin-top:6px" data-imei="${esc(p.gps_imei)}">
				${__("Yurgan yo'li")}
			</button>
		</div>`;
	}

	status_key(p) {
		const st = this.status(p);
		return Object.keys(KX_STATUS).find((k) => KX_STATUS[k] === st);
	}

	render_stats(all) {
		const counts = { moving: 0, stopped: 0, offline: 0, none: 0 };
		all.forEach((p) => (counts[this.status_key(p)] += 1));
		const total_km = all.reduce((s, p) => s + flt(p.bugun_km), 0);
		const chip = (key) => `<div class="kx-stat ${this.status_filter === key ? "active" : ""}" data-status="${key}"
			title="${__("Bosing: faqat shu holatdagilar")}">
			<b style="color:${KX_STATUS[key].color}">${counts[key]}</b><span>${KX_STATUS[key].label}</span></div>`;
		this.$stats.html(
			chip("moving") +
				chip("stopped") +
				chip("offline") +
				`<div class="kx-stat" style="cursor:default"><b>${flt(total_km, 0)}</b><span>${__("km bugun")}</span></div>`
		);
	}

	matches(p) {
		if (this.status_filter && this.status_key(p) !== this.status_filter) return false;
		if (!this.search) return true;
		return [p.vehicle, p.gps_imei, p.texnika_turi, p.model, p.haydovchi]
			.filter(Boolean)
			.some((v) => String(v).toLowerCase().includes(this.search));
	}

	render_list() {
		const esc = frappe.utils.escape_html;
		const all = Object.values(this.points);
		this.render_stats(all);
		const pts = all.filter((p) => this.matches(p)).sort((a, b) => this.label(a).localeCompare(this.label(b)));
		if (all.length && !pts.length) {
			this.$list.html(`<div class="kx-empty">${__("Bu filtr bo'yicha texnika yo'q")}</div>`);
			return;
		}
		if (!pts.length) {
			this.$list.html(`<div class="kx-empty">
				${__("Hali GPS ma'lumot yo'q.")}<br><br>
				1) ${__("Karer sozlamalari -> GPS API token yozing.")}<br>
				2) ${__("Haydovchi telefoniga Traccar Client o'rnating, server URL:")}
				<code style="word-break:break-all">${location.origin}/api/method/carieer.api.traccar?token=TOKEN</code><br>
				3) ${__("Texnika (Vehicle) -> «GPS qurilma IMEI» maydoniga ilovadagi qurilma ID sini yozing.")}
			</div>`);
			return;
		}
		const active = this.device_field.get_value();
		this.$list.html(
			pts
				.map((p) => {
					const st = this.status(p);
					const when = p.vaqt ? this.to_moment(p.vaqt).fromNow() : "";
					const speed = p.vaqt ? ` · ${flt(p.tezlik, 0)} ${__("km/soat")}` : "";
					const km = p.bugun_km ? `<span class="kx-km">${flt(p.bugun_km, 1)} km</span>` : "";
					const turi = [p.texnika_turi, p.haydovchi].filter(Boolean).map(esc).join(" · ");
					return `<div class="kx-item ${p.gps_imei === active ? "active" : ""}" data-imei="${esc(p.gps_imei)}">
						<div class="kx-title">${km}<span class="kx-dot" style="background:${st.color}"></span>${esc(this.label(p))}</div>
						${turi ? `<div class="kx-meta">${turi}</div>` : ""}
						<div class="kx-meta">${st.label}${speed}${when ? " · " + when : ""}</div>
						${p.lat != null ? `<div class="kx-meta">${this.coord_text(p.lat, p.lon)}</div>` : ""}
						${p.vehicle ? "" : `<div class="kx-meta">${__("Vehicle ga bog'lanmagan")}</div>`}
					</div>`;
				})
				.join("")
		);
	}

	update_device_options() {
		const df = this.device_field.df;
		df.options = [{ label: "", value: "" }].concat(
			Object.values(this.points).map((p) => ({ label: this.label(p), value: p.gps_imei }))
		);
		const val = this.device_field.get_value();
		this.device_field.refresh();
		if (val) this.device_field.set_value(val);
	}

	focus(imei) {
		const p = this.points[imei];
		this.device_field.set_value(imei);
		this.$list.find(".kx-item").removeClass("active").filter(`[data-imei="${CSS.escape(imei)}"]`).addClass("active");
		if (!p || p.lat == null || !this.markers[imei]) {
			frappe.show_alert({ message: __("Bu texnikadan hali ma'lumot kelmagan"), indicator: "orange" });
			return;
		}
		this.map.setView([p.lat, p.lon], Math.max(this.map.getZoom(), 15));
		this.markers[imei].openPopup();
		// Bosilgan texnikaning tanlangan kundagi (odatda bugungi) yo'li ham darhol chiziladi
		this.show_track({ silent: true, imei });
	}

	fit_all() {
		const ll = Object.values(this.points)
			.filter((p) => p.lat != null && p.vaqt)
			.map((p) => [p.lat, p.lon]);
		if (ll.length === 1) this.map.setView(ll[0], 15);
		else if (ll.length) this.map.fitBounds(ll, { padding: [40, 40], maxZoom: 15 });
	}

	// ------------------------------------------------------------------ yurgan yo'l
	show_track(opts = {}) {
		// set_value darhol qo'llanmaydi (promise) -> texnika ro'yxatdan bosilganda imei to'g'ridan-to'g'ri beriladi
		const imei = opts.imei || this.device_field.get_value();
		const date = this.date_field.get_value() || frappe.datetime.get_today();
		if (!imei) {
			if (!opts.silent) frappe.msgprint(__("Texnikani tanlang"));
			return;
		}
		frappe.call({ method: "carieer.api.get_track", args: { gps_imei: imei, date }, freeze: !opts.silent }).then((r) => {
			this.clear_track();
			const pts = (r.message || []).filter((p) => p.lat != null && p.lon != null);
			if (!pts.length) {
				if (!opts.silent) frappe.show_alert({ message: __("Bu kunda ma'lumot yo'q"), indicator: "orange" });
				return;
			}
			const t = (this.track = { imei, date, pts: [], gaps: [], stops: [], km: 0, line: null, layer: L.featureGroup().addTo(this.map) });
			pts.forEach((p) => this.add_track_point(p));
			t.stops_layer = L.featureGroup().addTo(t.layer);
			// Kunning boshlanish nuqtasi doim ko'rinib turadi (yozuvi bilan)
			const first = pts[0];
			t.start = L.marker([first.lat, first.lon], { icon: this.badge_icon("S", "start"), zIndexOffset: 1000 })
				.bindTooltip(__("Boshlanish") + " " + this.hhmm(first.vaqt), { permanent: true, direction: "right", offset: [12, 0], className: "kx-tip" })
				.bindPopup(this.place_popup(__("Kun boshlanishi"), first.lat, first.lon, [[__("Vaqt"), frappe.datetime.str_to_user(first.vaqt)]]))
				.addTo(t.layer);
			const last = pts[pts.length - 1];
			t.end = L.marker([last.lat, last.lon], { icon: this.badge_icon("F", "end"), zIndexOffset: 1000 }).addTo(t.layer);
			this.update_end(last);
			this.render_stops();
			this.map.fitBounds(t.layer.getBounds(), { padding: [40, 40], maxZoom: 16 });
			this.render_summary();
		});
	}

	// Telefon ba'zan uzoq vaqt nuqta yubormaydi (ilova to'xtatilgan, GPS signal yo'q). Bunday uzilishni
	// to'g'ri chiziq bilan tutashtirish yolg'on yo'l ko'rsatadi -> uzilish alohida (punktir) chiziladi,
	// OSRM orqali ko'chalar bo'yicha taxminiy yo'l qo'yiladi, masofaga esa faqat haqiqiy GPS qo'shiladi.
	add_track_point(p) {
		const t = this.track;
		const prev = t.pts[t.pts.length - 1];
		t.pts.push(p);
		if (prev && !this.is_gap(prev, p)) {
			t.km += L.latLng(prev.lat, prev.lon).distanceTo([p.lat, p.lon]) / 1000;
			t.line.addLatLng([p.lat, p.lon]);
			return;
		}
		if (prev) this.add_gap(prev, p);
		t.line = L.polyline([[p.lat, p.lon]], { color: "#2563eb", weight: 4, opacity: 0.85 }).addTo(t.layer);
	}

	is_gap(a, b) {
		const secs = this.to_moment(b.vaqt).diff(this.to_moment(a.vaqt), "seconds");
		const meters = L.latLng(a.lat, a.lon).distanceTo([b.lat, b.lon]);
		return secs > KX_GAP_SECONDS && meters > KX_GAP_METERS;
	}

	add_gap(a, b) {
		const t = this.track;
		const mins = Math.round(this.to_moment(b.vaqt).diff(this.to_moment(a.vaqt), "minutes", true));
		const tip = __("Ma'lumot yo'q: {0} daqiqa ({1} – {2})", [
			mins,
			this.to_moment(a.vaqt).format("HH:mm"),
			this.to_moment(b.vaqt).format("HH:mm"),
		]);
		const gap = {
			mins,
			line: L.polyline([[a.lat, a.lon], [b.lat, b.lon]], { color: "#9ca3af", weight: 3, dashArray: "6 8" })
				.bindTooltip(tip)
				.addTo(t.layer),
		};
		t.gaps.push(gap);
		if (L.latLng(a.lat, a.lon).distanceTo([b.lat, b.lon]) < KX_SNAP_MAX_METERS) this.snap_gap(t, gap, a, b, tip);
	}

	snap_gap(t, gap, a, b, tip) {
		// OSRM bepul demo serveri -> so'rovlar ketma-ket yuboriladi (serverni zo'riqtirmaslik uchun)
		const url = `${KX_OSRM_URL}${a.lon},${a.lat};${b.lon},${b.lat}?overview=full&geometries=geojson`;
		this.osrm_queue = (this.osrm_queue || Promise.resolve())
			.then(() => (this.track === t ? fetch(url).then((r) => r.json()) : null))
			.then((res) => {
				const route = res && res.routes && res.routes[0];
				if (!route || this.track !== t) return;
				t.layer.removeLayer(gap.line);
				gap.line = L.polyline(
					route.geometry.coordinates.map(([lon, lat]) => [lat, lon]),
					{ color: "#f97316", weight: 4, opacity: 0.8, dashArray: "8 8" }
				)
					.bindTooltip(tip + "<br>" + __("Ko'chalar bo'yicha taxminiy yo'l"))
					.addTo(t.layer);
			})
			.catch(() => null); // internet yoki OSRM ishlamasa to'g'ri punktir qoladi
	}

	extend_track(p) {
		const t = this.track;
		if (!t || t.imei !== p.gps_imei || p.vaqt.slice(0, 10) !== t.date || p.lat == null) return;
		const last = t.pts[t.pts.length - 1];
		if (last && p.vaqt <= last.vaqt) return;
		this.add_track_point(p);
		this.update_end(p);
		this.render_stops();
		// Kuzatilayotgan mashina ekrandan chiqib ketsa xarita unga ergashadi
		if (!this.map.getBounds().contains([p.lat, p.lon])) this.map.panTo([p.lat, p.lon]);
		this.render_summary();
	}

	// ------------------------------------------------------------------ to'xtashlar
	badge_icon(text, cls) {
		return L.divIcon({
			className: "kx-icon",
			html: `<div class="kx-badge ${cls}">${frappe.utils.escape_html(String(text))}</div>`,
			iconSize: [24, 24],
			iconAnchor: [12, 12],
		});
	}

	place_popup(title, lat, lon, rows = []) {
		rows = rows.concat([[__("Koordinata"), this.coord_html(lat, lon)]]);
		return `<div class="kx-popup">
			<div style="font-weight:600;font-size:14px;margin-bottom:4px">${title}</div>
			<table>${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("")}</table>
		</div>`;
	}

	update_end(p) {
		const t = this.track;
		const today = t.date === frappe.datetime.get_today();
		t.end.setLatLng([p.lat, p.lon]);
		t.end.bindTooltip((today ? __("Hozir") : __("Kun oxiri")) + " " + this.hhmm(p.vaqt), { direction: "right", offset: [12, 0] });
		t.end.bindPopup(this.place_popup(today ? __("Oxirgi joylashuv") : __("Kun oxiri"), p.lat, p.lon, [
			[__("Vaqt"), frappe.datetime.str_to_user(p.vaqt)],
		]));
	}

	// Ketma-ket nuqtalar birinchisidan KX_STOP_METERS radius ichida qolib, KX_STOP_MINUTES dan uzoq davom etsa -
	// bu to'xtash. Telefon turganda kam nuqta yuborishi mumkin: 2 nuqta orasida 30 daqiqa bo'lsa-yu joy
	// o'zgarmagan bo'lsa, bu ham to'xtash hisoblanadi.
	compute_stops(pts) {
		const ms = (p) => (p._ms = p._ms || this.to_moment(p.vaqt).valueOf());
		const dist = (a, b) => L.latLng(a.lat, a.lon).distanceTo([b.lat, b.lon]);
		const stops = [];
		let i = 0;
		while (i < pts.length) {
			const a = pts[i];
			let j = i;
			for (;;) {
				if (j + 1 < pts.length && dist(a, pts[j + 1]) <= KX_STOP_METERS) j++;
				// Bitta nuqta "sakrab" ketib, keyingisi yana shu joyda bo'lsa - bu GPS xatosi, to'xtash davom etadi
				else if (j + 2 < pts.length && dist(a, pts[j + 2]) <= KX_STOP_METERS) j += 2;
				else break;
			}
			const mins = (ms(pts[j]) - ms(a)) / 60000;
			if (j > i && mins >= KX_STOP_MINUTES) {
				const group = pts.slice(i, j + 1).filter((p) => dist(a, p) <= KX_STOP_METERS);
				const prev = stops[stops.length - 1];
				// GPS bir lahza "sakrab" ketsa bitta to'xtash ikkiga bo'linmasin
				if (prev && ms(a) - prev.to_ms < KX_STOP_MINUTES * 60000 && dist(prev, a) <= 2 * KX_STOP_METERS) {
					prev.to = pts[j].vaqt;
					prev.to_ms = ms(pts[j]);
					prev.mins = (prev.to_ms - prev.from_ms) / 60000;
					prev.last_idx = j;
				} else {
					stops.push({
						from: a.vaqt,
						to: pts[j].vaqt,
						from_ms: ms(a),
						to_ms: ms(pts[j]),
						mins,
						lat: group.reduce((s, p) => s + p.lat, 0) / group.length,
						lon: group.reduce((s, p) => s + p.lon, 0) / group.length,
						last_idx: j,
					});
				}
				i = j + 1;
			} else {
				i++;
			}
		}
		stops.forEach((s) => (s.ongoing = s.last_idx === pts.length - 1));
		return stops;
	}

	render_stops() {
		const t = this.track;
		t.stops = this.compute_stops(t.pts);
		t.stops_layer.clearLayers();
		t.stops.forEach((s, i) => {
			const range = `${this.hhmm(s.from)} – ${s.ongoing ? __("hozirgacha") : this.hhmm(s.to)}`;
			s.marker = L.marker([s.lat, s.lon], { icon: this.badge_icon(i + 1, "stop") })
				.bindTooltip(__("To'xtash {0}: {1} ({2})", [i + 1, range, this.duration_text(s.mins)]))
				.bindPopup(this.place_popup(__("To'xtash {0}", [i + 1]), s.lat, s.lon, [
					[__("Vaqt"), range],
					[__("Davomiyligi"), this.duration_text(s.mins)],
				]))
				.addTo(t.stops_layer);
		});
	}

	focus_place(kind, idx) {
		const t = this.track;
		if (!t) return;
		const m = kind === "start" ? t.start : kind === "end" ? t.end : t.stops[idx] && t.stops[idx].marker;
		if (!m) return;
		this.map.setView(m.getLatLng(), Math.max(this.map.getZoom(), 16));
		m.openPopup();
	}

	render_summary() {
		const t = this.track;
		if (!t) return this.$summary.empty();
		const max_speed = t.pts.reduce((m, p) => Math.max(m, flt(p.tezlik)), 0);
		const first = t.pts[0].vaqt;
		const last = t.pts[t.pts.length - 1].vaqt;
		const gap_mins = t.gaps.reduce((s, g) => s + g.mins, 0);
		const p = this.points[t.imei] || { gps_imei: t.imei };
		const legend = (style, text) =>
			`<span style="display:inline-block;width:18px;border-top:${style};vertical-align:middle;margin-right:4px"></span>${text}`;
		const gaps_html = t.gaps.length
			? `<div style="margin-top:6px;color:var(--orange-600)">${__("Uzilishlar: {0} ta, jami {1} daqiqa ma'lumot yo'q", [t.gaps.length, gap_mins])}</div>`
			: "";
		const stop_mins = t.stops.reduce((s, x) => s + x.mins, 0);
		// Harakat vaqti: ketma-ket nuqtalar orasidagi vaqt (bitta to'xtash ichidagisi va uzilishlar hisobga olinmaydi)
		const ms = (p) => (p._ms = p._ms || this.to_moment(p.vaqt).valueOf());
		const same_stop = (a, b) => t.stops.some((s) => ms(a) >= s.from_ms && ms(b) <= s.to_ms);
		let move_mins = 0;
		for (let k = 1; k < t.pts.length; k++) {
			const a = t.pts[k - 1];
			const b = t.pts[k];
			if (!same_stop(a, b) && !this.is_gap(a, b)) move_mins += (ms(b) - ms(a)) / 60000;
		}
		const today = t.date === frappe.datetime.get_today();
		const fp = t.pts[0];
		const lp = t.pts[t.pts.length - 1];
		const row = (kind, idx, badge, cls, title, sub) => `
			<div class="kx-stop-row" data-kind="${kind}" data-idx="${idx}">
				<div class="kx-badge ${cls}">${badge}</div>
				<div><b>${title}</b><div class="text-muted">${sub}</div></div>
			</div>`;
		const stops_html = `<div class="kx-stops">
			<div style="font-weight:600;margin-bottom:2px">${__("To'xtashlar ({0} daqiqadan ko'p)", [KX_STOP_MINUTES])}: ${t.stops.length}</div>
			${row("start", 0, "S", "start", __("Boshlanish") + " · " + this.hhmm(fp.vaqt), this.coord_text(fp.lat, fp.lon))}
			${t.stops
				.map((s, i) =>
					row(
						"stop",
						i,
						i + 1,
						"stop",
						`${this.hhmm(s.from)} – ${s.ongoing ? __("hozirgacha") : this.hhmm(s.to)} · ${this.duration_text(s.mins)}`,
						this.coord_text(s.lat, s.lon)
					)
				)
				.join("")}
			${row("end", 0, "F", "end", (today ? __("Hozir") : __("Kun oxiri")) + " · " + this.hhmm(lp.vaqt), this.coord_text(lp.lat, lp.lon))}
		</div>`;
		this.$summary.html(`
			<div style="font-weight:600;margin-bottom:4px">${frappe.utils.escape_html(this.label(p))} · ${frappe.datetime.str_to_user(t.date)}</div>
			<div>${__("Yurgan masofa (GPS)")}: <b>${flt(t.km, 1)} km</b></div>
			<div>${__("Maks. tezlik")}: <b>${flt(max_speed, 0)} ${__("km/soat")}</b></div>
			<div>${__("Vaqt")}: ${this.to_moment(first).format("HH:mm")} – ${this.to_moment(last).format("HH:mm")}</div>
			<div>${__("Turgan vaqti")}: <b>${this.duration_text(stop_mins)}</b> · ${__("Harakatda")}: <b>${this.duration_text(move_mins)}</b></div>
			<div class="text-muted">${__("Nuqtalar")}: ${t.pts.length}</div>
			${gaps_html}
			${stops_html}
			<div class="text-muted" style="margin-top:6px;font-size:11px;line-height:1.7">
				${legend("4px solid #2563eb", __("GPS bo'yicha"))}<br>
				${legend("4px dashed #f97316", __("Uzilish: ko'chalar bo'yicha taxminiy"))}<br>
				${legend("3px dashed #9ca3af", __("Uzilish: yo'l topilmadi"))}
			</div>
		`);
	}

	clear_track() {
		if (this.track) this.map.removeLayer(this.track.layer);
		this.track = null;
		this.render_summary();
	}
}
