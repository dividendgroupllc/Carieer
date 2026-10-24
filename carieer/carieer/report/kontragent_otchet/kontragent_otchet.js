// Kontragent qatori ochilganda ostida uning hujjatlari (sana, hujjat, tovarlar). Filtrlar - hisobot JSON'ida.
frappe.query_reports["Kontragent Otchet"] = {
	tree: true,
	name_field: "name",
	parent_field: "parent_row",
	initial_depth: 0,
};
