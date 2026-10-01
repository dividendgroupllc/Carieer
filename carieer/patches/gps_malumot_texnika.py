# GPS Malumot: eski nuqtalarga mashina raqami, turi, markasi va modeli qo'yiladi (Vehicle.gps_imei bo'yicha).

import frappe

from carieer.api import sync_vehicle_gps


def execute():
	for v in frappe.get_all("Vehicle", filters={"gps_imei": ["is", "set"]}, fields=["name", "gps_imei", "texnika_turi", "make", "model"]):
		sync_vehicle_gps(v)
	frappe.db.sql("update `tabGPS Malumot` set qurilma='Traccar Client' where ifnull(qurilma, '') = ''")
