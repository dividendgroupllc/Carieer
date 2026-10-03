"""Tashqi tizimlar uchun API (GPS provayder, Traccar Client) va texnikalar xaritasi."""

import hashlib
import hmac
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, get_system_timezone, getdate, now_datetime

# Realtime hodisa nomi: yangi GPS nuqta kelganda xarita sahifasiga yuboriladi
GPS_EVENT = "karer_gps"
# Shundan eski GPS Malumot yozuvlari har kuni o'chiriladi (jadval cheksiz o'smasin)
GPS_SAQLASH_KUN = 90
XARITA_ROLLARI = ("System Manager", "Karer Menejer", "Karer Operator", "Beton Menejer", "Beton Operator")


def check_token(token: str | None):
	from frappe.utils.password import get_decrypted_password

	expected = get_decrypted_password("Karer Sozlamalari", "Karer Sozlamalari", "gps_token", raise_exception=False)
	if not expected or not token or not hmac.compare_digest(str(token), expected):
		frappe.throw(_("Noto'g'ri token"), frappe.AuthenticationError)


def save_point(imei: str, **values) -> dict | None:
	"""Bitta GPS nuqtani saqlaydi va xaritaga realtime xabar yuboradi.
	Aynan shu nuqta (vaqt + koordinata) oldin saqlangan bo'lsa None qaytaradi: telefon yangi joylashuvni
	aniqlay olmasa, "heartbeat"da oxirgi eski nuqtani qayta-qayta yuboradi."""
	vehicle = frappe.db.get_value("Vehicle", {"gps_imei": imei}, "name")
	doc = frappe.get_doc({"doctype": "GPS Malumot", "vehicle": vehicle, "gps_imei": imei, **values})
	doc.vaqt = get_datetime(doc.vaqt or now_datetime()).replace(microsecond=0)
	# Traccar bir nuqtani bir vaqtda parallel bir necha marta yuboradi, shunda "exists" tekshiruvi hammasiga
	# "yo'q" deydi. Takrorni bazadagi unique `nuqta_kalit` ishonchli to'xtatadi. (Nomni kalit qilish
	# ishlamaydi: autoname=hash da Frappe PK to'qnashuvida yangi tasodifiy nom bilan qayta yozadi.)
	key = f"{imei}|{doc.vaqt}|{flt(doc.lat, 7)}|{flt(doc.lon, 7)}"
	doc.nuqta_kalit = hashlib.sha1(key.encode()).hexdigest()
	if frappe.db.exists("GPS Malumot", {"nuqta_kalit": doc.nuqta_kalit}):
		return None
	try:
		doc.insert(ignore_permissions=True)
	except frappe.UniqueValidationError:
		frappe.clear_messages()
		return None
	point = point_dict(doc)
	frappe.publish_realtime(GPS_EVENT, point, after_commit=True)
	return point


def point_dict(d) -> dict:
	return {
		"gps_imei": d.gps_imei,
		"vehicle": d.vehicle,
		"vaqt": str(d.vaqt),
		"lat": flt(d.lat),
		"lon": flt(d.lon),
		"tezlik": flt(d.tezlik),
		"yonalish": flt(d.get("yonalish")),
		"batareya": d.get("batareya"),
		"yoqilgi_darajasi": d.get("yoqilgi_darajasi"),
		"qurilma": d.get("qurilma"),
	}


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
			lat=d.get("lat"),
			lon=d.get("lon"),
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
	points = parse_traccar_json(body) if isinstance(body, dict) and body.get("location") else parse_traccar_query(form)

	qurilma = traccar_source()
	saved = skipped = 0
	for imei, values in points:
		if not imei or values.get("lat") is None or values.get("lon") is None:
			continue
		if save_point(imei, qurilma=qurilma, **values):
			saved += 1
		else:
			skipped += 1
	if not saved and not skipped:
		frappe.log_error(title="Traccar: nuqta topilmadi", message=frappe.as_json({"form": form, "body": body}))
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
					"lat": c.get("latitude"),
					"lon": c.get("longitude"),
					"tezlik": round(speed * 3.6, 1) if speed > 0 else 0,
					"yonalish": c.get("heading") if flt(c.get("heading")) >= 0 else None,
					"batareya": round(flt(battery.get("level")) * 100) if battery.get("level") is not None else None,
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
				"lat": flt(lat) if lat not in (None, "") else None,
				"lon": flt(lon) if lon not in (None, "") else None,
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


