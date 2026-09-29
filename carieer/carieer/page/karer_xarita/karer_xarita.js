// Texnikalar xaritasi: GPS (Traccar Client yoki GPS provayder) orqali kelgan oxirgi joylashuvlar,
// realtime yangilanish (carieer.api -> publish_realtime "karer_gps") va tanlangan kundagi yurgan yo'l.

frappe.pages["karer-xarita"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Texnikalar xaritasi"),
		single_column: true,
	});
	wrapper.xarita = new KarerXarita(page);
};

frappe.pages["karer-xarita"].on_page_show = function (wrapper) {
	wrapper.xarita && wrapper.xarita.on_show();
};

const KX_DEFAULT_CENTER = [41.3111, 69.2797]; // Toshkent
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

		this.add_style();
		this.make_filters();
		this.make_layout();

		Promise.all([frappe.require("leaflet.bundle.js"), frappe.require("leaflet.bundle.css")]).then(() => {
			this.make_map();
			this.load(true);
			frappe.realtime.on("karer_gps", (p) => this.on_point(p));
		});
		// "necha daqiqa oldin" va holat rangi vaqt o'tishi bilan o'zgaradi
		setInterval(() => this.render_all(), 30 * 1000);
	}

	on_show() {
		if (!this.map) return;
		setTimeout(() => this.map.invalidateSize(), 150);
		this.load(false);
	}

	// ------------------------------------------------------------------ UI
	make_filters() {
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
		this.page.add_menu_item(__("GPS Malumot ro'yxati"), () => frappe.set_route("List", "GPS Malumot"));
	}

	make_layout() {
		this.$body = $(`
			<div class="karer-xarita">
				<div class="kx-side">
					<div class="kx-summary"></div>
					<div class="kx-list"></div>
				</div>
				<div class="kx-map"></div>
			</div>
		`).appendTo(this.page.main);
		this.$list = this.$body.find(".kx-list");
		this.$summary = this.$body.find(".kx-summary");
		this.$map = this.$body.find(".kx-map");

		this.$list.on("click", ".kx-item", (e) => this.focus($(e.currentTarget).attr("data-imei")));
		this.$map.on("click", ".kx-track-btn", (e) => {
			this.device_field.set_value($(e.currentTarget).attr("data-imei"));
			this.show_track();
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
		if (document.getElementById("karer-xarita-style")) return;
		$(`<style id="karer-xarita-style">
			.karer-xarita { display: flex; gap: 12px; height: calc(100vh - 200px); min-height: 440px; }
			.kx-side { width: 290px; flex-shrink: 0; display: flex; flex-direction: column; gap: 8px; min-height: 0; }
			.kx-summary:empty { display: none; }
			.kx-summary { padding: 10px 12px; border: 1px solid var(--border-color); border-radius: var(--border-radius-md);
				background: var(--card-bg); font-size: var(--text-sm); }
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
				.karer-xarita { flex-direction: column; height: auto; }
				.kx-side { width: 100%; }
				.kx-list { max-height: 220px; }
				.kx-map { height: 60vh; flex: none; }
			}
		</style>`).appendTo("head");
	}

	// ------------------------------------------------------------------ ma'lumot
	load(fit) {
		frappe.call("carieer.api.get_live_positions").then((r) => {
			this.points = {};
			(r.message || []).forEach((p) => (this.points[p.gps_imei] = p));
			this.update_device_options();
			this.render_all();
			if (fit) this.fit_all();
		});
	}

	on_point(p) {
		const old = this.points[p.gps_imei] || {};
		// Telefon oflayn bufer'dagi eski nuqtalarni keyinroq yuboradi -> ular joriy joylashuvni almashtirmaydi
		if (old.vaqt && p.vaqt < old.vaqt) return;
		// texnika_turi/model faqat get_live_positions da keladi -> saqlab qolamiz
		this.points[p.gps_imei] = { ...old, ...p, vehicle: p.vehicle || old.vehicle };
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
		];
		if (p.texnika_turi || p.model) rows.push([__("Turi"), esc([p.texnika_turi, p.model].filter(Boolean).join(", "))]);
		if (p.batareya != null) rows.push([__("Batareya"), `${cint(p.batareya)}%`]);
		if (p.yoqilgi_darajasi) rows.push([__("Yoqilg'i"), `${flt(p.yoqilgi_darajasi, 1)} l`]);
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

	render_list() {
		const esc = frappe.utils.escape_html;
		const pts = Object.values(this.points).sort((a, b) => this.label(a).localeCompare(this.label(b)));
		if (!pts.length) {
			this.$list.html(`<div class="kx-empty">
				${__("Hali GPS ma'lumot yo'q.")}<br><br>
				${__("Traccar Client ilovasida server URL ni sozlang va Vehicle ning GPS IMEI maydoniga qurilma ID sini yozing.")}
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
					return `<div class="kx-item ${p.gps_imei === active ? "active" : ""}" data-imei="${esc(p.gps_imei)}">
						<div class="kx-title"><span class="kx-dot" style="background:${st.color}"></span>${esc(this.label(p))}</div>
						<div class="kx-meta">${st.label}${speed}${when ? " · " + when : ""}</div>
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
	}

	fit_all() {
		const ll = Object.values(this.points)
			.filter((p) => p.lat != null && p.vaqt)
			.map((p) => [p.lat, p.lon]);
		if (ll.length === 1) this.map.setView(ll[0], 15);
		else if (ll.length) this.map.fitBounds(ll, { padding: [40, 40], maxZoom: 15 });
	}

	// ------------------------------------------------------------------ yurgan yo'l
	show_track() {
		const imei = this.device_field.get_value();
		const date = this.date_field.get_value();
		if (!imei || !date) {
			frappe.msgprint(__("Texnika va sanani tanlang"));
			return;
		}
		frappe.call({ method: "carieer.api.get_track", args: { gps_imei: imei, date }, freeze: true }).then((r) => {
			this.clear_track();
			const pts = (r.message || []).filter((p) => p.lat != null && p.lon != null);
			if (!pts.length) {
				frappe.show_alert({ message: __("Bu kunda ma'lumot yo'q"), indicator: "orange" });
				return;
			}
			const latlngs = pts.map((p) => [p.lat, p.lon]);
			const line = L.polyline(latlngs, { color: "#2563eb", weight: 4, opacity: 0.8 });
			const start = L.circleMarker(latlngs[0], { radius: 6, color: "#fff", weight: 2, fillColor: "#2563eb", fillOpacity: 1 })
				.bindTooltip(__("Boshlanish") + ": " + frappe.datetime.str_to_user(pts[0].vaqt));
			const end = L.circleMarker(latlngs[latlngs.length - 1], { radius: 6, color: "#fff", weight: 2, fillColor: "#dc2626", fillOpacity: 1 })
				.bindTooltip(__("Oxirgi") + ": " + frappe.datetime.str_to_user(pts[pts.length - 1].vaqt));
			const layer = L.layerGroup([line, start, end]).addTo(this.map);
			this.track = { imei, date, layer, line, end, pts };
			this.map.fitBounds(line.getBounds(), { padding: [40, 40], maxZoom: 16 });
			this.render_summary();
		});
	}

	extend_track(p) {
		const t = this.track;
		if (!t || t.imei !== p.gps_imei || p.vaqt.slice(0, 10) !== t.date || p.lat == null) return;
		t.pts.push(p);
		t.line.addLatLng([p.lat, p.lon]);
		t.end.setLatLng([p.lat, p.lon]);
		this.render_summary();
	}

	render_summary() {
		const t = this.track;
		if (!t) return this.$summary.empty();
		let km = 0;
		let max_speed = 0;
		for (let i = 1; i < t.pts.length; i++) {
			km += L.latLng(t.pts[i - 1].lat, t.pts[i - 1].lon).distanceTo([t.pts[i].lat, t.pts[i].lon]) / 1000;
		}
		t.pts.forEach((p) => (max_speed = Math.max(max_speed, flt(p.tezlik))));
		const first = t.pts[0].vaqt;
		const last = t.pts[t.pts.length - 1].vaqt;
		const p = this.points[t.imei] || { gps_imei: t.imei };
		this.$summary.html(`
			<div style="font-weight:600;margin-bottom:4px">${frappe.utils.escape_html(this.label(p))} · ${frappe.datetime.str_to_user(t.date)}</div>
			<div>${__("Yurgan masofa")}: <b>${flt(km, 1)} km</b></div>
			<div>${__("Maks. tezlik")}: <b>${flt(max_speed, 0)} ${__("km/soat")}</b></div>
			<div>${__("Vaqt")}: ${this.to_moment(first).format("HH:mm")} – ${this.to_moment(last).format("HH:mm")}</div>
			<div class="text-muted">${__("Nuqtalar")}: ${t.pts.length}</div>
		`);
	}

	clear_track() {
		if (this.track) this.map.removeLayer(this.track.layer);
		this.track = null;
		this.render_summary();
	}
}
