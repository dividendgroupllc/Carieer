## Carieer

Eko Karer va Beton Zavod uchun ERPNext v16 ilovasi: sotuv posti, kassa, nachislenie, ombor, beton ishlab chiqarish,
firmalararo oldi-sotdi (Sales / Purchase Invoice), texnika (yoqilg'i, GPS) va Google Sheets'dagi hisobotlar
(Оборотка, Акт сверка, ДДС, Cash Flow, P&L, Баланс, Қарздорликлар, Отчет).

Custom JS yo'q — hammasi Frappe / ERPNext'ning o'z UI'si bilan. To'liq qo'llanma: [carieer_readme.md](carieer_readme.md).

### O'rnatish (Frappe v16 + ERPNext v16 + HRMS v16)

```bash
cd frappe-bench
bench new-site SITE --db-root-password 'MYSQL_ROOT' --admin-password 'Admin123!' --install-app erpnext --install-app hrms
# brauzerda Setup Wizard (UZS), keyin ikkinchi firma (Company)
bench --site SITE install-app carieer
bench build --app carieer
bench --site SITE execute carieer.install.setup_karer --kwargs "{'karer_company': 'Eko Karer', 'beton_company': 'Eko Beton'}"
bench --site SITE execute carieer.install.setup_user --kwargs "{'email': 'post@firma.uz', 'full_name': 'Post Operator', 'zavod': 'Ikkalasi', 'lavozim': 'Operator', 'password': 'Parol123!'}"
```

### License

mit
