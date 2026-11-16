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
				// avval resolve: d.hide() onhide'ni chaqiradi, hal bo'lgan Promise'ga reject ta'sir qilmaydi
				resolve(certs[Number(v.key)]);
				d.hide();
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
		carieer.didox.warn(res);
	} catch (e) {
		carieer.didox.fail(e);
	}
};

carieer.didox.warn = (res) => {
	if (res && res.warning)
		frappe.msgprint({ title: __("Soliq ogohlantirishi"), message: res.warning });
};

// Kiruvchi hujjatni qabul qilish: Didox bergan matnga imzo qo'yamiz, server uni sotuvchi imzosiga qo'shadi
carieer.didox.qabul_qilish = async (hujjat, company) => {
	try {
		const info = await carieer.didox.call("qabul_malumoti", { hujjat });
		const signature = await carieer.didox.sign(company, info.data, info.inn);
		const res = await carieer.didox.call("qabul_qilish", { hujjat, signature });
		frappe.show_alert({ message: __("Hujjat qabul qilindi"), indicator: "green" });
		carieer.didox.warn(res);
	} catch (e) {
		carieer.didox.fail(e);
	}
};

carieer.didox.ask_izoh = (title, label) =>
	new Promise((resolve) =>
		frappe.prompt(
			{ fieldname: "izoh", fieldtype: "Small Text", label, reqd: 1 },
			(v) => resolve(v.izoh.trim()),
			title,
			__("Davom etish")
		)
	);

carieer.didox.rad_etish = async (hujjat, company) => {
	const izoh = await carieer.didox.ask_izoh(
		__("Hujjatni rad etish"),
		__("Sababi (kontragentga ko'rinadi)")
	);
	try {
		const info = await carieer.didox.call("rad_malumoti", { hujjat, izoh });
		const signature = await carieer.didox.sign(company, info.data, info.inn);
		await carieer.didox.call("rad_etish", { hujjat, izoh, signature });
		frappe.show_alert({ message: __("Hujjat rad etildi"), indicator: "orange" });
	} catch (e) {
		carieer.didox.fail(e);
	}
};

// Kiruvchi faktura -> Приход (Purchase Invoice qoralamasi): har qatorga ERPNext tovari tanlanadi
carieer.didox.prixod = async (frm) => {
	const m = await carieer.didox.call("prixod_malumoti", { hujjat: frm.doc.name });
	const d = new frappe.ui.Dialog({
		title: __("Приход yaratish"),
		size: "extra-large",
		fields: [
			{
				fieldname: "supplier",
				fieldtype: "Link",
				options: "Supplier",
				label: __("Yetkazib beruvchi"),
				default: m.supplier,
				description: m.supplier
					? ""
					: __("Topilmadi: bo'sh qoldirsangiz «{0}» (INN {1}) yangi yaratiladi", [
							m.kontragent,
							m.inn,
					  ]),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "ombor",
				fieldtype: "Link",
				options: "Warehouse",
				label: __("Ombor"),
				default: m.ombor,
				get_query: () => ({ filters: { company: frm.doc.company, is_group: 0 } }),
			},
			{ fieldtype: "Section Break" },
			{
				fieldname: "qatorlar",
				fieldtype: "Table",
				label: __("Faktura qatorlari"),
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: true,
				data: m.qatorlar,
				fields: [
					{ fieldname: "ordno", fieldtype: "Int", label: "№", read_only: 1, in_list_view: 1, columns: 1 },
					{ fieldname: "nomi", fieldtype: "Data", label: __("Faktura bo'yicha"), read_only: 1, in_list_view: 1, columns: 3 },
					{ fieldname: "mxik", fieldtype: "Data", label: __("MXIK"), read_only: 1, in_list_view: 1, columns: 2 },
					{ fieldname: "miqdor", fieldtype: "Float", label: __("Miqdor"), read_only: 1, in_list_view: 1, columns: 1 },
					{ fieldname: "jami", fieldtype: "Currency", label: __("Jami"), read_only: 1, in_list_view: 1, columns: 1 },
					{ fieldname: "item_code", fieldtype: "Link", options: "Item", label: __("ERPNext tovari"), reqd: 1, in_list_view: 1, columns: 2 },
				],
			},
			{
				fieldtype: "HTML",
				options: `<p class="text-muted small">${__(
					"MXIK bo'yicha topilgan tovar oldindan tanlangan. Qo'lda tanlangan tovarga fakturadagi MXIK yozib qo'yiladi - keyingi safar o'zi topiladi. Приход qoralama bo'lib yaratiladi, tekshirib Submit qiling."
				)} ${m.qqs_tolovchi ? __("QQS alohida soliq qatori bo'ladi.") : __("QQS tannarxga qo'shiladi (firma QQS to'lovchi emas).")}</p>`,
			},
		],
		primary_action_label: __("Приход yaratish"),
		primary_action: async (v) => {
			const tanlov = (v.qatorlar || []).map((r) => ({ ordno: r.ordno, item_code: r.item_code }));
			const pi = await carieer.didox.call("prixod_yaratish", {
				hujjat: frm.doc.name,
				tanlov,
				supplier: v.supplier,
				ombor: v.ombor,
			});
			d.hide();
			frappe.show_alert({ message: __("Приход qoralamasi yaratildi: {0}", [pi]), indicator: "green" });
			frappe.set_route("Form", "Purchase Invoice", pi);
		},
	});
	d.show();
};

