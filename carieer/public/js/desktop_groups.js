// Desktop: Carieer ikonkalari firma bo'yicha sarlavha ostida turadi - avval «Beton Zavod», keyin «Karer»,
// qolganlari (ERPNext ...) eng pastda. Firma ikonka nomining oxiridan aniqlanadi («Kassa Karer», «Panel Beton»)
// va sarlavha ostida qisqa nom ko'rinadi («Kassa»). Desktop'ni tahrirlash rejimida hech narsa o'zgarmaydi.

frappe.provide("carieer");

carieer.DESKTOP_GROUPS = [
	{ suffix: " Beton", title: __("Beton Zavod") },
	{ suffix: " Karer", title: __("Karer"), extra: ["Didox"] },
];

carieer.desktop_group = function (label) {
	return carieer.DESKTOP_GROUPS.find(
		(g) => label.endsWith(g.suffix) || (g.extra || []).includes(label)
	);
};

carieer.group_desktop = function (desktop) {
	if (!desktop || desktop.edit_mode || frappe.is_mobile()) return;
	const $grid = desktop.wrapper.find(".icons-container > .icons").first();
	if (!$grid.length) return;

	const sections = carieer.DESKTOP_GROUPS.map((group) => ({ group, icons: [] }));
	$grid.children(".desktop-icon").each(function () {
		const group = carieer.desktop_group($(this).attr("data-id") || "");
		if (group) sections.find((s) => s.group === group).icons.push(this);
	});
	if (!sections.some((s) => s.icons.length)) return;

	sections
		.filter((s) => s.icons.length)
		.forEach(({ group, icons }) => {
			const $section = $(`<div class="carieer-desktop-group">
				<div class="carieer-desktop-title">${frappe.utils.escape_html(group.title)}</div>
				<div class="icons" style="display: grid"></div>
			</div>`).insertBefore($grid);
			const $icons = $section.find(".icons");
			icons.forEach((el) => {
				carieer.strip_group_suffix($(el).find(".icon-title"));
				$icons.append(el);
			});
		});

	if ($grid.children().length) {
		$(`<div class="carieer-desktop-title">${__("Boshqa")}</div>`).insertBefore($grid);
	} else {
		$grid.hide();
	}
};

// «Hisobotlar Karer» papkasi ochilganda ham: «Баланс Karer» -> «Баланс»
carieer.strip_group_suffix = function ($el) {
	const text = $el.text().trim();
	const group = carieer.desktop_group(text);
	if (group && group.suffix && text.endsWith(group.suffix)) {
		$el.text(text.slice(0, -group.suffix.length));
	}
};

$(document).on("desktop_screen", (e, args) => carieer.group_desktop(args && args.desktop));
$(document).on("shown.bs.modal", (e) => {
	const $modal = $(e.target);
	if (!$modal.find(".desktop-icon").length) return;
	$modal.find(".modal-title, .icon-title").each((i, el) => carieer.strip_group_suffix($(el)));
});

frappe.dom.set_style(`
	.carieer-desktop-group { margin-bottom: var(--margin-lg); }
	.carieer-desktop-group .icons { grid-template-rows: none; }
	.carieer-desktop-title {
		font-size: var(--text-lg);
		font-weight: var(--weight-semibold);
		color: var(--heading-color);
		margin: var(--margin-md) 0 var(--margin-sm);
	}
`);
