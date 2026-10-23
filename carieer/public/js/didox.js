// Didox: E-IMZO bilan imzolash (brauzerda). Sotuv va Didox Hujjat formalari frappe.require bilan yuklaydi.
// E-IMZO kompyuterda ishlab turishi kerak: u brauzer bilan lokal websocket orqali gaplashadi.
// Didox'ga so'rovlar serverdan ketadi (carieer.didox.api), bu yerda faqat imzo qo'yiladi.

frappe.provide("carieer.didox");

carieer.didox.API = "carieer.didox.api.";

carieer.didox.call = (method, args) =>
	frappe.call({ method: carieer.didox.API + method, args, freeze: true }).then((r) => r.message);

// ------------------------------------------------------------------ E-IMZO
carieer.didox.eimzo = (plugin, name, args) =>
	new Promise((resolve, reject) => {
		const url =
			location.protocol === "https:"
				? "wss://127.0.0.1:64443/service/cryptapi"
				: "ws://127.0.0.1:64646/service/cryptapi";
		let ws;
		try {
			ws = new WebSocket(url);
		} catch (e) {
			reject(__("E-IMZO bilan ulanib bo'lmadi"));
			return;
		}
		ws.onerror = () =>
			reject(__("E-IMZO ishlamayapti. Dasturni ishga tushiring va sahifani yangilang."));
		ws.onopen = () => {
			const message = { name, arguments: args || [] };
			if (plugin) message.plugin = plugin;
			ws.send(JSON.stringify(message));
		};
		ws.onmessage = (e) => {
			ws.close();
			const data = JSON.parse(e.data);
			if (data.success === false) reject(data.reason || __("E-IMZO xatosi"));
			else resolve(data);
		};
	});

carieer.didox.apikey = async () => {
	const keys = await carieer.didox.call("eimzo_kalitlari");
	if (keys && keys.length) await carieer.didox.eimzo(null, "apikey", keys);
};

carieer.didox.alias_field = (alias, key) => {
	const part = (alias || "").split(",").find((p) => p.startsWith(key + "="));
	return part ? part.slice(key.length + 1) : "";
};

carieer.didox.choose_key = async (inn) => {
	const res = await carieer.didox.eimzo("pfx", "list_all_certificates");
	const all = res.certificates || [];
	if (!all.length)
		throw __("Kompyuterda ERI kaliti topilmadi (C:\\DSKEYS papkasini tekshiring)");
	const mine = all.filter((c) => (c.alias || "").includes("=" + inn));
	const certs = mine.length ? mine : all;
	if (certs.length === 1) return certs[0];

	const label = (c) =>
		[carieer.didox.alias_field(c.alias, "o"), carieer.didox.alias_field(c.alias, "cn"), c.name]
			.filter(Boolean)
			.join(" — ");
	return new Promise((resolve, reject) => {
		const d = new frappe.ui.Dialog({
			title: __("ERI kalitini tanlang"),
			fields: [
				{
					fieldname: "key",
					fieldtype: "Select",
					label: __("Kalit"),
					reqd: 1,
					options: certs.map((c, i) => ({ value: String(i), label: label(c) })),
				},
			],
			primary_action_label: __("Tanlash"),
			primary_action: (v) => {
				d.hide();
				resolve(certs[Number(v.key)]);
			},
		});
		d.onhide = () => reject(__("Bekor qilindi"));
		d.show();
	});
};

// base64 ma'lumotni imzolaydi va Didox timestamp'i qo'shilgan imzoni qaytaradi
carieer.didox.sign = async (company, data, inn) => {
	await carieer.didox.apikey();
	const cert = await carieer.didox.choose_key(inn);
	const key = await carieer.didox.eimzo("pfx", "load_key", [
		cert.disk,
		cert.path,
		cert.name,
		cert.alias,
	]);
	const pkcs7 = await carieer.didox.eimzo("pkcs7", "create_pkcs7", [data, key.keyId, "no"]);
	return carieer.didox.call("timestamp", {
		company,
		pkcs7: pkcs7.pkcs7_64,
		signature_hex: pkcs7.signature_hex,
	});
};

carieer.didox.fail = (e) => {
	if (e && typeof e === "string")
		frappe.msgprint({ title: __("Didox"), message: e, indicator: "red" });
};

// ------------------------------------------------------------------ amallar
carieer.didox.eri_login = async (company) => {
	try {
		const info = await carieer.didox.call("kirish_malumoti", { company });
		const signature = await carieer.didox.sign(company, info.data, info.inn);
		await carieer.didox.call("eri_login", { company, signature });
		frappe.show_alert({ message: __("Didox'ga kirildi: {0}", [company]), indicator: "green" });
	} catch (e) {
		carieer.didox.fail(e);
		throw e;
	}
};

carieer.didox.imzolash = async (hujjat, company) => {
	try {
		const info = await carieer.didox.call("imzo_malumoti", { hujjat });
		const signature = await carieer.didox.sign(company, info.data, info.inn);
		const res = await carieer.didox.call("imzolash", { hujjat, signature });
		frappe.show_alert({ message: __("Hujjat imzolanib yuborildi"), indicator: "green" });
		if (res && res.warning)
			frappe.msgprint({ title: __("Soliq ogohlantirishi"), message: res.warning });
	} catch (e) {
		carieer.didox.fail(e);
	}
};

carieer.didox.ask_company = (title, action) => {
	frappe.prompt(
		{
			fieldname: "company",
			fieldtype: "Link",
			options: "Company",
			label: __("Firma"),
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		(v) => action(v.company),
		title
	);
};
