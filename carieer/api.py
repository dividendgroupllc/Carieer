"""GPS: tashqi tizimlar uchun API (Traccar Client telefon ilovasi va GPS trekkerlar).

Xarita uchun alohida JS sahifa yo'q - Frappe'ning o'z «Map» ko'rinishi ishlatiladi:
  - Vehicle ro'yxati -> Map: har bir texnikaning oxirgi joyi (latitude / longitude maydonlari)
  - GPS Malumot ro'yxati -> Map: tanlangan texnika / kun bo'yicha nuqtalar (yurgan yo'li)
"""

import hashlib
import hmac
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, get_system_timezone, now_datetime


def check_token(token: str | None):
	from frappe.utils.password import get_decrypted_password

	expected = get_decrypted_password(
		"Karer Sozlamalari", "Karer Sozlamalari", "gps_token", raise_exception=False
	)
	if not expected or not token or not hmac.compare_digest(str(token), expected):
		frappe.throw(_("Noto'g'ri token"), frappe.AuthenticationError)


def save_point(imei: str, **values) -> dict | None:
	"""Bitta GPS nuqtani saqlaydi va texnikaning oxirgi joyini (Vehicle.latitude / longitude) yangilaydi.
	Aynan shu nuqta (vaqt + koordinata) oldin saqlangan bo'lsa None qaytaradi: telefon yangi joylashuvni
	aniqlay olmasa, "heartbeat"da oxirgi eski nuqtani qayta-qayta yuboradi."""
	vehicle = (
		frappe.db.get_value("Vehicle", {"gps_imei": imei}, ["name", "company"], as_dict=True)
		or frappe._dict()
	)
	doc = frappe.get_doc(
		{
			"doctype": "GPS Malumot",
			"vehicle": vehicle.name,
			"company": vehicle.company,
			"gps_imei": imei,
			**values,
		}
	)
	doc.vaqt = get_datetime(doc.vaqt or now_datetime()).replace(microsecond=0)
	# Traccar bir nuqtani bir vaqtda parallel bir necha marta yuboradi, shunda "exists" tekshiruvi hammasiga
	# "yo'q" deydi. Takrorni bazadagi unique `nuqta_kalit` ishonchli to'xtatadi. (Nomni kalit qilish
	# ishlamaydi: autoname=hash da Frappe PK to'qnashuvida yangi tasodifiy nom bilan qayta yozadi.)
	key = f"{imei}|{doc.vaqt}|{flt(doc.latitude, 7)}|{flt(doc.longitude, 7)}"
	doc.nuqta_kalit = hashlib.sha1(key.encode()).hexdigest()
	if frappe.db.exists("GPS Malumot", {"nuqta_kalit": doc.nuqta_kalit}):
		return None
	try:
		doc.insert(ignore_permissions=True)
	except frappe.UniqueValidationError:
		frappe.clear_messages()
		return None
	if vehicle.name:
		update_vehicle_position(vehicle.name, doc)
	return {"gps_imei": imei, "vehicle": vehicle.name, "vaqt": str(doc.vaqt)}


