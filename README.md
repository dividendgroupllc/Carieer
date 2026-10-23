## Carieer

Eko Karer uchun ERPNext v16 ilovasi — Google Sheets'dagi «Эко Карьер» jadvalining o'rnini bosadi: sotuv posti, kassa,
начисление, приход, приход ОС, инвентаризация va jadvaldagi hisobotlar (Оборотка, Акт сверка, ДДС, Cash Flow, P&L,
P&L Разбитый, Баланс, Қарздорликлар, Отчет, ПР Срав., Контрагент отчет нев, Материальный отчет).

Custom JS yo'q — hammasi Frappe / ERPNext'ning o'z UI'si bilan. To'liq qo'llanma: [carieer_readme.md](carieer_readme.md).

### O'rnatish (Frappe v16 + ERPNext v16 + HRMS v16)

```bash
cd frappe-bench
bench new-site SITE --admin-password 'Admin123!' --install-app erpnext --install-app hrms
# brauzerda Setup Wizard (UZS)
bench --site SITE install-app carieer
bench build --app carieer
bench --site SITE execute carieer.install.setup_karer --kwargs "{'karer_company': 'Eko Karer'}"
bench --site SITE execute carieer.install.setup_user --kwargs "{'email': 'post@firma.uz', 'full_name': 'Post Operator', 'lavozim': 'Operator', 'password': 'Parol123!'}"
```

### License

mit
