# Carieer — Eko Karer (ERPNext v16 ustida)

Google Sheets'dagi «Эко Карьер» jadvalining o'rnini bosadigan tizim: **sotuv posti, kassa, начисление, приход,
приход ОС, инвентаризация va jadvaldagi barcha hisobotlar** (Оборотка, Акт сверка, ДДС, Cash Flow, P&L, Баланс ...).

> Faqat **Eko Karer** firmasi. Eko Beton (ishlab chiqarish, retsept, texnika / GPS) — alohida loyiha.
>
> **Formalarda custom JS yo'q.** Forma, ro'yxat, hisobot va menyu Frappe / ERPNext'ning o'z UI'si bilan ishlaydi.
> Mantiq Python'da (`validate`, `on_submit`), filtrlar DocType va Report JSON'ida.

---

## 1. Ikonkalar = jadval varaqlari

Desktop'dagi har bir ikonka jadvaldagi bitta varaq. Xodim faqat o'z roliga tegishli ikonkalarni ko'radi.

| Ikonka (varaq) | Tizimda | Kimga |
|---|---|---|
| Эко Карьер | bosh sahifa + barcha jurnal, hisobot va ma'lumotnomalar menyusi | System Manager |
| Диспетчер | Tovarlar, Tovar guruhlari (Тип), Mijozlar, Ta'minotchilar, Xodimlar, Kategoriyalar, Hisoblar (Счета), Kurs | Menejer |
| Продажа карьер | **Sotuv** | Operator, Kassir, Menejer |
| Касса карьер | **Kassa** | Kassir, Menejer |
| Приход | hisobot **Prixod** + Purchase Invoice | Menejer |
| Приход ОС | **Prixod OS** | Menejer |
| Инвентаризация | Stock Reconciliation + Материальный отчет | Menejer |
| Начисление карьер | **Nachislenie** | Kassir, Menejer |
| Оборотка Контрагентов | **Kontragent Otchet** | Kassir, Menejer |
| Акт сверка | **Akt Sverka** | Kassir, Menejer |
| Баланс / Баланс бпр | **Balans** / **Balans Bpr** | Menejer |
| P&L / P&L Разбитый | **Foyda Zarar** / **Pl Razbityi** | Menejer |
| Cash Flow | **Pul Oqimi** | Kassir, Menejer |
| Отчет | **Kontrol Hisobot** (kunlik otchet) | Operator, Kassir, Menejer |
| ДДС | **DDS** | Kassir, Menejer |
| Постав Клиент / Постав Клиент Факт | **Postav Klient** / **Postav Klient Fakt** | Kassir, Menejer |
| Кардорликлар | **Qarzdorlik** (7 / 14 / 21+ kun, FIFO) | Kassir, Menejer |
| БД контрагент | **BD Kontragent** | Kassir, Menejer |
| ПР Срав. | **Pr Srav** — mahsulot bo'yicha oyma-oy sotuv, СС, marja («ПР Срав. Общ» — Гуруҳлаш = Наименование) | Menejer |
| Контрагент отчет нев | **Kontragent Oylik** — kontragent × oy: Приход, Продажа, Услуга, Деньги | Kassir, Menejer |
| Материальный отчет | **Material Hisobot** — tovar bo'yicha qoldiq, kirim, chiqim | Kassir, Menejer |

Rollar: **Karer Operator** (sotuv posti), **Karer Kassir**, **Karer Menejer**. Xodim faqat o'z firmasini ko'radi
(User Permission → Company / Zavod), desktop'da faqat Carieer ikonkalari (`permissions.hide_foreign_icons`).
Ikonka kimga ko'rinishi — `desktop_icon/*.json` dagi `roles`.

## 2. O'rnatish

```bash
cd frappe-bench
bench new-site SITE --admin-password 'Admin123!' --install-app erpnext --install-app hrms
# brauzerda Setup Wizard: Uzbekistan, UZS, Asia/Tashkent, firma (masalan "Eko Karer")
bench --site SITE install-app carieer
bench build --app carieer

# bir martalik sozlash: Zavod «Karer», omborlar, kassalar, «Диспетчер» ro'yxatlari (tovarlar, kategoriyalar,
# kontragentlar, kurs) - carieer/data/dispetcher.json dan
bench --site SITE execute carieer.install.setup_karer --kwargs "{'karer_company': 'Eko Karer'}"

# xodimlar (lavozim: Operator | Kassir | Menejer)
bench --site SITE execute carieer.install.setup_user \
    --kwargs "{'email': 'kassir@ekokarer.uz', 'full_name': 'Karer Kassir', 'lavozim': 'Kassir', 'password': 'Parol123!'}"
```

Kod yangilangandan keyin: `bench --site SITE migrate && bench build --app carieer`.

## 3. Kundalik ish

**Tovar.** Karer mahsuloti (qum, sheben, klinets) — «Maintain Stock» ✅, tan narxi **0** (yerdan qazib olinadi).
Qoldiq **Инвентаризация** (Stock Reconciliation) bilan kiritiladi, tan narx 0 ruxsat etilgan. Sotuv qoldiq yetmasa
ham bloklanmaydi (jadvaldagidek), faqat ogohlantiradi.

**Sotuv** («Продажа карьер», operator): Дата, Тип, Валюта (UZS / USD), Доставка, Клиент, Номер машины, haydovchi →
**Товары** (miqdor, narx; narx 0 bo'lsa Item Price'dan) → **Услуги** → **Оплаты** (kassa, summa, kurs, kim, izoh) →
Save → Submit: Sales Invoice (tovar ombordan chiqadi, mijozga qarz) + har bir to'lov uchun Payment Entry.
Keyinroq to'lov — tasdiqlangan sotuvda Оплаты'ga qator qo'shib **Update**. Tovarsiz tuzatish — «Корректировка».

