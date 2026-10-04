# Carieer — Eko Karer va Beton Zavod (ERPNext v16 ustida)

Karer va beton zavodining hisob-kitobi: **sotuv posti, kassa, nachislenie, ombor, beton ishlab chiqarish,
firmalararo oldi-sotdi, texnika (yoqilg'i, GPS) va Google Sheets'dagi barcha hisobotlar**.

> **Custom JS yo'q.** Hamma forma, ro'yxat, hisobot va menyu Frappe / ERPNext'ning o'z UI'si bilan ishlaydi.
> Mantiq faqat Python'da (`validate`, `on_submit`), filtrlar DocType va Report JSON'ida.

---

## 1. Bo'limlar (menyu)

Desktop'da faqat **ikkita** ikonka: **Karer** va **Beton Zavod**. Har biri chap menyuli bo'lim.
Menyudagi har bir punkt foydalanuvchining ruxsatiga qarab o'zi ko'rinadi / yashirinadi.

| Bo'lim (chap menyu) | Karer | Beton Zavod |
|---|---|---|
| Bosh sahifa | ko'rsatkichlar (bugungi / oylik sotuv, qarz, kassa, qazib olingan), kunlik sotuv grafigi, tezkor tugmalar | xuddi shunday (ishlab chiqarilgan beton) |
| Sotuv posti | Sotuv, Mijozlar | Sotuv, Mijozlar |
| Ishlab chiqarish | — | Beton ishlab chiqarish, Retsept (BOM) |
| Kassa va qarzlar | Kassa, Начисление, Firmalararo to'lov, Valyuta kursi | xuddi shunday |
| Ombor | Qazib olish, Приход (xarid), Приход ОС, Инвентаризация, Ombor harakati | Приход, Приход ОС, Инвентаризация, Ombor harakati |
| Texnika | Texnikalar, Texnikalar xaritasi, Yoqilg'i va moy, GPS nuqtalar | xuddi shunday |
| Hisobotlar | 11 ta hisobot (8-bo'lim) | xuddi shunday |
| Sozlamalar | Zavodlar, Tovarlar, Omborlar, Kassalar, Kategoriyalar, Ta'minotchilar, Xodimlar, Birliklar, Hisoblar rejasi, Karer sozlamalari | xuddi shunday |

## 2. Rollar va dostup

6 ta rol = **zavod** (Karer / Beton) × **lavozim** (Operator / Kassir / Menejer).
Har bir xodim faqat o'z firmasining ma'lumotini ko'radi (ERPNext **User Permission → Company**).

| Hujjat / hisobot | Operator | Kassir | Menejer |
|---|---|---|---|
| Sotuv (yaratish, tasdiqlash, to'lov qo'shish) | ✅ (bekor qila olmaydi) | ✅ + bekor qilish | ✅ hammasi |
| Qazib olish | faqat Karer operatori | — | Karer menejeri |
| Beton ishlab chiqarish | faqat Beton operatori | — | Beton menejeri |
| Yoqilg'i hisobi | ✅ | — | ✅ |
| Kassa, Начисление, Firmalararo to'lov | — | ✅ | ✅ |
| Приход ОС, Приход, Инвентаризация, BOM | — | — | ✅ |
| Kunlik otchet, Material hisobot | ✅ | ✅ (kunlik) | ✅ |
| Akt sverka, Оборотка, Qarzdorlik, ДДС, Cash Flow, Firmalararo qarzlar | — | ✅ | ✅ |
| P&L, Баланс, Texnika xarajatlari | — | — | ✅ |

* Karer xodimi desktop'da faqat **Karer**, beton xodimi faqat **Beton Zavod** ikonkasini ko'radi
  (ERPNext'ning Selling, Stock, Accounting ... ikonkalari ularga ko'rinmaydi).
* **Sotuv posti operatori** ikkala zavod nomidan sotadi: ikkala bo'lim ham ko'rinadi, Sotuv'da «Тип» tanlaydi.
* System Manager hamma narsani ko'radi.

## 3. Yangi sayt (WSL terminalida)

```bash
cd /mnt/d/finance/frappe-bench-v16

# 1) yangi sayt + ERPNext + HRMS
bench new-site ekokarer.local --db-root-password 'MYSQL_ROOT_PAROL' --admin-password 'Admin123!' \
    --install-app erpnext --install-app hrms
bench use ekokarer.local

# 2) brauzerda Setup Wizard: Uzbekistan, UZS, Asia/Tashkent, birinchi firma (masalan "Eko Karer")
bench start            # boshqa terminalda; http://localhost:8001
#    Setup Wizard tugagach: Company -> New -> ikkinchi firma "Eko Beton" (valyuta UZS)

# 3) ilova
bench --site ekokarer.local install-app carieer
bench build --app carieer
bench --site ekokarer.local clear-cache

# 4) bir martalik sozlash: omborlar, kassalar, tovarlar, xizmatlar, kategoriyalar, Zavod, firmalararo kontragentlar
bench --site ekokarer.local execute carieer.install.setup_karer \
    --kwargs "{'karer_company': 'Eko Karer', 'beton_company': 'Eko Beton'}"

# 5) xodimlar (zavod: Karer | Beton | Ikkalasi,  lavozim: Operator | Kassir | Menejer)
bench --site ekokarer.local execute carieer.install.setup_user \
    --kwargs "{'email': 'post@ekokarer.uz', 'full_name': 'Post Operator', 'zavod': 'Ikkalasi', 'lavozim': 'Operator', 'password': 'Parol123!'}"
bench --site ekokarer.local execute carieer.install.setup_user \
    --kwargs "{'email': 'kassir@ekokarer.uz', 'full_name': 'Karer Kassir', 'zavod': 'Karer', 'lavozim': 'Kassir', 'password': 'Parol123!'}"
bench --site ekokarer.local execute carieer.install.setup_user \
    --kwargs "{'email': 'menejer@ekobeton.uz', 'full_name': 'Beton Menejer', 'zavod': 'Beton', 'lavozim': 'Menejer', 'password': 'Parol123!'}"
```

Keyin brauzerda (administrator):
1. **Valyuta kursi** (Currency Exchange): USD → UZS kursini kiriting (har kuni yoki o'zgarganda).
2. **Retsept (BOM)**: har bir beton markasi uchun (Beton Zavod firmasida) → Submit.
3. Boshlang'ich qoldiqlar: **Инвентаризация** (Stock Reconciliation) — karer tovari tan narxi 0 bo'lsa ham bo'ladi.
4. Kontragentlarning eski qarzlari: Journal Entry (Opening) yoki Начисление orqali.

> Eski `karer16.local` saytida yangi kodni `migrate` qilmang: u eski tuzilmada (Firmalararo Sotuv, firma rollari ...).
> Yangi sayt toza tuzilma bilan ishlaydi.

## 4. Kundalik ish

### 4.1 Sotuv posti («Ввод продажи») — operator
1. **Sotuv → Add** : Дата, **Тип** (Karer / Beton — firma o'zi qo'yiladi), **Валюта** (UZS / USD), **Доставка** (Да / Нет).
2. **Клиент**, **Номер машины**, haydovchi.
3. **Товары**: tovar (qum, sheben, klinets, beton ...), miqdor, narx. Ombor o'zi qo'yiladi.
4. **Услуги**: погрузчик, доставка ... (ombor tovari emas).
5. **Оплаты**: kassa (Наличные, Наличные $, Р/С, Карта ...), summa, kurs (bo'sh = Currency Exchange), kim to'ladi, izoh.
6. **Save** → summa, qarz (Долг) hisoblanadi. **Submit** → Sales Invoice (tovar ombordan chiqadi, mijozga qarz) +
   har bir to'lov uchun Payment Entry.
7. Keyinroq to'lov («Изменить оплату»): yakunlangan sotuvda **Оплаты** jadvaliga qator qo'shib **Update** bosiladi.

Holat: `To'lanmagan` → `Qisman to'langan` → `To'langan` (Kassa orqali olingan to'lov ham hisobga olinadi).

### 4.2 Qazib olish — karer operatori
Karerdan qazib olingan qum / sheben / klinets omborga **tan narxi 0** bilan kiradi (Stock Entry, Material Receipt).
Ombor bo'sh qoldirilsa Zavod'dagi asosiy ombor.

### 4.3 Kassa — kassir («Касса карьер»)
| Turi | Kontragent turi | Natija |
|---|---|---|
| Kirim / Chiqim | Customer, Supplier, Employee | Payment Entry (qarz kamayadi; mijoz to'lovi eng eski sotuvga taqsimlanadi) |
| Chiqim | Xarajat | Journal Entry: kassa → **kategoriya** moddasi (masalan Хоз.расход, Топливо и ГСМ) |
| Kirim | Daromad | Journal Entry: kassa ← Прочие доходы |
| Chiqim | Dividend | Journal Entry: kassa → Dividends Paid |
| O'tkazma | — | kassadan kassaga (Наличные → Р/С), valyuta har xil bo'lsa kurs bo'yicha |

**Kategoriya** har bir yozuvda: ДДС va Cash Flow shu bo'yicha yig'iladi (jadvaldagi kabi).

### 4.4 Начисление — pul harakatisiz qarz
* **Закуп услуга**: bizga xizmat ko'rsatildi (samosval, ekskavator ...) → biz ta'minotchiga qarzdormiz, xarajat moddaga yoziladi.
* **Продажа услуга**: biz xizmat ko'rsatdik → mijoz qarzdor, daromad.
Pul keyin Kassa orqali to'lanadi / olinadi.

### 4.5 Приход, Приход ОС, Инвентаризация
* **Приход (xarid)** — ERPNext Purchase Invoice (`Update Stock` ✅): sement, solyarka, metall, xizmatlar.
* **Приход ОС** — asosiy vosita kirimi: yetkazib beruvchidan (qarz) yoki ta'sischidan (ustav kapitali). USD ham bo'ladi.
* **Инвентаризация** — Stock Reconciliation (karer omborida tan narx 0 avtomatik ruxsat etiladi).

### 4.6 Firmalararo oldi-sotdi (Karer ↔ Beton)
* **Perexod / sotuv**: oddiy **Sotuv**, mijoz = ikkinchi firmamiz (ichki mijoz). Submit → sotuvchida Sales Invoice,
  xaridorda **avtomatik Purchase Invoice** (tovar uning xomashyo omboriga kiradi). Ikkala kitob doim mos.
* **To'lov**: **Firmalararo to'lov** → ikkala firmada Payment Entry (to'lovchida chiqim, oluvchida kirim).
* Holat: **Firmalararo qarzlar** hisoboti.

### 4.7 Beton
1. Karerdan sheben / qum — firmalararo sotuv (4.6) bilan **Beton xomashyo** omboriga.
2. Sement, ximikat — Приход (Purchase Invoice) bilan Beton xomashyo omboriga.
3. **Beton ishlab chiqarish**: BOM + miqdor → saqlaganda xomashyo jadvali (kerak / bor), Submit →
   Stock Entry (Manufacture): xomashyo chiqadi, beton kiradi, tan narx avtomatik.
4. Beton sotuvi — Sotuv, Тип = Beton.

### 4.8 Texnika, yoqilg'i, GPS
* **Texnikalar** (Vehicle): raqam, marka, model, texnika turi, GPS IMEI.
* **Yoqilg'i va moy**: *Ombordan* → ombordan chiqim, xarajat «Топливо и ГСМ» / «Масло для техники» moddasiga;
  *Zapravkadan* → zapravkaga qarz (Journal Entry), pul Kassa orqali. Spidometr bo'yicha 100 km ga sarf.
* **GPS**: telefon (Traccar Client) yoki trekker o'zi yuboradi:
  `https://DOMEN/api/method/carieer.api.traccar?token=GPS_TOKEN` (token: Karer sozlamalari).
* **Texnikalar xaritasi** — Vehicle ro'yxatining Frappe'dagi o'z **Map** ko'rinishi (oxirgi joy);
  **GPS nuqtalar → Map** — tanlangan texnika / kun bo'yicha yo'l.

## 5. Google Sheets → tizim

| Varaq | Tizimda |
|---|---|
| Диспетчер | Tovarlar (Item), birliklar, xizmatlar, Kassa Kategoriya, kassalar (Mode of Payment), kontragentlar |
| Продажа карьер | **Sotuv** |
| Касса карьер | **Kassa** |
| Приход | Purchase Invoice |
| Приход ОС | **Prixod OS** |
| Инвентаризация | Stock Reconciliation |
| Начисление карьер | **Nachislenie** |
| Оборотка Контрагентов | hisobot **Kontragent Otchet** |
| Акт сверка | **Akt Sverka** |
| Баланс / Баланс бпр | **Balans** |
| P&L / P&L Разбитый | **Foyda Zarar** |
| Cash Flow | **Pul Oqimi** |
| ДДС | **DDS** |
| Отчет | **Kontrol Hisobot** (ko'rinish: Kunlik otchet) |
| Постав/Клиент, БД контрагент | Kontragent Otchet (tur filtri) |
| Карздорликлар | **Qarzdorlik** (7 / 14 / 21 kun) |

## 6. Hisobotlar

| Hisobot | Nima ko'rsatadi |
|---|---|
| **Kontrol Hisobot** | *Kunlik otchet*: ПРОДАЖА (mijoz, tovar, miqdor, narx, summa) + КАССА (kategoriya bo'yicha kirim / chiqim), tepada kassa qoldig'i. *Sotuvlar*: har bir sotuv, guruhlash (mijoz / tovar / kun / mashina) |
| **Kontragent Otchet** | Оборотка: boshlang'ich, oborot, yakuniy qoldiq (Кредит / Дебет, сўм va $ alohida), Акт сверка havolasi |
| **Akt Sverka** | bitta kontragent: har bir hujjat (tovar, miqdor, narx), to'lovlar, начисления, qoldiq; tepada yig'ma |
| **Qarzdorlik** | sof qarz va muddati: 7 kun ichi, 7 / 14 / 21 kundan ko'p (FIFO) |
| **DDS** | kategoriya × valyuta (kirim / chiqim), boshlang'ich va yakuniy qoldiq; «Batafsil» — har bir harakat |
| **Pul Oqimi** | Cash Flow oyma-oy: kirim kategoriyalari, chiqim guruhlari (Административный, Производственный ...) |
| **Foyda Zarar** | P&L Разбитый oyma-oy: выручка, себестоимость, маржа, xarajatlar daraxti, чистая прибыль, рентабельность |
| **Balans** | oy oxiriga: kassalar, debitorlar, zapaslar, OS, kreditorlar, kapital, foyda; «Разница» = 0 |
| **Material Hisobot** | tovar × ombor: qoldiq, qazib olindi, ishlab chiqarildi, xarid, sotildi, sarf, yakuniy |
| **Firmalararo Qarzlar** | Karer ↔ Beton: kim kimdan qancha qarz va nima uchun |
| **Texnika Xarajatlari** | texnika bo'yicha litr, summa, km, 100 km ga sarf, motor soat |

Filtrlar hisobot JSON'ida; **Firma** bo'sh qoldirilsa — o'z firmangiz, **Sana dan** bo'sh — oy / yil boshi.
ERPNext'ning standart hisobotlari (General Ledger, Stock Balance, Accounts Receivable ...) menejerga ham ochiq.

## 7. Kod tuzilishi

```
carieer/
├── hooks.py             doc_events (Payment Entry, Vehicle, Stock Reconciliation), boot_session, scheduler
├── install.py           after_migrate (rollar, ruxsatlar, Vehicle maydonlari) + setup_karer + setup_user
├── permissions.py       rollar, firma ruxsati, menyuni tozalash (boot_session)
├── utils.py             Zavod, kurs, kassa, kategoriya -> hisob, ombor, firmalararo, SMS
├── events.py            Stock Reconciliation: karer tovari tan narxi 0
├── api.py               GPS: traccar(), gps_push(), cleanup_gps()
├── desktop_icon/        Karer, Beton Zavod ikonkalari (rol bo'yicha)
├── workspace_sidebar/   chap menyu (Karer, Beton Zavod)
├── public/icons/        desktop ikonkalari (svg)
└── carieer/
    ├── doctype/         sotuv(+tovar, xizmat, tolov), kassa, nachislenie, prixod_os, qazib_olish(+tovar),
    │                    beton_ishlab_chiqarish(+xomashyo), firmalararo_tolov, yoqilgi_hisobi, gps_malumot,
    │                    zavod, kassa_kategoriya, karer_sozlamalari
    ├── report/          11 ta hisobot (.py + .json filtrlar), common.py, moliya.py
    ├── workspace/       Karer, Beton Zavod bosh sahifalari
    ├── number_card/     ko'rsatkichlar
    ├── dashboard_chart/ kunlik sotuv grafigi
    └── dashboard.py     kassa qoldig'i, mijozlar qarzi kartochkalari
```

## 8. Tez-tez uchraydigan xatolar

| Xato | Yechim |
|---|---|
| «USD -> UZS kursi topilmadi» | Valyuta kursi (Currency Exchange) ga kurs kiriting |
| «... omborida ... yetarli emas» | Qazib olish / Приход / Инвентаризация bilan qoldiqni kiriting |
| «... kassasida ... firmasi uchun hisob yo'q» | Kassalar (Mode of Payment) → Accounts jadvaliga shu firma hisobini qo'shing |
| «Zavod '...' uchun firma ko'rsatilmagan» | Sozlamalar → Zavodlar: Karer va Beton yozuvlari (setup_karer yaratadi) |
| «Ichki firmaga sotuvda to'lov shu yerda olinmaydi» | Firmalararo to'lov orqali kiriting |
| Firmalararo sotuvni bekor qilib bo'lmaydi | Avval undan foydalangan hujjatlarni (beton ishlab chiqarish, sotuv) bekor qiling |
| Menyuda bo'lim ko'rinmaydi | `bench --site SITE clear-cache`, foydalanuvchi qayta kirsin |