def update_vehicle_position(vehicle: str, point):
	"""Vehicle'dagi oxirgi joy (faqat yangiroq nuqta bo'lsa): Vehicle ro'yxatining Map ko'rinishi shu bilan ishlaydi."""
	last = frappe.db.get_value("Vehicle", vehicle, "gps_vaqt")
	if last and get_datetime(last) > get_datetime(point.vaqt):
		return
	frappe.db.set_value(
		"Vehicle",
		vehicle,
		{
			"latitude": flt(point.latitude),
			"longitude": flt(point.longitude),
			"gps_vaqt": point.vaqt,
			"gps_tezlik": flt(point.tezlik),
		},
		update_modified=False,
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def gps_push():
	"""GPS provayder shu endpointga ma'lumot yuboradi.

	POST /api/method/carieer.api.gps_push
	Header:  X-Karer-Token: <Karer Sozlamalari -> GPS API token>
	Body (JSON, bitta obyekt yoki ro'yxat):
	  {"imei": "358...", "time": "2026-09-28 10:15:00", "lat": 41.3, "lon": 69.2,
	   "speed": 34, "odometer": 125430.5, "fuel": 120.5, "engine_hours": 3500.2, "ignition": 1}
	"""
	check_token(frappe.get_request_header("X-Karer-Token"))

	payload = frappe.request.get_json(silent=True)
	if payload is None:
		try:
			payload = json.loads(frappe.request.data or "{}")
		except ValueError:
			frappe.throw(_("JSON noto'g'ri formatda"), frappe.ValidationError)
	rows = payload if isinstance(payload, list) else [payload]
	saved = 0
	for d in rows:
		if not isinstance(d, dict):
			continue
		imei = str(d.get("imei") or "").strip()
		# Koordinatasiz nuqta xaritada (0, 0) bo'lib chiqmasin
		if not imei or d.get("lat") in (None, "") or d.get("lon") in (None, ""):
			continue
		point = save_point(
			imei,
			vaqt=get_datetime(d.get("time")) if d.get("time") else now_datetime(),
			latitude=d.get("lat"),
			longitude=d.get("lon"),
			tezlik=d.get("speed"),
			odometr=d.get("odometer"),
			yoqilgi_darajasi=d.get("fuel"),
			motor_soat=d.get("engine_hours"),
			dvigatel_yoqilgan=1 if d.get("ignition") else 0,
			qurilma="GPS trekker",
		)
		if not point:
			continue
		saved += 1
		odometer = flt(d.get("odometer"))
		if point["vehicle"] and odometer > 0:
			frappe.db.sql(
				"update `tabVehicle` set last_odometer=%s where name=%s and ifnull(last_odometer,0) < %s",
				(int(odometer), point["vehicle"], odometer),
			)
	frappe.db.commit()
	return {"saved": saved}


# ------------------------------------------------------------------ Traccar Client (telefon)
@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def traccar(**kwargs):
	"""Traccar Client (Android/iOS) ilovasi uchun endpoint (OsmAnd protokoli).

	Ilovadagi "URL сервера":
	  http://<server>:<port>/api/method/carieer.api.traccar?token=<GPS API token>
	"Идентификатор устройства" -> Vehicle ning "GPS qurilma IMEI" maydoniga yoziladi.

	Ikkala format qabul qilinadi:
	  - yangi ilova: JSON {"device_id": "...", "location": {"timestamp", "coords": {...}, "battery": {...}}}
	  - eski ilova:  ?id=...&lat=...&lon=...&timestamp=...&speed=<uzel>&bearing=...&batt=...
	"""
	form = frappe.form_dict
	# JSON so'rovda form_dict = JSON tanasi, URL dagi ?token= esa faqat request.args da qoladi
	check_token(
		frappe.request.args.get("token") or form.get("token") or frappe.get_request_header("X-Karer-Token")
	)

	body = frappe.request.get_json(silent=True) if frappe.request.data else None
	points = (
		parse_traccar_json(body)
		if isinstance(body, dict) and body.get("location")
		else parse_traccar_query(form)
	)

	qurilma = traccar_source()
	saved = skipped = 0
	for imei, values in points:
		if not imei or values.get("latitude") is None or values.get("longitude") is None:
			continue
		if save_point(imei, qurilma=qurilma, **values):
			saved += 1
		else:
			skipped += 1
	if not saved and not skipped:
		frappe.log_error(
			title="Traccar: nuqta topilmadi", message=frappe.as_json({"form": form, "body": body})
		)
	frappe.db.commit()
	return {"saved": saved}


def traccar_source() -> str:
	"""User-Agent bo'yicha qaysi ilova/telefon yuborganini aniqlaydi (masalan "Traccar Client (Android)")."""
	ua = (frappe.get_request_header("User-Agent") or "").lower()
	if "android" in ua or "okhttp" in ua or "dalvik" in ua:
		return "Traccar Client (Android)"
	if "iphone" in ua or "ios" in ua or "cfnetwork" in ua or "darwin" in ua:
		return "Traccar Client (iOS)"
	return "Traccar Client"


def parse_traccar_json(body: dict) -> list[tuple[str, dict]]:
	device_id = str(body.get("device_id") or "").strip()
	locations = body["location"] if isinstance(body["location"], list) else [body["location"]]
	out = []
	for loc in locations:
		c = loc.get("coords") or {}
		speed = flt(c.get("speed"))  # m/s, noma'lum bo'lsa -1
		battery = loc.get("battery") or {}
		out.append(
			(
				device_id,
				{
					"vaqt": to_system_time(loc.get("timestamp")),
					"latitude": c.get("latitude"),
					"longitude": c.get("longitude"),
					"tezlik": round(speed * 3.6, 1) if speed > 0 else 0,
					"yonalish": c.get("heading") if flt(c.get("heading")) >= 0 else None,
					"batareya": round(flt(battery.get("level")) * 100)
					if battery.get("level") is not None
					else None,
					"dvigatel_yoqilgan": 1 if loc.get("is_moving") else 0,
				},
			)
		)
	return out


def parse_traccar_query(form) -> list[tuple[str, dict]]:
	lat, lon = form.get("lat"), form.get("lon")
	if (lat is None or lon is None) and form.get("location"):  # location=lat,lon
		lat, _sep, lon = str(form.location).partition(",")
	return [
		(
			str(form.get("id") or form.get("deviceid") or "").strip(),
			{
				"vaqt": to_system_time(form.get("timestamp")),
				"latitude": flt(lat) if lat not in (None, "") else None,
				"longitude": flt(lon) if lon not in (None, "") else None,
				"tezlik": round(flt(form.get("speed")) * 1.852, 1),  # uzel -> km/soat
				"yonalish": flt(form.get("bearing") or form.get("heading")) or None,
				"batareya": flt(form.get("batt")) if form.get("batt") not in (None, "") else None,
			},
		)
	]


def to_system_time(value) -> datetime:
	"""Unix vaqt (s yoki ms) yoki ISO (UTC 'Z') -> tizim vaqt zonasidagi naive datetime."""
	if value in (None, ""):
		return now_datetime()
	tz = ZoneInfo(get_system_timezone())
	try:
		if str(value).replace(".", "", 1).isdigit():
			ts = float(value)
			if ts > 1e12:
				ts /= 1000
			return datetime.fromtimestamp(ts, tz=tz).replace(tzinfo=None)
		dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
		return dt.astimezone(tz).replace(tzinfo=None) if dt.tzinfo else dt
	except ValueError:
		return now_datetime()


def sync_vehicle_gps(doc, method=None):
	"""hooks.py -> Vehicle on_update: IMEI yozilgan / o'zgargan texnikaning GPS nuqtalariga mashina raqami,
	turi va firmasi qo'yiladi (IMEI Vehicle ga keyinroq yozilgan bo'lsa ham)."""
	if not doc.get("gps_imei"):
		return
	frappe.db.sql(
		"""update `tabGPS Malumot` set vehicle=%s, texnika_turi=%s, company=%s where gps_imei=%s""",
		(doc.name, doc.get("texnika_turi"), doc.get("company"), doc.gps_imei),
	)


def cleanup_gps():
	"""hooks.py -> scheduler (har kuni): eski GPS nuqtalarni o'chiradi (Karer Sozlamalari -> necha kun saqlansin)."""
	days = cint(frappe.db.get_single_value("Karer Sozlamalari", "gps_saqlash_kun")) or 90
	frappe.db.delete("GPS Malumot", {"vaqt": ("<", add_days(now_datetime(), -days))})