**Kassa** («Касса карьер», kassir):

| Turi | Kontragent | Natija |
|---|---|---|
| Kirim / Chiqim | Customer, Supplier, Employee | Payment Entry (mijoz to'lovi eng eski qarzga taqsimlanadi) |
| Chiqim | Xarajat | xarajat **kategoriya** moddasiga (Топливо и ГСМ, Хоз.расход ...) |
| Kirim | Daromad | Прочие доходы |
| Chiqim / Kirim | Dividend, Kapital | Dividends / Инвестиция, Сальдо, Фин займ |
| O'tkazma / Konvertatsiya | — | kassadan kassaga (Перемещение), valyuta har xil bo'lsa kurs bo'yicha |

Kassada pul yetmasa chiqim bloklanmaydi (jadvaldagidek): ogohlantirish chiqadi, kassa minusga kiradi.

**Начисление** — pul harakatisiz qarz: *Закуп услуга* (bizga xizmat → ta'minotchiga qarz, xarajat moddaga),
*Продажа услуга* (biz xizmat ko'rsatdik → mijoz qarzdor, daromad). Pul keyin Kassa orqali.

**Приход** — Purchase Invoice (`Update Stock` ✅) yoki Purchase Receipt → Purchase Invoice.
**Приход ОС** — asosiy vosita kirimi (ta'minotchidan qarz yoki ta'sischidan), USD ham bo'ladi.

## 4. Hisobotlar qanday hisoblaydi

* **P&L** (Foyda Zarar): Выручка (продукции / услуг) → Себестоимость → Маржинальная прибыль → Общепроизводственные
  (kategoriya «Оборот» = Произв) → Валовая прибыль → Административные → Операционная / Чистая прибыль.
  Manba — GL Entry. Kontragentga to'lov xarajat emas (qarzni yopish), xarajat Kassa (Xarajat), Начисление yoki
  Purchase Invoice kunida tushadi — jadvaldagi formula bilan bir xil natija. «На ОС» kategoriyasi Balansga o'tadi.
* **P&L Разбитый**: xarajatlar kategoriya daraxti bo'yicha (guruh 1 → guruh 2 → modda, jadvaldagi Лист55).
* **ПР Срав.**: tasdiqlangan Sotuv tovar qatorlari; Продажа so'mda (USD sotuv kurs bo'yicha), СС — Sotuv'dagi «Сумма СС».
* **Контрагент отчет нев**: kredit tomoni: Сальдо кон. = нач. + Приход − Продажа + Услуга + Деньги Кр − Деньги Дт
  (musbat — biz qarzdormiz, manfiy — kontragent qarzdor). Boshqa provodkalar bo'lsa «Прочие» ustuni chiqadi.
* **Материальный отчет**: Stock Ledger bo'yicha; Инвентаризация farqi ham kirim / chiqimga tushadi.

Filtrlar: **Firma** bo'sh — o'z firmangiz, **Сана дан** bo'sh — oy yoki yil boshi.

## 5. Jadvalda bor, tizimda boshqacha

| Varaq | Nega |
|---|---|
| Муммо контр | kontragent nomlaridagi bo'sh joy farqlarini tutish uchun yordamchi ro'yxat; tizimda kontragent ro'yxatdan tanlanadi, bunday xato bo'lmaydi |
| ПР Срав. (jadvaldagi) | formulalar noto'g'ri ustunlarga qaragan (natija 0); tizimda to'g'ri hisoblanadi |
| Производство | Eko Beton loyihasida |
| Зарплата, Сотрудники, Посещение, Расчёт ЗП, ВЕДОМОСТЬ, Рабочие дни, Ишчи ойлиги | keyingi bosqich (HRMS); hozircha oylik Kassa orqali «Зарплата ...» kategoriyasi bilan to'lanadi |

## 6. Kod tuzilishi

```
carieer/
├── hooks.py          doc_events: Payment Entry (Sotuv qarzi), Kassa Kategoriya (modda hisobi), Mode of Payment,
│                     Currency Exchange (teskari kurs), Stock Reconciliation (tan narx 0)
├── install.py        after_migrate (rollar, ruxsatlar, maydonlar) + setup_karer + setup_user + seed_dispetcher
├── permissions.py    firma ruxsati, menyuni tozalash
├── utils.py          zavod, kurs, kassa, kategoriya -> hisob
├── events.py         Инвентаризация: karer tovari tan narxi 0
├── data/             dispetcher.json (jadvaldagi «Диспетчер» ro'yxatlari)
├── desktop_icon/     ikonkalar (har bir varaq), rollar
└── carieer/
    ├── doctype/      sotuv (+ tovar, xizmat, tolov), kassa, kassa_kategoriya, nachislenie, prixod_os, zavod,
    │                 karer_sozlamalari
    ├── report/       hisobotlar (.py + .json filtrlar), common.py, moliya.py (oylik ustunlar, P&L qoidalari)
    ├── sidebar/      har bir ikonkaning chap menyusi
    └── workspace/    Эко Карьер bosh sahifasi
```

## 7. Tez-tez uchraydigan xatolar

| Xato | Yechim |
|---|---|
| «USD -> UZS kursi topilmadi» | Kurs (Currency Exchange) ga shu kun kursini kiriting |
| «... narxini kiriting» | Sotuvda narxni yozing yoki Item Price ga qo'shing |
| «... kassasida ... firmasi uchun hisob yo'q» | Hisoblar (Mode of Payment) → Accounts jadvaliga firma hisobini qo'shing |
| «Zavod 'Karer' topilmadi» | `setup_karer` ni ishga tushiring |
| Menyuda ikonka ko'rinmaydi | `bench --site SITE clear-cache`, foydalanuvchi qayta kirsin |
