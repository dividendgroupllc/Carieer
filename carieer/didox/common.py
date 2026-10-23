# Didox ma'lumotnomalari: hujjat turlari va holat kodlari (API hujjatidagi «Статусы документов»).

HUJJAT_TURLARI = {
	"002": "Hisob-faktura",
	"008": "Hisob-faktura (farm)",
	"023": "Gibrid hisob-faktura",
	"041": "TTN",
	"005": "Bajarilgan ishlar akti",
	"006": "Ishonchnoma",
	"062": "Ishonchnoma",
	"007": "Shartnoma",
	"000": "Erkin hujjat",
	"010": "Ko'p tomonlama hujjat",
	"052": "Akt sverka",
	"054": "Qabul-topshirish akti",
	"075": "Ta'sischilar yig'ilishi bayonnomasi",
	"031": "Soliq xati",
}

HOLATLAR = {
	0: "Qoralama",
	1: "Kontragent imzosini kutmoqda",
	2: "Bizning imzoni kutmoqda",
	3: "Imzolangan",
	4: "Rad etilgan",
	5: "O'chirilgan",
	6: "Agent imzosini kutmoqda",
	8: "Agent imzolagan",
	40: "Yaroqsiz",
	50: "Soliq bekor qilgan",
	55: "Qoralama o'chirilgan",
	60: "Agent imzosini kutmoqda",
}


def hujjat_turi(kod: str | None) -> str:
	return HUJJAT_TURLARI.get(kod or "", kod or "")


def holat(kod) -> str:
	try:
		kod = int(kod)
	except (TypeError, ValueError):
		return "Noma'lum"
	return HOLATLAR.get(kod, "Boshqa")
