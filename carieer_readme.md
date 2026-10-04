# Carieer: Karer, beton, texnika va GPS (ERPNext ustida)

Bu hujjat `carieer` ilovasini **0 dan** ishga tushirish, sozlash va har kuni ishlatish bo'yicha to'liq qo'llanma.
Ketma-ketlik bilan o'qing: avval tushunchalar, keyin sozlash, keyin kundalik ish, oxirida hisobotlar va texnik qism.

---

## Mundarija
1. [Umumiy tushuncha](#1-umumiy-tushuncha)
2. [ERPNext asoslari (ombor, buxgalteriya)](#2-erpnext-asoslari)
3. [O'rnatish](#3-ornatish)
4. [0 dan sozlash: ketma-ketlik](#4-0-dan-sozlash-ketma-ketlik)
5. [Kundalik ish: hujjatlar](#5-kundalik-ish-hujjatlar)
6. [Beton: BOM va ishlab chiqarish](#6-beton-bom-va-ishlab-chiqarish)
7. [GPS: texnikalarni onlayn kuzatish](#7-gps-texnikalarni-onlayn-kuzatish)
8. [Hisobotlar](#8-hisobotlar)
9. [Rollar va ruxsatlar](#9-rollar-va-ruxsatlar)
10. [Kod tuzilishi (dasturchi uchun)](#10-kod-tuzilishi-dasturchi-uchun)
11. [Serverga chiqarish (production)](#11-serverga-chiqarish-production)
12. [Tez-tez uchraydigan xatolar](#12-tez-tez-uchraydigan-xatolar)

---

## 1. Umumiy tushuncha

| Qatlam | Nima |
|---|---|
| **Frappe** | Python framework (Django o'rniga). DocType, forma, API, ruxsatlar |
| **ERPNext** | Frappe ustidagi tayyor ERP: ombor, buxgalteriya, sotuv, xarid, ishlab chiqarish |
| **carieer** | Bizning ilova: karer biznesi uchun soddalashtirilgan formalar + hisobotlar + GPS |

**Asosiy g'oya:** foydalanuvchi faqat bizning oddiy formalarni to'ldiradi (Sotuv, Qazib Olish, ...).
Murakkab ERPNext hujjatlari (Sales Invoice, Stock Entry, Payment Entry, GL Entry) **avtomatik** yaratiladi.
Shuning uchun omborchi va buxgalter bir xil to'g'ri raqamlarni ko'radi.

### Biznes jarayoni (rasm o'rnida)
```
 Qazib Olish ──▶ Karer ombori (qum, shag'al, tan narx 0)
                     │
                     ├──▶ Sotuv ──▶ mijozga sotildi (Sales Invoice + to'lov + SMS)
                     │
                     └──▶ (ko'chirish) ──▶ Beton xomashyo ombori ◀── Xarid (sement, ximikat)
                                                   │
                                     Beton Ishlab Chiqarish (BOM bo'yicha)
                                                   │
                                                   ▼
                                           Beton ombori ──▶ Sotuv (beton sotish)

 Yoqilg'i ombori ──▶ Yoqilg'i Hisobi ──▶ texnikaga sarf (km, 100 km ga litr)
 Telefon (Traccar Client) ──▶ GPS Malumot ──▶ Texnikalar xaritasi (onlayn)
 Firma A ◀──▶ Firma B : Firmalararo Sotuv
```

---

## 2. ERPNext asoslari

### 2.1 Hujjat hayot sikli (`docstatus`)
```
0 = Draft (qoralama)  ──Submit──▶  1 = Submitted  ──Cancel──▶  2 = Cancelled  ──Amend──▶ yangi nusxa
   o'zgartirsa bo'ladi              o'zgarmaydi!                  tarixda qoladi
```
Ombor va buxgalteriyaga ta'sir **faqat Submit** paytida bo'ladi. Cancel qilinsa, teskari yozuvlar qo'shiladi (hech narsa o'chirilmaydi).

### 2.2 Ombor
| Tushuncha | Ma'nosi |
|---|---|
| **Item** | Tovar: Qum, Shag'al, Sement, Ximikat, Beton, Dizel |
| **Warehouse** | Ombor: Karer ombori, Beton xomashyo, Beton ombori, Yoqilgi ombori |
| **UOM** | O'lchov birligi. Ombor birligi Kg, sotuv birligi Tonne (1 Tonne = 1000 Kg) |
| **Stock Entry** | Ombor harakati hujjati (pastdagi jadval) |
| **Stock Ledger Entry (SLE)** | Ombor daftari: har harakat bitta qator (+kirim / −chiqim) |
| **Bin** | "Tovar + ombor" bo'yicha joriy qoldiq |
| **Valuation Rate** | Tan narx: kirim narxlaridan o'rtacha hisoblanadi |

| Stock Entry turi | Nima qiladi | Bizda kim yaratadi |
|---|---|---|
| Material Receipt | Kirim | **Qazib Olish** |
| Material Issue | Chiqim (sarf) | **Yoqilg'i Hisobi** (Ombordan) |
| Material Transfer | Ombordan omborga | Qo'lda (masalan, qumni Beton xomashyo omboriga) |
| Manufacture | Xomashyo chiqadi, tayyor mahsulot kiradi | **Beton Ishlab Chiqarish** |

### 2.3 Buxgalteriya
- **GL Entry**: buxgalteriya daftari, ikki tomonlama yozuv (Debet = Kredit).
- **Perpetual inventory** yoqilgan: har bir ombor harakati avtomatik buxgalteriyaga ham yoziladi.
- **Sales Invoice**: sotuv hisob-fakturasi. `update_stock=1` bo'lsa, tovarni ombordan ham chiqaradi.
- **Payment Entry**: to'lov (kassaga kirim, mijoz qarzi kamayadi).
- **Purchase Invoice**: xarid (sement, ximikat sotib olish).

---

## 3. O'rnatish

```bash
cd frappe-bench-v16
bench get-app <repo-url> --branch karer-sotuv      # yoki apps/carieer allaqachon bor bo'lsa shart emas
bench --site karer16.local install-app carieer
bench --site karer16.local migrate
bench start                                         # dev rejimda
```
`install-app` va har bir `migrate` dan keyin `carieer.install.after_migrate` avtomatik ishlaydi:
- rollar yaratiladi: **Karer Operator, Karer Kassir, Karer Menejer**
- **Vehicle** ga maydonlar qo'shiladi: *Texnika turi*, *GPS qurilma IMEI*
- rollar uchun kerakli ERPNext ruxsatlari beriladi
- Item formasidagi keraksiz maydonlar yashiriladi
- module profile yaratiladi

> ⚠️ Python kodi o'zgarganda `bench start` ni qayta ishga tushiring. JS o'zgarganda brauzerda **Ctrl+Shift+R** bosing.

---

## 4. 0 dan sozlash: ketma-ketlik

Quyidagi tartibda bajaring. Har bir qadam oldingisiga bog'liq.

### 4.1 Firma (Company)
**Qayerda:** Setup → Company → New
- Nomi, qisqartmasi (masalan `C`), valyuta **UZS**, hisoblar rejasi (Chart of Accounts).
- Bir nechta firma bo'lsa (masalan, karer firmasi `C` va beton zavodi `BZ`), har birini alohida yarating.

### 4.2 Firma uchun karer asoslari (bitta buyruq)
**Qayerda:** konsol (`bench --site karer16.local console`) yoki API:
```python
from carieer.install import setup_firma
setup_firma("Firma nomi")
```
Bu buyruq quyidagilarni yaratadi (qayta ishga tushirish xavfsiz):
- Omborlar: **Karer ombori**, **Beton xomashyo**, **Beton ombori**, **Yoqilgi ombori** (`- C` qo'shimchasi bilan)
- Kassa hisoblari: **Kassa UZS**, **Kassa USD**
- To'lov turlari: **Naqd UZS**, **Naqd USD**, **Plastik**, **Bank o'tkazma**
- UOM: Tonne, Kg, Litre, Cubic Meter
- **Karer Sozlamalari** da shu firma qatori (omborlar va kassa bilan)

### 4.3 Karer Sozlamalari
**Qayerda:** Karer → Karer Sozlamalari (bitta nusxali "Single" hujjat)

| Bo'lim | Maydon | Nima uchun |
|---|---|---|
| Firmalar | Sotuv (karer) ombori | Sotuv'da standart ombor |
| | Qazib olingan tovar ombori | Qazib Olish kirim qiladigan ombor |
| | Beton xomashyo ombori | Beton ishlab chiqarishda xomashyo shu yerdan olinadi |
| | Tayyor beton ombori | Ishlab chiqarilgan beton shu yerga kiradi |
| | Yoqilg'i / moy ombori | Yoqilg'i Hisobi (Ombordan) shu yerdan chiqaradi |
| | Asosiy to'lov turi | Sotuv'da standart kassa |
| | Firmalararo narx varaqasi | Firmalararo Sotuv uchun narxlar (Price List) |
| SMS | SMS yuborish, provayder | **Frappe SMS Settings** yoki **Eskiz.uz** |
| | SMS shablon | Masalan: `{customer}: {item} {qty} {uom} = {amount} {currency}` |
| | Eskiz email / parol / from | Eskiz.uz akkaunti ma'lumotlari |
| GPS | GPS API token | Telefon va GPS qurilmalar shu parol bilan ma'lumot yuboradi |

### 4.4 Tovarlar (Item)
**Qayerda:** Stock → Item → New, yoki konsolda:
```python
from carieer.install import setup_tovar
setup_tovar("Qum")                          # Kg da saqlanadi, Tonne da sotiladi (1 Tonne = 1000 Kg)
setup_tovar("Shagal")
setup_tovar("Sement", is_sales_item=False)  # faqat xomashyo
setup_tovar("Ximikat", is_sales_item=False)
setup_tovar("Beton")
setup_tovar("Dizel", stock_uom="Litre", tonne=False)
```
Qo'lda yaratsangiz, **Maintain Stock** ✅ bo'lishi va **UOM Conversion** jadvalida `Tonne = 1000` bo'lishi shart.

### 4.5 Mijozlar, yetkazib beruvchilar, xodimlar
- **Customer** (Selling → Customer): mijozlar. Telefon raqami SMS uchun.
- **Supplier** (Buying → Supplier): sement va ximikat yetkazib beruvchilar, zapravkalar.
- **Employee** (HR → Employee): haydovchilar (Yoqilg'i Hisobi uchun).

### 4.6 Texnikalar (Vehicle)
**Qayerda:** Karer → Vehicle → New (yoki HR → Vehicle)
- **License Plate**: davlat raqami (masalan `01A123BC`)
- **Make / Model**: marka, model
- **Odometer**: hozirgi spidometr (0 bo'lsa ham yozing)
- **Fuel UOM**: `Litre`
- **Texnika turi**: Samosval, Betonovoz, Ekskavator, ...
- **GPS qurilma IMEI**: telefondagi Traccar "Device identifier" yoki GPS trekker IMEI (7-bo'lim)

### 4.7 Boshlang'ich qoldiqlar
Tizimga o'tish kuni omborda allaqachon tovar bo'lsa:
**Stock → Stock Reconciliation → New** → tovar, ombor, miqdor, tan narx → Submit.

### 4.8 Xomashyo xaridi
Sement va ximikat: **Buying → Purchase Invoice** (`Update Stock` ✅, ombor = **Beton xomashyo**).
Shu hujjatdagi narx keyin betonning tan narxiga kiradi.

### 4.9 BOM (beton retsepti)
6-bo'limga qarang. Bir marta yaratiladi, keyin faqat tanlanadi.

---

## 5. Kundalik ish: hujjatlar

Barchasi **Karer** bo'limida (`/desk/karer`).

### 5.1 Qazib Olish
**Vazifasi:** karerdan qazib olingan qum/shag'alni omborga kirim qilish.

| Maydon | Nima yoziladi |
|---|---|
| Firma, Ombor | Karer ombori |
| Sana, vaqt | Qazish vaqti |
| Texnika | Qaysi ekskavator/mashina (ixtiyoriy) |
| Tovarlar jadvali | Tovar + miqdor (Kg). Masalan 20 t qum = `20000` |

**Submit** → `Stock Entry (Material Receipt)`, **tan narx 0** (o'zimiz qazdik, sotib olmadik).
Cancel → Stock Entry ham bekor qilinadi.

### 5.2 Sotuv (sotuv posti, AppSheet "Ввод продажи")
**Vazifasi:** postda mijozga sotish. Bitta post ikkala zavodga xizmat qiladi: **Тип = Karer** bo'lsa
Karer firmasi nomidan, **Тип = Beton** bo'lsa Beton Zavod nomidan sotiladi (firmalar: Karer Sozlamalari ->
Sotuv posti). Karer xodimi faqat Karer, beton xodimi faqat Beton tipini ko'radi.

| Qism | Izoh |
|---|---|
| Дата, Тип, Валюта, Доставка | Valyuta UZS yoki USD, kurs Currency Exchange dan |
| Клиент, Номер машины | Mijoz va mashina raqami |
| Товары | Tovar, miqdor, narx -> summa. Ombor **o'zi qo'yiladi** |
| Услуги | Погрузчик, Доставка kabi xizmatlar (ombor tovari emas) |
| Оплаты | Kassa (to'lov turi), valyuta, kurs, kim to'ladi, izoh |
| Итог / Услуг / Общий / Долг | Avtomatik hisoblanadi |

**Завершить (Submit)** -> **Sales Invoice** (tovar ombordan chiqadi, mijozga qarz) + har bir to'lov qatori uchun
**Payment Entry** (kassaga kirim). Keyin **Оплата** tugmasi bilan qolgan qarz to'lanadi (boshqa valyutada ham).

**Misol:** Qum 9 t × 100 000 + Shagal 5 t × 120 000 + Погрузчик 50 000 = 1 550 000; 500 000 naqd -> Долг 1 050 000;
keyin 87.5 $ × 12 000 -> To'langan.

### 5.3 Beton Ishlab Chiqarish
6.2 ga qarang.

### 5.4 Yoqilg'i Hisobi
**Vazifasi:** qaysi texnikaga qancha yoqilg'i yoki moy ketganini hisoblash.

| Maydon | Izoh |
|---|---|
| Texnika | Vehicle. Texnika turi o'zi chiqadi |
| Haydovchi | Employee |
| Turi | Dizel, Benzin, Gaz, Motor moyi, Gidravlik moy, Boshqa |
| Qayerdan | **Ombordan**: o'z omborimizdan. **Zapravkadan**: tashqaridan sotib olindi |
| Tovar, Ombor | Ombordan bo'lsa (Yoqilgi ombori) |
| Zapravka | Zapravkadan bo'lsa (Supplier) |
| Miqdor (litr), 1 litr narxi | Summa hisoblanadi. Ombordan bo'lsa narx = tan narx |
| Spidometr (km) | Hozirgi ko'rsatkich. **Oldingi spidometr** va **yurgan km** o'zi topiladi |
| Motor soat | Ekskavator kabi texnikalar uchun (km o'rniga) |

**Submit** → *Ombordan* bo'lsa `Stock Entry (Material Issue)`: yoqilg'i ombordan chiqadi.
**Sarf (litr / 100 km)** avtomatik hisoblanadi. Birinchi yozuvda oldingi ko'rsatkich sifatida Vehicle'dagi Odometer olinadi.

### 5.5 Firmalararo Sotuv
**Vazifasi:** ikki firmamiz o'rtasida oldi-sotdi (masalan, Beton Zavod karerdan qum/shag'al oladi).
Hujjat **ikkala firmaga ham ko'rinadi** (sotuvchi ham, xaridor ham). Firma xodimi yaratganda xaridor = o'z firmasi.

| Maydon | Izoh |
|---|---|
| Sotuvchi firma, chiqish ombori | Tovar shu yerdan chiqadi (ombor o'zi qo'yiladi) |
| Xaridor firma, kirish ombori | Tovar shu yerga kiradi (beton zavodda -> Beton xomashyo) |
| Tovarlar jadvali | Tovar, miqdor, narx |

**Submit** -> sotuvchida **Sales Invoice** (ichki mijozga), xaridorda **Purchase Invoice** (ichki yetkazib beruvchidan).
Ichki mijoz/yetkazib beruvchi kerak bo'lsa o'zi yaratiladi. **Draft holatda qarz ham, tovar ham yozilmaydi!**

### 5.5.1 Firmalararo To'lov
Bir firma ikkinchisiga qarzini to'laydi: to'lovchi firma + kassa, oluvchi firma + kassa, summa. Formada joriy qarz ko'rinadi.
**Submit** -> to'lovchida Payment Entry (Pay), oluvchida Payment Entry (Receive). To'lov eng eski to'lanmagan
firmalararo hisob-fakturalarga taqsimlanadi.

### 5.5.2 Firmalararo Qarzlar (hisobot)
Har bir firma o'z kitobini ko'radi: **"Beton Zavod bizdan X qarz"** yoki **"Biz Carieerdan X qarzmiz"**, ostida
batafsil: sana, hujjat, nima olingan (tovar × narx), to'lovlar, qoldiq. Ikkala firma kitobi mos kelmasa yoki
tasdiqlanmagan (Draft) hujjat bo'lsa ogohlantiradi.

### 5.6 GPS Malumot
Qo'lda kiritilmaydi, telefon yoki trekker **o'zi yuboradi** (7-bo'lim). Ro'yxatda har bir nuqta ko'rinadi:
vaqt, koordinata, tezlik, yo'nalish, batareya.

---

## 6. Beton: BOM va ishlab chiqarish

### 6.1 BOM (Bill of Materials): retsept
**BOM** = "1 tonna beton uchun qaysi xomashyodan qancha kerak". BOM **omborda hech narsani o'zgartirmaydi**, faqat retsept.

**Qayerda:** Manufacturing → BOM → New

| Maydon | Qiymat |
|---|---|
| Item | `Beton` (har bir marka uchun alohida item: `Beton M300`, `Beton M400`) |
| Company | Beton ishlab chiqaradigan firma |
| Quantity | `1`, UOM `Tonne` |
| Rate Of Materials Based On (Costing tab) | **Valuation Rate** |
| Components (Items) | Pastdagi jadval |

Hozirgi `BOM-Beton-001` (1 tonna uchun):

| Xomashyo | Qty | Narx qayerdan | Summa |
|---|---|---|---|
| Shag'al | 450 kg | Qazib olingan → 0 | 0 |
| Qum | 400 kg | Qazib olingan → 0 | 0 |
| Sement | 130 kg | Purchase Invoice → 1 200 so'm/kg | 156 000 |
| Ximikat | 2 kg | Purchase Invoice → 15 000 so'm/kg | 30 000 |
| **Jami** | | | **≈ 186 000 so'm/t** |

**Save → Submit.** Faqat submit qilingan va **Is Active** bo'lgan BOM ishlatiladi. Asosiysi **Is Default** bo'lsin.
Retsept o'zgarsa, eski BOM'ni o'zgartirmang: **Copy** qilib yangisini submit qiling, eskisini *Is Active* dan chiqaring.

> BOM'dagi narxlar **taxminiy**. Haqiqiy tan narx ishlab chiqarish kuni ombordagi narxlar bo'yicha hisoblanadi.
> Narxni BOM'da qo'lda yozmang, u xarid hujjatlaridan olinadi.

### 6.2 Beton Ishlab Chiqarish (haqiqiy ishlab chiqarish)
**Qayerda:** Karer → Beton Ishlab Chiqarish → New

1. **Firma**, **Sana**
2. **BOM** tanlanadi. Item va birlik o'zi chiqadi
3. **Miqdor**: necha tonna (masalan `10`)
4. **Xomashyo ombori** (Beton xomashyo), **Tayyor mahsulot ombori** (Beton ombori)
5. **Save** → **Xomashyolar** jadvali o'zi to'ladi: *kerak* va *omborda bor* (faqat o'qish uchun, o'zgartirilmaydi)
6. **Submit**:
   - xomashyo yetmasa: xato, "Xomashyo yetarli emas: Sement kerak 1300, bor 500"
   - yetsa: **Stock Entry (Manufacture)** yaratiladi

```
10 t beton:
  Beton xomashyo → chiqim: Shag'al −4500 kg, Qum −4000 kg, Sement −1300 kg, Ximikat −20 kg
  Beton ombori   → kirim:  Beton +10 t
  Jami xarajat: 1 860 000 so'm | 1 t tan narxi: 186 000 so'm
```
Beton sotilganda foyda = sotuv narxi − 186 000.

### 6.3 Qum va shag'alni Beton xomashyo omboriga o'tkazish
Qazib olingan tovar **Karer ombori**da turadi. Betonga ishlatishdan oldin:
**Stock → Stock Entry → New → Material Transfer** → From: Karer ombori, To: Beton xomashyo → Submit.

### 6.4 Nega Manufacturing dashboard bo'sh?
U grafiklar faqat **Work Order / Job Card** ni sanaydi. Bizda ishlab chiqarish to'g'ridan-to'g'ri
Stock Entry (Manufacture) orqali, shuning uchun u yerda 0 ko'rinadi. **Bu xato emas.**
Ishlab chiqarishni ko'rish uchun: *Beton Ishlab Chiqarish* ro'yxati, *Material Hisobot*, *Stock Ledger* (Item = Beton).

---

## 7. GPS: texnikalarni onlayn kuzatish

### 7.1 Qanday ishlaydi
```
Haydovchi telefoni (Traccar Client) ──internet──▶ /api/method/carieer.api.traccar?token=...
                                                          │
                                                   GPS Malumot (bazaga)
                                                          │ realtime (socket.io)
                                                          ▼
                                            Karer → Texnikalar xaritasi (onlayn)
```
- Haydovchiga **akkaunt shart emas**, faqat ilova va server URL.
- Internet yo'q bo'lsa, telefon nuqtalarni **o'zida saqlaydi** va internet kelganda hammasini yuboradi.
- Bir nuqta ikki marta kelsa, bitta saqlanadi (`nuqta_kalit` unique).
- 90 kundan eski nuqtalar har kuni avtomatik o'chiriladi (`cleanup_gps`).

### 7.2 Serverda sozlash
1. **Karer Sozlamalari → GPS API token**: uzun tasodifiy parol yozing (masalan 32 belgi).
2. **Vehicle → GPS qurilma IMEI**: telefondagi *Device identifier* bilan bir xil raqam.

### 7.3 Telefonda sozlash (Traccar Client, Android/iOS, bepul)
| Sozlama | Qiymat |
|---|---|
| Device identifier | Masalan `43745749` (Vehicle'dagi GPS IMEI bilan bir xil) |
| Server URL | `https://<domen>/api/method/carieer.api.traccar?token=<GPS API token>` |
| Location accuracy | High |
| Frequency | 10–30 soniya |
| Distance | 10–20 m |
| Offline buffering | ✅ yoqilgan |

Telefonda: ilovaga **joylashuvga doimiy ruxsat** ("Allow all the time") bering va **batareya tejashdan** chiqaring.
Aks holda ekran o'chganda GPS to'xtaydi.

> Hozir (lokal) server tashqaridan Tailscale orqali ochiladi. Serverga + domenga chiqqanda Tailscale kerak emas:
> URL `https://domen/...` bo'ladi va barcha haydovchilar oddiy internet orqali yuboradi.

### 7.4 Xarita sahifasi
**Qayerda:** Karer → **Texnikalar xaritasi** (`/desk/texnika-xarita`)
- Chap ro'yxat: barcha texnikalar, oxirgi vaqt, tezlik, batareya. 🟢 onlayn / ⚪ eski
- Texnikani bosing → xaritada o'sha joy + **bugungi yurgan yo'li**
- Sana tanlab **boshqa kun yo'lini** ko'rish mumkin
- Signal uzilgan joylar (2 daqiqa yoki 300 m dan ko'p) **punktir** bilan, yo'l bo'ylab (OSRM) to'ldiriladi
- 🔵 **S**: kun boshlanish nuqtasi (vaqti doim yozilgan), 🔴 **F**: hozirgi joy yoki kun oxiri
- 🟠 **1, 2, 3…**: **to'xtashlar**, ya'ni mashina 60 m ichida **5 daqiqadan ko'p** turgan joylar.
  Chap panelda ro'yxati bor: qachondan qachongacha, qancha turdi, koordinatasi. Bosilsa, xaritada ochiladi
- Har bir joyda **latitude, longitude** ko'rsatiladi. Bosilsa, Google Maps'da ochiladi
- Panelda **turgan vaqti** va **harakatdagi vaqti** ko'rsatiladi
- Sozlash (`karer_xarita.js` boshida): `KX_STOP_MINUTES = 5`, `KX_STOP_METERS = 60`
- Yangi nuqta kelganda xarita **o'zi yangilanadi** (refresh shart emas)

### 7.5 Haqiqiy GPS trekker (ixtiyoriy)
Mashinaga o'rnatiladigan trekker yoki GPS provayder uchun alohida endpoint bor:
```
POST /api/method/carieer.api.gps_push
Header: X-Karer-Token: <GPS API token>
Body:   {"imei": "358...", "time": "2026-09-28 10:15:00", "lat": 41.3, "lon": 69.2,
         "speed": 34, "odometer": 125430.5, "fuel": 120.5, "engine_hours": 3500.2, "ignition": 1}
```
Odometer kelsa, Vehicle'dagi `last_odometer` ham yangilanadi.

---

## 8. Hisobotlar

Barchasi **Karer** bo'limida. Har birida tepada filtrlar bor, natijani Excel'ga yuklab olish mumkin (⋯ → Export).

### 8.1 Kontrol Hisobot
**Vazifasi:** karer sotuvlari va to'lov/qarz nazorati.
- **Filtrlar:** firma, sana oralig'i, mijoz, tovar, ombor, mashina raqami, valyuta, holat
- **Guruhlash:** Mijoz / Tovar / Kun / Mashina / Valyuta
- **Ko'rsatadi:** miqdor, summa, to'langan, qarz. Grafik va jami ko'rsatkichlar
- **Kimga:** menejer (kunlik sotuv), kassir (kim qarz)

### 8.2 Material Hisobot (материальный отчёт)
**Vazifasi:** har bir tovar va ombor bo'yicha harakat.
```
Boshlang'ich qoldiq
  + Qazib olindi + Ishlab chiqarildi + Xarid + Ko'chirib kelindi + Boshqa kirim
  − Sotildi − Ishlab chiqarishga − Boshqa omborga − Boshqa chiqim (texnika, spisaniye)
= Yakuniy qoldiq (va uning qiymati)
```
- **Filtrlar:** firma, sana, ombor, tovar, nol qoldiqlarni ko'rsatish
- **Kimga:** omborchi, menejer (qancha qazildi, qancha sotildi, qancha betonga ketdi)

### 8.3 DDS va Pul Oqimi (движение денежных средств)
**DDS:** kassa va bank hisoblaridagi har bir kirim/chiqim qatori (sana, kassa, kontragent, kategoriya, summa),
tepada boshlang'ich qoldiq → kategoriyalar → yakuniy qoldiq. Jadvaldagi «ДДС» varag'i.
**Pul Oqimi:** xuddi shu ma'lumot oyma-oy ustunlarda, xarajatlar jadvaldagi guruhlar bo'yicha. «Cash Flow» varag'i.
- **Filtrlar:** firma, sana, kassa (to'lov turi)
- **Kimga:** rahbar, buxgalter, kassir

### 8.4 Texnika Xarajatlari
**Vazifasi:** har bir texnika bo'yicha yoqilg'i va moy sarfi (Yoqilg'i Hisobi asosida).
- **Ko'rsatadi:** texnika, turi, model, yoqilg'i turi, litr, summa, yurgan km, motor soat,
  **100 km ga sarf**, **1 motor soatga sarf**
- **Filtrlar:** firma, sana, texnika
- **Kimga:** mexanik, rahbar (qaysi mashina ko'p yeyapti, yoqilg'i o'g'irlanmayaptimi)

### 8.5 ERPNext'ning foydali standart hisobotlari
| Hisobot | Qayerda | Nima uchun |
|---|---|---|
| Stock Balance | Stock → Reports | Omborlardagi qoldiq |
| Stock Ledger | Stock → Reports | Tovar harakatlari, qator-baqator |
| Accounts Receivable | Accounting → Reports | Mijozlar qarzi |
| General Ledger | Accounting → Reports | Buxgalteriya yozuvlari |
| Profit and Loss | Accounting → Reports | Foyda / zarar |
| Gross Profit | Accounting → Reports | Har bir sotuvdan foyda (sotuv narxi − tan narx) |

---

## 9. Rollar va ruxsatlar

| Rol | Kim | Nima qila oladi |
|---|---|---|
| **Karer Operator** | Tarozichi, post operatori | Sotuv, Qazib Olish, Yoqilg'i Hisobi; to'lov qabul qilish; xaritani ko'rish |
| **Karer Kassir** | Kassir | To'lovlar (Payment Entry), mijozlar, DDS hisobot |
| **Karer Menejer** | Menejer | Hammasi: sotuv, xarid, ishlab chiqarish, BOM, texnika, hisobotlar, xarita |
| **System Manager** | Admin | Sozlamalar, foydalanuvchilar |

Beton zavod xodimlari uchun xuddi shunday **Beton Operator / Beton Kassir / Beton Menejer** rollari bor.

### Kim qaysi bo'limni ko'radi
| Bo'lim | Kim ko'radi | Nima bor |
|---|---|---|
| **Karer** | karer xodimlari (operator, kassir, menejer) | dashboard, sotuv, qazib olish, ombor, texnika, hisobotlar |
| **Beton Zavod** | beton xodimlari | dashboard, ishlab chiqarish, retsept, sotuv, ombor, hisobotlar |
| **Sotuv operator** | post xodimi (ikkala firma nomidan sotadi) | sotuv, mijozlar, bugungi sotuv |
| **Kassa** | kassirlar | Kassa, Nachislenie, DDS, akt sverka, qarzlar |
| **Buxgalter oynasi** | menejer, kassir | Balans, P&L, Cash Flow, DDS, akt sverka, Prixod OS |
| **Texnika** | menejer, operator | xarita, yoqilg'i, texnikalar, GPS |

**Foydalanuvchi qo'shish** (rol + faqat o'z firmasi + standart bo'lim bitta buyruqda):
```bash
bench --site SITE execute carieer.install.setup_firma_user --kwargs "{'email': 'kassir@firma.uz', 'full_name': 'Ism Familiya', 'company': 'Carieer', 'role': 'Karer Kassir', 'password': '...'}"
# post xodimi (ikkala firma):
bench --site SITE execute carieer.install.setup_post_user --kwargs "{'email': 'post@firma.uz', 'full_name': 'Ism Familiya', 'password': '...'}"
```

---

## 10. Kod tuzilishi (dasturchi uchun)

```
apps/carieer/carieer/
├── hooks.py              ilova sozlamalari: after_migrate, doc_events (Payment Entry), scheduler (GPS tozalash)
├── install.py            rollar, Vehicle custom field'lar, ruxsatlar, setup_firma(), setup_tovar()
├── utils.py              umumiy: firma sozlamasi, valyuta kursi, SMS (Eskiz), get_item_warehouse()
├── api.py                GPS: traccar(), gps_push(), get_live_positions(), get_track(), cleanup_gps()
├── patches.txt           ma'lumot migratsiyalari
├── public/               logo va statik fayllar
├── workspace_sidebar/    Karer bo'limi menyusi
└── carieer/
    ├── doctype/
    │   ├── karer_sotuv/               + .json (maydonlar) .py (server) .js (forma)
    │   ├── qazib_olish/ + qazib_olish_tovar/            (child jadval)
    │   ├── beton_ishlab_chiqarish/ + beton_xomashyo/    (child jadval)
    │   ├── firmalararo_sotuv/ + firmalararo_sotuv_tovar/
    │   ├── yoqilgi_hisobi/
    │   ├── gps_malumot/
    │   └── karer_sozlamalari/ + karer_firma_sozlamasi/  (Single + child)
    ├── report/            kontrol_hisobot, material_hisobot, dds, pul_oqimi, balans, foyda_zarar, texnika_xarajatlari ...
    ├── page/karer_xarita/ Leaflet xarita sahifasi (realtime)
    └── workspace/karer/   Karer workspace (yorliqlar)
```

### Controller hodisalari (Django signals o'rniga)
| Metod | Qachon | Misol |
|---|---|---|
| `validate()` | Har Save | Sotuv: netto, summa; Beton: xomashyolar jadvali |
| `before_submit()` | Submit'dan oldin | Beton: xomashyo yetarlimi |
| `on_submit()` | Submit'dan keyin | Sales Invoice / Stock Entry / Payment Entry yaratish |
| `on_cancel()` | Cancel | Bog'langan hujjatlarni bekor qilish |

### Yangi maydon qo'shish
1. Developer mode: `bench --site karer16.local set-config developer_mode 1`
2. Desk → DocType → masalan *Qazib Olish* → maydon qo'shing → Save. JSON fayl o'zi yangilanadi.
3. Mantiq kerak bo'lsa `.py` (server) yoki `.js` (forma) ga yozing.
4. Boshqa kompyuterda: `git pull` → `bench --site ... migrate`.

### Git
- Branch: `karer-sotuv` (karer qismi). Beton qismi ustida sherik ham ishlaydi, shuning uchun push'dan oldin `git pull`.
- `apps/hrms` dagi tuzatish (patch guard) boshqa repo, bizning branch'ga kirmaydi.

---

## 11. Serverga chiqarish (production)

1. VPS (Ubuntu 22.04+, kamida 4 GB RAM) + domen (masalan `karer.uz`, yiliga ~10$). **Bitta domen butun loyihaga yetadi.**
2. Domen DNS: `A` yozuv → server IP.
3. Serverda:
   ```bash
   bench init frappe-bench --frappe-branch version-16
   bench get-app erpnext --branch version-16
   bench get-app hrms   --branch version-16
   bench get-app <carieer-repo> --branch karer-sotuv
   bench new-site karer.uz
   bench --site karer.uz install-app erpnext hrms carieer
   sudo bench setup production <user>
   sudo bench setup lets-encrypt karer.uz        # bepul HTTPS
   ```
4. **GPS token'ni yangi uzun parolga almashtiring** (test token'ni ishlatmang).
5. Traccar Client URL: `https://karer.uz/api/method/carieer.api.traccar?token=<yangi token>`.
6. Zaxira nusxa: `bench --site karer.uz backup --with-files` (cron orqali har kuni).

---

## 12. Tez-tez uchraydigan xatolar

| Xato | Sabab | Yechim |
|---|---|---|
| `Out of range value for column 'total_qty'` | Miqdorga juda katta raqam yozilgan | Raqamni tekshiring (20 t = `20000` kg) |
| "Xomashyo yetarli emas" | Beton xomashyo omborida kam | Xarid qiling yoki Material Transfer bilan o'tkazing |
| "BOM faol va submit qilingan bo'lishi kerak" | BOM draft yoki Is Active ✗ | BOM'ni submit qiling, Is Active ✅ |
| "... kursi topilmadi" | USD kursi yo'q | Accounting → Currency Exchange → kurs kiriting |
| Sotuv'da ombor noto'g'ri | Karer Sozlamalari'da firma omborlari to'ldirilmagan | 4.3 ni bajaring |
| Telefon xaritada ko'rinmaydi | URL/token noto'g'ri, telefon ruxsati yo'q, internet yo'q | Traccar'da status log'ini ko'ring. Token, ruxsat va batareya tejashni tekshiring |
| Xaritada nom o'rniga raqam | Vehicle'da GPS IMEI yozilmagan | Vehicle → GPS qurilma IMEI |
| Vehicle yaratishda Odometer / Fuel UOM so'raydi | Majburiy maydonlar | Odometer `0`, Fuel UOM `Litre` |
| Manufacturing dashboard bo'sh | Work Order ishlatilmaydi | 6.4 ga qarang |
| Kod o'zgardi, lekin ishlamayapti | Dev server eski kodni ishlatyapti | `bench start` qayta, brauzerda Ctrl+Shift+R |
| Refresh qilganda logout bo'ladi | Brauzer cookie | Cookie'larni tozalang, bitta manzildan kiring (IP yoki domen) |

---

## Dostup: Karer va Beton zavod alohida

| Zavod | Rollar (lavozim) | Firma roli | Ko'radi |
|---|---|---|---|
| Karer | Karer Operator / Karer Kassir / Karer Menejer | Karer xodimi | Karer workspace, Qazib Olish, Karer Sozlamalari, Sotuv (Karer) |
| Beton | Beton Operator / Beton Kassir / Beton Menejer | Beton zavod xodimi | Beton Zavod workspace, Beton Ishlab Chiqarish, Sotuv (Beton) |

- Umumiy hujjatlar (Sotuv, Kassa, Начисление, Приход ОС, Yoqilg'i, hisobotlar) ikkala zavodda bor, lekin
  **User Permission -> Company** bilan har kim faqat o'z firmasi ma'lumotini ko'radi.
- Beton xodimiga "Karer" nomli sahifa ko'rinmaydi (ilova va sidebar nomi ham "Beton Zavod"), karer xodimiga beton sahifalari ko'rinmaydi.
- Firmalararo Sotuv / To'lov va Firmalararo Qarzlar ikkala firmaga ko'rinadi.
- Xodim yaratish (System Manager):

  ```
  bench --site SITE execute carieer.install.setup_firma_user --kwargs "{'email': 'menejer@beton.uz', 'full_name': 'Ali Valiyev', 'company': 'Beton Zavod', 'role': 'Beton Menejer', 'password': '...'}"
  ```

  Firma roli va workspace roldan o'zi aniqlanadi, boshqa zavodning rollari olib tashlanadi.