# ------------------------------------------------------------------ Xarita sahifasi (texnika-xarita)
def allowed_imeis() -> set[str] | None:
	"""Firmaga bog'langan xodim faqat o'z firmasi texnikalarini ko'radi. None = cheklov yo'q (admin)."""
	from carieer.utils import get_allowed_companies

	companies = get_allowed_companies()
	if not companies:
		return None
	return set(
		frappe.get_all(
			"Vehicle", filters={"company": ["in", companies], "gps_imei": ["is", "set"]}, pluck="gps_imei"
		)
	)


@frappe.whitelist()
def get_live_positions(days: int = 7) -> list[dict]:
	"""Har bir GPS qurilmaning oxirgi nuqtasi + GPS IMEI yozilgan, lekin hali ma'lumot kelmagan texnikalar."""
	frappe.only_for(XARITA_ROLLARI)
	since = add_days(now_datetime(), -int(days))
	rows = frappe.db.sql(
		"""select g.gps_imei, g.vehicle, g.vaqt, g.lat, g.lon, g.tezlik, g.yonalish, g.batareya, g.yoqilgi_darajasi,
			g.qurilma
		from `tabGPS Malumot` g
		join (select gps_imei, max(vaqt) vaqt from `tabGPS Malumot` where vaqt >= %s group by gps_imei) m
			on m.gps_imei = g.gps_imei and m.vaqt = g.vaqt""",
		since,
		as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.gps_imei, point_dict(r))

	vehicles = {
		v.gps_imei: v
		for v in frappe.get_all(
			"Vehicle", filters={"gps_imei": ["is", "set"]}, fields=["name", "gps_imei", "texnika_turi", "make", "model"]
		)
	}
	for imei, v in vehicles.items():
		p = out.setdefault(imei, {"gps_imei": imei, "vehicle": v.name, "vaqt": None})
		p["vehicle"] = v.name  # IMEI keyinroq Vehicle ga yozilgan bo'lsa ham to'g'ri nom chiqsin
		p["texnika_turi"] = v.texnika_turi
		p["model"] = " ".join(filter(None, (v.make, v.model)))
	allowed = allowed_imeis()
	if allowed is not None:
		out = {imei: p for imei, p in out.items() if imei in allowed}
	return sorted(out.values(), key=lambda p: (p.get("vehicle") or p["gps_imei"]))


@frappe.whitelist()
def get_track(gps_imei: str, date: str) -> list[dict]:
	"""Bitta qurilmaning tanlangan kundagi yurgan yo'li."""
	frappe.only_for(XARITA_ROLLARI)
	allowed = allowed_imeis()
	if allowed is not None and gps_imei not in allowed:
		frappe.throw(_("Bu texnikani ko'rishga ruxsatingiz yo'q"), frappe.PermissionError)
	day = getdate(date)
	return frappe.db.sql(
		"""select vaqt, lat, lon, tezlik from `tabGPS Malumot`
		where gps_imei = %s and vaqt >= %s and vaqt < %s
		order by vaqt""",
		(gps_imei, day, add_days(day, 1)),
		as_dict=True,
	)


def sync_vehicle_gps(doc, method=None):
	"""hooks.py -> Vehicle on_update: IMEI yozilgan/o'zgargan texnikaning barcha GPS nuqtalariga
	mashina raqami, turi, markasi va modeli qo'yiladi (IMEI Vehicle ga keyinroq yozilgan bo'lsa ham)."""
	if not doc.get("gps_imei"):
		return
	frappe.db.sql(
		"""update `tabGPS Malumot` set vehicle=%s, texnika_turi=%s, marka=%s, model=%s where gps_imei=%s""",
		(doc.name, doc.get("texnika_turi"), doc.get("make"), doc.get("model"), doc.gps_imei),
	)


@frappe.whitelist(methods=["POST"])
def delete_gps_points(gps_imei: str | None = None, to_date: str | None = None) -> int:
	"""GPS Malumot ro'yxatidagi "Tozalash" tugmasi: nuqtalarni bitta SQL bilan tez o'chiradi
	(standart bulk delete minglab nuqtani bittalab, fonda o'chiradi va juda sekin)."""
	frappe.only_for(("System Manager", "Karer Menejer", "Beton Menejer"))
	filters = {}
	if gps_imei:
		filters["gps_imei"] = gps_imei
	if to_date:
		filters["vaqt"] = ("<", add_days(getdate(to_date), 1))
	count = frappe.db.count("GPS Malumot", filters)
	frappe.db.delete("GPS Malumot", filters)
	return count


def cleanup_gps():
	"""hooks.py -> scheduler (har kuni): eski GPS nuqtalarni o'chiradi."""
	frappe.db.delete("GPS Malumot", {"vaqt": ("<", add_days(now_datetime(), -GPS_SAQLASH_KUN))})
