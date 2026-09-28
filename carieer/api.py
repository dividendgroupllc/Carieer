"""Tashqi tizimlar uchun API (GPS provayder)."""

import hmac
import json

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime
from frappe.utils.password import get_decrypted_password


@frappe.whitelist(allow_guest=True, methods=["POST"])
def gps_push():
	"""GPS provayder shu endpointga ma'lumot yuboradi.

	POST /api/method/carieer.api.gps_push
	Header:  X-Karer-Token: <Karer Sozlamalari -> GPS API token>
	Body (JSON, bitta obyekt yoki ro'yxat):
	  {"imei": "358...", "time": "2026-09-28 10:15:00", "lat": 41.3, "lon": 69.2,
	   "speed": 34, "odometer": 125430.5, "fuel": 120.5, "engine_hours": 3500.2, "ignition": 1}
	"""
	token = frappe.get_request_header("X-Karer-Token")
	expected = get_decrypted_password(
		"Karer Sozlamalari", "Karer Sozlamalari", "gps_token", raise_exception=False
	)
	if not expected or not token or not hmac.compare_digest(token, expected):
		frappe.throw(_("Noto'g'ri token"), frappe.AuthenticationError)

	payload = frappe.request.get_json(silent=True) or json.loads(frappe.request.data or "{}")
	rows = payload if isinstance(payload, list) else [payload]
	saved = 0
	for d in rows:
		imei = str(d.get("imei") or "").strip()
		if not imei:
			continue
		vehicle = frappe.db.get_value("Vehicle", {"gps_imei": imei}, "name")
		doc = frappe.get_doc(
			{
				"doctype": "GPS Malumot",
				"vehicle": vehicle,
				"gps_imei": imei,
				"vaqt": get_datetime(d.get("time")) if d.get("time") else now_datetime(),
				"lat": d.get("lat"),
				"lon": d.get("lon"),
				"tezlik": d.get("speed"),
				"odometr": d.get("odometer"),
				"yoqilgi_darajasi": d.get("fuel"),
				"motor_soat": d.get("engine_hours"),
				"dvigatel_yoqilgan": 1 if d.get("ignition") else 0,
			}
		)
		doc.insert(ignore_permissions=True)
		saved += 1
		if vehicle and d.get("odometer"):
			frappe.db.sql(
				"update `tabVehicle` set last_odometer=%s where name=%s and ifnull(last_odometer,0) < %s",
				(int(float(d["odometer"])), vehicle, float(d["odometer"])),
			)
	frappe.db.commit()
	return {"saved": saved}
