# Didox API (elektron hujjat almashish operatori) bilan aloqa.
# Har bir so'rovda ikki sarlavha: Partner-Authorization (Orange'ning partner tokeni, bitta)
# va user-key (firma tokeni, 6 soat amal qiladi). Firma tokeni parol bilan (server o'zi)
# yoki ERI bilan (brauzerda E-IMZO, carieer.didox.api.eri_login) olinadi va keshda turadi.
# Didox so'rovlarni faqat arizadagi IP'dan (server) qabul qiladi.

import frappe
import requests
from frappe import _

URLS = {
	"Test": "https://testapi3.didox.uz",
	"Prod": "https://api-partners.didox.uz",
}
TOKEN_TTL = 350 * 60  # Didox 360 daqiqa beradi, 10 daqiqa zaxira
TIMEOUT = 30


class DidoxError(frappe.ValidationError):
	pass


def token_key(company: str) -> str:
	return f"didox_token:{company}"


def get_settings():
	settings = frappe.get_cached_doc("Didox Sozlamalari")
	if not settings.yoqilgan:
		frappe.throw(_("Didox o'chiq: Didox Sozlamalari'da yoqing"), DidoxError)
	if not settings.get_password("partner_token", raise_exception=False):
		frappe.throw(_("Didox Sozlamalari'da partner token kiritilmagan"), DidoxError)
	return settings


def get_firma(company: str):
	for row in get_settings().firmalar:
		if row.company == company:
			return row
	frappe.throw(_("{0} firmasi Didox Sozlamalari'da yo'q").format(company), DidoxError)


class DidoxClient:
	def __init__(self, company: str | None = None):
		self.settings = get_settings()
		self.base = URLS[self.settings.rejim or "Test"]
		self.locale = self.settings.til or "ru"
		self.partner_token = self.settings.get_password("partner_token")
		self.company = company
		self.firma = get_firma(company) if company else None

	# ------------------------------------------------------------------ token
	def user_token(self) -> str:
		token = frappe.cache.get_value(token_key(self.company))
		if token:
			return token
		if self.firma.get_password("parol", raise_exception=False):
			return self.login_password()
		frappe.throw(
			_("{0}: Didox'ga kirilmagan. ERI kaliti bilan kiring (Didox Hujjat → «ERI bilan kirish»)").format(
				self.company
			),
			DidoxError,
		)

	def save_token(self, token: str) -> str:
		frappe.cache.set_value(token_key(self.company), token, expires_in_sec=TOKEN_TTL)
		return token

	def login_password(self) -> str:
		# Diqqat: Didox noto'g'ri parolni bloklaydi (3 ta xato -> 10 daqiqa, 25 ta -> butunlay).
		# Shuning uchun xato bo'lsa qayta urinmaymiz.
		data = self.post(
			f"/v1/auth/{self.firma.inn}/password/{self.locale}",
			{"password": self.firma.get_password("parol")},
			auth=False,
		)
		return self.save_token(data["token"])

	def login_signature(self, signature: str) -> str:
		data = self.post(
			f"/v1/auth/{self.firma.inn}/token/{self.locale}", {"signature": signature}, auth=False
		)
		return self.save_token(data["token"])

	# ------------------------------------------------------------------ so'rovlar
	def headers(self, auth: bool) -> dict:
		h = {"Partner-Authorization": self.partner_token, "Accept-Language": self.locale}
		if auth:
			h["user-key"] = self.user_token()
		return h

	def request(self, method: str, path: str, auth: bool = True, raw: bool = False, **kwargs):
		try:
			r = requests.request(
				method, self.base + path, headers=self.headers(auth), timeout=TIMEOUT, **kwargs
			)
		except requests.RequestException as e:
			frappe.throw(_("Didox bilan aloqa yo'q: {0}").format(e), DidoxError)

		if r.status_code == 401 and auth:
			# token muddati tugagan: keyingi so'rov qayta kiradi
			frappe.cache.delete_value(token_key(self.company))
		if not r.ok:
			frappe.throw(_("Didox xatosi ({0}): {1}").format(r.status_code, error_text(r)), DidoxError)
		return r if raw else r.json()

	def get(self, path: str, params: dict | None = None, **kwargs):
		return self.request("GET", path, params=params, **kwargs)

	def post(self, path: str, data: dict | None = None, **kwargs):
		return self.request("POST", path, json=data or {}, **kwargs)

	# ------------------------------------------------------------------ hujjatlar
	def org_info(self, inn: str, date: str | None = None, seller: bool = False) -> dict:
		params = {"isSeller": "true" if seller else "false"}
		if date:
			params["document_date"] = str(date)
		return self.get(f"/v1/utils/info/{inn}", params)

	def create(self, doctype_kod: str, doc_json: dict) -> dict:
		return self.post(f"/v1/documents/{doctype_kod}/create/{self.locale}", doc_json)

	def document(self, didox_id: str, owner: int = 1) -> dict:
		return self.get(f"/v1/documents/{didox_id}", {"owner": owner})["data"]

	def documents(self, page: int = 1, limit: int = 100, **filters) -> dict:
		return self.get("/v2/documents", {"page": page, "limit": limit, **filters})

	def timestamp(self, pkcs7: str, signature_hex: str) -> str:
		data = self.post("/v1/dsvs/timestamp", {"pkcs7": pkcs7, "signatureHex": signature_hex}, auth=False)
		return data["timeStampTokenB64"]

	def sign(self, didox_id: str, signature: str) -> dict:
		return self.post(f"/v1/documents/{didox_id}/sign", {"signature": signature})

	def delete_draft(self, didox_id: str):
		return self.post(f"/v1/documents/{didox_id}/delete/draft")

	def pdf(self, didox_id: str) -> bytes:
		return self.get(f"/v1/documents/view/{didox_id}/pdf/{self.locale}", raw=True).content


def error_text(r) -> str:
	try:
		body = r.json()
	except ValueError:
		return r.text[:500]
	if isinstance(body, dict):
		details = body.get("errorDetails") or {}
		inner = body.get("data") if isinstance(body.get("data"), dict) else body
		msg = details.get("description") or inner.get("message") or body.get("message")
		if msg:
			return str(msg)
	return str(body)[:500]