carieer.didox.bekor_qilish = async (hujjat, company) => {
	try {
		const info = await carieer.didox.call("bekor_malumoti", { hujjat });
		const signature = await carieer.didox.sign(company, info.data, info.inn);
		await carieer.didox.call("bekor_qilish", { hujjat, signature });
		frappe.show_alert({ message: __("Hujjat bekor qilindi"), indicator: "orange" });
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

// ------------------------------------------------------------------ TTN, ishonchnoma, shartnoma
// Hujjat Didox'da qoralama bo'lib yaratiladi, so'ng ERI bilan imzolab yuborish taklif qilinadi.
carieer.didox.yaratildi = async (hujjat, company, nomi) => {
	frappe.show_alert({ message: __("{0} qoralamasi Didox'da yaratildi", [nomi]), indicator: "green" });
	frappe.confirm(
		__("{0} qoralamasi yaratildi. Hozir ERI bilan imzolab yuborasizmi?", [nomi]),
		async () => {
			await carieer.didox.imzolash(hujjat, company);
			frappe.set_route("Form", "Didox Hujjat", hujjat);
		},
		() => frappe.set_route("Form", "Didox Hujjat", hujjat)
	);
};

carieer.didox.pinfl_field = (fieldname, label, reqd = 1) => ({
	fieldname,
	fieldtype: "Data",
	label,
	reqd,
	length: 14,
	description: __("14 ta raqam"),
});

// viloyat tanlanganda tuman ro'yxati shu viloyatnikiga almashadi
carieer.didox.manzil_fields = (prefix, label, regions) => [
	{ fieldtype: "Section Break", label },
	{
		fieldname: `${prefix}_viloyat`,
		fieldtype: "Select",
		label: __("Viloyat"),
		reqd: 1,
		options: [""].concat(regions.map((r) => ({ value: String(r.regionId), label: r.name }))),
	},
	{ fieldname: `${prefix}_tuman`, fieldtype: "Select", label: __("Tuman"), reqd: 1, options: [""] },
	{ fieldtype: "Column Break" },
	{ fieldname: `${prefix}_manzil`, fieldtype: "Data", label: __("Manzil"), reqd: 1 },
];

carieer.didox.tuman_ulash = (d, prefix, districts, tanlangan) => {
	const viloyat = d.fields_dict[`${prefix}_viloyat`];
	const yangila = () => {
		const id = Number(d.get_value(`${prefix}_viloyat`));
		const opts = [""].concat(
			districts
				.filter((x) => Number(x.regionId) === id)
				.map((x) => ({ value: String(x.districtCode), label: x.name }))
		);
		d.set_df_property(`${prefix}_tuman`, "options", opts);
	};
	viloyat.df.onchange = yangila;
	yangila();
	if (tanlangan) d.set_value(`${prefix}_tuman`, String(tanlangan));
};

carieer.didox.ttn = async (frm) => {
	const m = await carieer.didox.call("ttn_malumoti", { sotuv: frm.doc.name });
	if (m.mavjud.length) {
		const ochish = await new Promise((resolve) =>
			frappe.confirm(
				__("Bu sotuvga TTN allaqachon yaratilgan: {0}. Uni ochasizmi? (Yo'q - yangisini yaratish)", [
					m.mavjud.join(", "),
				]),
				() => resolve(true),
				() => resolve(false)
			)
		);
		if (ochish) return frappe.set_route("Form", "Didox Hujjat", m.mavjud[0]);
	}
	const tovarlar = m.tovarlar.map((t) => `${t.nomi}: ${t.miqdor} × ${format_currency(t.narx)}`).join("<br>");
	const d = new frappe.ui.Dialog({
		title: __("TTN (yuk xati) yaratish"),
		size: "large",
		fields: [
			{ fieldtype: "HTML", options: `<p><b>${__("Yuk")}:</b><br>${tovarlar}</p>` },
			{
				fieldname: "tashuvchi",
				fieldtype: "Select",
				label: __("Kim tashiydi"),
				options: [
					{ value: "Mijoz", label: __("Mijoz (o'z mashinasi)") },
					{ value: "Karer", label: __("Karer (bizning texnika)") },
				],
				default: m.tashuvchi,
				reqd: 1,
			},
			{ fieldname: "mashina_raqami", fieldtype: "Data", label: __("Mashina raqami"), default: m.mashina_raqami, reqd: 1 },
			{ fieldname: "mashina_modeli", fieldtype: "Data", label: __("Mashina modeli"), default: m.mashina_modeli, reqd: 1 },
			{ fieldtype: "Column Break" },
			{ fieldname: "haydovchi_fio", fieldtype: "Data", label: __("Haydovchi FISh"), default: m.haydovchi_fio, reqd: 1 },
			carieer.didox.pinfl_field("haydovchi_pinfl", __("Haydovchi PINFL")),
			...carieer.didox.manzil_fields("yuklash", __("Yuklash joyi (Karer)"), m.regions),
			{ fieldname: "yuklash_masul_fio", fieldtype: "Data", label: __("Yuklovchi mas'ul FISh"), default: m.yuklash_masul_fio, reqd: 1 },
			carieer.didox.pinfl_field("yuklash_masul_pinfl", __("Yuklovchi mas'ul PINFL")),
			{
				fieldname: "saqlash",
				fieldtype: "Check",
				label: __("Yuklash ma'lumotlarini keyingi safar uchun eslab qolish"),
				default: 1,
			},
			...carieer.didox.manzil_fields("tushirish", __("Tushirish joyi (mijoz)"), m.regions),
			{ fieldname: "tushirish_masul_fio", fieldtype: "Data", label: __("Qabul qiluvchi FISh"), reqd: 1 },
			carieer.didox.pinfl_field("tushirish_masul_pinfl", __("Qabul qiluvchi PINFL")),
			{ fieldtype: "Section Break" },
			{ fieldname: "masofa", fieldtype: "Float", label: __("Masofa (km)"), reqd: 1 },
			{ fieldtype: "Column Break" },
			{ fieldname: "km_narxi", fieldtype: "Currency", label: __("1 km narxi"), default: 0 },
		],
		primary_action_label: __("TTN yaratish"),
		primary_action: async (v) => {
			const hujjat = await carieer.didox.call("ttn_yaratish", { sotuv: frm.doc.name, qiymatlar: v });
			d.hide();
			frm.reload_doc();
			carieer.didox.yaratildi(hujjat, frm.doc.company, __("TTN"));
		},
	});
	if (m.yuklash_viloyat) d.set_value("yuklash_viloyat", String(m.yuklash_viloyat));
	if (m.yuklash_manzil) d.set_value("yuklash_manzil", m.yuklash_manzil);
	if (m.yuklash_masul_pinfl) d.set_value("yuklash_masul_pinfl", m.yuklash_masul_pinfl);
	carieer.didox.tuman_ulash(d, "yuklash", m.districts, m.yuklash_tuman);
	carieer.didox.tuman_ulash(d, "tushirish", m.districts);
	d.show();
};

carieer.didox.tovar_jadvali = (narx) => ({
	fieldname: "tovarlar",
	fieldtype: "Table",
	label: __("Tovarlar"),
	in_place_edit: true,
	data: [],
	fields: [
		{ fieldname: "item_code", fieldtype: "Link", options: "Item", label: __("Tovar"), reqd: 1, in_list_view: 1, columns: 5 },
		{ fieldname: "miqdor", fieldtype: "Float", label: __("Miqdor"), reqd: 1, in_list_view: 1, columns: 2 },
	].concat(
		narx ? [{ fieldname: "narx", fieldtype: "Currency", label: __("Narx"), reqd: 1, in_list_view: 1, columns: 3 }] : []
	),
});

carieer.didox.ishonchnoma = (company) => {
	carieer.didox.call("firma_standartlari", { company }).then((s) => {
		const d = new frappe.ui.Dialog({
			title: __("Ishonchnoma (tovar olish uchun)"),
			size: "large",
			fields: [
				{ fieldname: "supplier", fieldtype: "Link", options: "Supplier", label: __("Yetkazib beruvchi"), reqd: 1 },
				{ fieldname: "raqam", fieldtype: "Data", label: __("Ishonchnoma raqami"), reqd: 1 },
				{ fieldtype: "Column Break" },
				{ fieldname: "sana", fieldtype: "Date", label: __("Berilgan sana"), default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: "muddat", fieldtype: "Date", label: __("Amal qilish muddati"), default: frappe.datetime.add_days(frappe.datetime.get_today(), 10), reqd: 1 },
				{ fieldtype: "Section Break", label: __("Shartnoma") },
				{ fieldname: "shartnoma_raqami", fieldtype: "Data", label: __("Shartnoma raqami") },
				{ fieldtype: "Column Break" },
				{ fieldname: "shartnoma_sanasi", fieldtype: "Date", label: __("Shartnoma sanasi") },
				{ fieldtype: "Section Break", label: __("Ishonchli shaxs (tovarni oladigan xodim)") },
				{ fieldname: "agent_fio", fieldtype: "Data", label: __("FISh"), reqd: 1 },
				{ fieldtype: "Column Break" },
				carieer.didox.pinfl_field("agent_pinfl", __("PINFL")),
				{ fieldtype: "Section Break", label: __("Bosh buxgalter") },
				{ fieldname: "buxgalter_fio", fieldtype: "Data", label: __("FISh"), default: s.buxgalter_fio, reqd: 1 },
				{ fieldtype: "Column Break" },
				{ ...carieer.didox.pinfl_field("buxgalter_pinfl", __("PINFL")), default: s.buxgalter_pinfl },
				{ fieldname: "saqlash", fieldtype: "Check", label: __("Buxgalterni eslab qolish"), default: 1 },
				{ fieldtype: "Section Break" },
				carieer.didox.tovar_jadvali(false),
			],
			primary_action_label: __("Ishonchnoma yaratish"),
			primary_action: async (v) => {
				const hujjat = await carieer.didox.call("ishonchnoma_yaratish", { company, qiymatlar: v });
				d.hide();
				carieer.didox.yaratildi(hujjat, company, __("Ishonchnoma"));
			},
		});
		d.show();
	});
};

carieer.didox.SHARTNOMA_BOLIMLARI = [
	{
		title: "1. Shartnoma predmeti",
		body: "Yetkazib beruvchi ushbu shartnomada ko'rsatilgan tovarlarni Xaridorga yetkazib beradi, Xaridor ularni qabul qiladi va haqini to'laydi.",
	},
	{
		title: "2. Narx va to'lov tartibi",
		body: "Tovar narxi shartnomaning tovarlar jadvalida ko'rsatilgan. To'lov Xaridor tomonidan pul o'tkazish yo'li bilan amalga oshiriladi.",
	},
	{
		title: "3. Yetkazib berish",
		body: "Tovar Yetkazib beruvchining omboridan yuk xati (TTN) va hisob-faktura asosida topshiriladi.",
	},
	{
		title: "4. Yakuniy qoidalar",
		body: "Shartnoma imzolangan kundan kuchga kiradi va ko'rsatilgan muddatgacha amal qiladi. Nizolar O'zbekiston Respublikasi qonunchiligiga muvofiq hal qilinadi.",
	},
];

carieer.didox.shartnoma = (company) => {
	const bugun = frappe.datetime.get_today();
	const d = new frappe.ui.Dialog({
		title: __("Shartnoma (mijoz bilan)"),
		size: "extra-large",
		fields: [
			{ fieldname: "customer", fieldtype: "Link", options: "Customer", label: __("Mijoz"), reqd: 1 },
			{ fieldname: "nomi", fieldtype: "Data", label: __("Shartnoma nomi"), default: __("Mahsulot yetkazib berish shartnomasi"), reqd: 1 },
			{ fieldname: "raqam", fieldtype: "Data", label: __("Shartnoma raqami"), reqd: 1 },
			{ fieldtype: "Column Break" },
			{ fieldname: "sana", fieldtype: "Date", label: __("Sana"), default: bugun, reqd: 1 },
			{ fieldname: "muddat", fieldtype: "Date", label: __("Tugash sanasi"), default: frappe.datetime.add_months(bugun, 12), reqd: 1 },
			{ fieldname: "joyi", fieldtype: "Data", label: __("Tuzilgan joyi"), reqd: 1 },
			{ fieldtype: "Section Break", label: __("Shartnoma matni") },
			{
				fieldtype: "HTML",
				options: `<p class="text-muted small">${__("Namuna matn. Yuborishdan oldin buxgalter yoki yurist tekshirib, kerakli joyini o'zgartirsin.")}</p>`,
			},
			{
				fieldname: "bolimlar",
				fieldtype: "Table",
				label: __("Bo'limlar"),
				in_place_edit: true,
				data: carieer.didox.SHARTNOMA_BOLIMLARI.map((b) => ({ ...b })),
				fields: [
					{ fieldname: "title", fieldtype: "Data", label: __("Sarlavha"), reqd: 1, in_list_view: 1, columns: 3 },
					{ fieldname: "body", fieldtype: "Small Text", label: __("Matn"), reqd: 1, in_list_view: 1, columns: 7 },
				],
			},
			{ fieldtype: "Section Break" },
			carieer.didox.tovar_jadvali(true),
		],
		primary_action_label: __("Shartnoma yaratish"),
		primary_action: async (v) => {
			const hujjat = await carieer.didox.call("shartnoma_yaratish", { company, qiymatlar: v });
			d.hide();
			carieer.didox.yaratildi(hujjat, company, __("Shartnoma"));
		},
	});
	d.fields_dict.customer.df.onchange = () => {
		const c = d.get_value("customer");
		if (!c) return;
		frappe.db.get_value("Customer", c, ["shartnoma_raqami"]).then(({ message }) => {
			if (message && message.shartnoma_raqami && !d.get_value("raqam"))
				d.set_value("raqam", message.shartnoma_raqami);
		});
	};
	d.show();
};
