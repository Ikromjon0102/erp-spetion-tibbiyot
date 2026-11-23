# O'zgarishlar tarixi

Yangi o'zgarishlar yuqoridan qo'shiladi.

## «Filial rahbari» lavozimi (2026-11-23)
- Yangi lavozim andozasi (migratsiya `panel.0008`): o'z filialida kundalik boshqaruv — o'quvchi, ustoz, ota-ona, sinf, jadval, to'lov qabul qilish, qarzdorlar, kunlik nazorat, terminallar, e'lonlar, taomnoma, xodimlar ro'yxatini ko'rish. **Yo'q:** xodim qo'shish/ruxsat, xarajat va oyliklar, narx va chegirmalar, to'lovni bekor qilish, faoliyat jurnali, exam bog'lash.
- Qaysi filial — xodim qo'shishda «Ish filiallari»da bitta filial belgilanadi; boshqa filiallar unga ko'rinmaydi, yangi filial ham avtomatik qo'shilmaydi.
- Sinov serverida: «Filial rahbari» (Markaz · Apteka) — +998 90 111-00-08.

## Yangi filial avtomatik biriktiriladi (2026-11-23)
- Founder yangi filial qo'shganda u tashkilotning **hamma filialiga biriktirilgan panel xodimlariga** (markaz direktori, hisobchi...) o'zi qo'shiladi. Bitta filialda ishlaydigan xodim (filial rahbari, reception) va ustozlarga qo'shilmaydi. Tashkilotda oldin bitta filial bo'lsa hech kim avtomatik qo'shilmaydi. Kimlarga qo'shilgani xabarda va jurnalda.

## Oylik: kiritish, avans va yakuniy hisob (2026-11-23, hisobchi fikri)
- **Qo'shishda oylik:** «Ustoz qo'shish» va «Xodim qo'shish» formalarida «Oylik ish haqi» bloki — qat'iy oylik (so'm) yoki foiz (o'quvchilar to'lovidan), yoki «keyin kiritiladi». Faqat oylik ruxsati borlarga (founder, hisobchi) chiqadi; direktor ustoz qo'shsa blok o'rnida «oylikni hisobchi kiritadi» yoziladi. Bir nechta filial belgilansa: foiz — hammasiga, qat'iy oylik — birinchi filialga.
- **Kartada «Oylik» bloki** (ustoz va xodim sahifasi, `payroll.view` bo'lsa): amaldagi oylik, shu oy avansi va yakuniy hisob holati; «Oylikni o'zgartirish» → bitta odamning oylik sahifasi (o'zgartirish «qaysi oydan» bilan, eski oylar o'zgarmaydi; tarix).
- **«Xodimlar oyligi»** (avvalgi «Oylik qoidalari» o'rniga): filialdagi hamma ustoz va xodim, oyligi belgilanmaganlar tepada. Founder ro'yxatda yo'q.
- **Avans va yakuniy hisob:** tashkilot bo'yicha sozlama — avans kuni (standart 15) va foizi (standart 50%, minggacha yaxlitlanadi); yakuniy hisob — oyning oxirgi kuni. Oyliklar sahifasida ikki karta: sana, «N kun qoldi / o'tdi», reja, to'langan, to'lanmagan. Jadvalda «Avans» ustuni va «Avans» tugmasi (summa va tur oldindan to'ldiriladi).
- Joriy oy hisobi sahifa ochilganda o'zi yangilanadi («Qayta hisoblash» tugmasi qoldi). Oyligi belgilanmaganlar soni ogohlantirishda.
- **Eslatma:** avansdan 3 kun oldin va oyning oxirgi 3 kunida (o'tgan oy qoldig'i — keyingi oyning 1–10 kunlari) bosh sahifada va founder «Raqamlar»ida: «Avans · 15-noyabr (2 kun qoldi) — 12 kishiga … so'm to'lanmagan».

## Founder ko'rinmaydi; tashkilot va filial qo'shish — faqat founder (2026-11-23)
- **Founder hech kimga ko'rinmaydi:** «maktab egasi» va texnik admin boshqa xodimlarning «Xodimlar» ro'yxatida, sonida va kartasida yo'q (kartasi 404); ular qilgan ishlar «Faoliyat jurnali»da va xodim kartasidagi «Oxirgi o'zgarishlar»da quyi xodimlarga umuman ko'rsatilmaydi. Founderlar bir-birini va hamma yozuvni ko'radi.
- **Filial qo'shish** («Tashkilot va brend» → «Filiallar»): nomi, manzili, telefoni; mavjud filialni qayta nomlash. Tashkilot ichida nom takrorlanmaydi.
- **Yangi tashkilot qo'shish** («Yangi tashkilot»): nomi, qisqa nomi, turi (maktab / bog'cha / o'quv markaz), rangi, taomnoma, birinchi filial. Saqlangach ish maydonida tanlanadi.
- Ikkalasi **faqat founder** uchun (markaz direktori yoki «Tashkilot sozlamasi» ruxsati bor xodim ham qila olmaydi — 403). Jurnalga yoziladi.
- **«Tashkilot va brend» sahifasi butunlay faqat founderda** (nomi, rangi, modullar, filiallar): boshqa xodimlarning menyusidan olib tashlandi, sahifa ularga 403. `org.settings` ruxsati endi faqat «Exam bilan bog'lash» uchun.

## Filial darajasidagi ko'rinish (2026-11-23)
- **Filial kartalari:** ish maydoni bitta tashkilotni, lekin bir nechta filialni qamrasa (markaz direktori 3–5 filial bilan, yoki founder «Markaz»ni tanlaganda), har bo'lim avval **filial kartalarini** ko'rsatadi: o'quvchilar, ustozlar, xodimlar, ota-onalar, sinflar, dars jadvali, terminallar, to'lovlar (shu oy tushumi), xarajatlar va oyliklar (ruxsat bo'lsa), e'lonlar. Karta bosilsa o'sha filial tanlanadi. Bir nechta tashkilot bo'lsa — avvalgidek tashkilot kartalari (`panel/hubs.py`: `hub_level`, `counts`). Ikki filialda ishlaydigan odam «jami»da bir marta sanaladi.
- **Bosh sahifada «Filiallar bo'yicha» jadvali** (bir nechta filial/tashkilot bilan ishlaydigan xodimlar uchun): o'quvchilar, bugun kelganlar, shu oy tushumi va (ruxsat bo'lsa) xarajati; qator bosilsa filial tanlanadi.
- Ish maydoni nomi: bitta tashkilotli xodimda «Markaz · barcha filiallar».
- Sinov ma'lumoti: `seed_mock_center` — markazga «Filial 2 (Chilonzor)», «Filial 3 (Yunusobod)» (guruh, o'quvchi, to'lov, ustoz, terminal, xarajat) va «Markaz direktori» (+998 90 111-00-07).
- Lavozimlar (Direktor, Hisobchi...) — umumiy andoza (ruxsatlar to'plami); qaysi tashkilot/filialni ko'rishi xodimning ish filiallari bilan belgilanadi.

## Xodim va ustoz qo'shish: filial va parol (2026-11-23)
- **Xato:** Tibbiyot uchun qo'shilgan direktor Bog'chaga ham tushib qolgan edi. Sabab: yangi xodim yaratuvchining joriy «Ish maydoni»ga (o'sha payt Bog'cha) biriktirilardi, ustiga avtomatik «asosiy filial» (Tibbiyot) qo'shilardi; formada filial tanlovi yo'q edi.
- **Tuzatildi:** «Xodim qo'shish» va «Ustoz qo'shish» formalarida majburiy **«Ish filiallari»** (tashkilotlar bo'yicha katakchalar). Joriy ish maydoni oldindan belgilanadi, lekin ko'rinib turadi; tahrirlovchining bitta filiali bo'lsa — o'zi tanlanadi. Yangi odam faqat belgilangan filiallarga tushadi (avtomatik filial qo'shilmaydi). Yangi odam joriy ish maydonida ko'rinmasa, ish maydoni uning tashkilotiga o'tadi (aks holda saqlangach sahifa «topilmadi» bo'lardi).
- **Parol qoidasi hamma uchun bir xil:** login — telefon, boshlang'ich parol — telefonning oxirgi 4 raqami, birinchi kirishda yangi parol qo'yiladi. Endi xodimlar (direktor, hisobchi...) uchun ham (avval tasodifiy bir martalik parol edi); xodim sahifasidagi tugma — «Parolni tiklash (oxirgi 4 raqam)». Telefon kiritilmagan bo'lsa — bir martalik parol.
- Sinov serveridagi yangi direktordan ortiqcha Bog'cha filiali olib tashlandi.

## Ustoz sahifasi: tashkilot bo'yicha (2026-11-23, founder fikrlari)
- **Faqat o'z tashkilotlari:** ustoz sahifasi avval tizimdagi BARCHA darslarni yuklardi (markaz ustozi tibbiyot sinflarini ham ko'rardi). Endi faqat ustozning filiallari va dars beradigan guruhlari tashkilotlari (`journal/teacher_data.py`). Davomat holati API'si ham faqat o'z darslari bo'yicha.
- **«Sinflar»:** maktab va bog'chada — o'z filialining barcha sinflari jadvali; o'quv markazda — faqat o'z guruhlari, «Guruhlarim» ko'rinishida: har guruh qaysi kunlari, soat nechadan nechagacha («Du, Ch, Ju · 08:00–10:00»; ketma-ket darslar bitta oraliq bo'lib birlashadi). Faqat markazda ishlaydigan ustozda tab nomi «Guruhlar».
- **Bir nechta tashkilotda ishlasa:** «Bugun» va «Hafta»da darslar tashkilot bo'yicha alohida bloklarda (rangli nuqta bilan), «Hozir» kartasida tashkilot nomi, «Sinflar»da tashkilot tanlagichi; turli filialda bir xil nomli sinflar filial nomi bilan.
- **Taomnoma dars jadvali ichida** (ota-ona sahifasidagidek): tushlik va yengil tushlik «Bugun», «Hafta» va «Sinflar» ro'yxatlarida o'z soatida qisqa qator («Menyu»), bosilsa taomlar rasmi bilan batafsil oyna. Boshqa haftaga o'tilganda o'sha hafta taomnomasi yuklanadi (`/ustoz/api/taomnoma/`). Alohida taomnoma kartasi olib tashlandi.
- **Tashkilot tanlansa butun sahifa rangi o'zgaradi:** bir nechta tashkilotda ishlaydigan ustozda «Hammasi / Asosiy maktab / Markaz» tanlagichi («Bugun», «Hafta»), «Sinflar»dagi tanlov ham umumiy; tanlov eslab qolinadi; `theme-color` ham yangilanadi.
- **Ustoz rasmi** (terminal uchun olingan yuz rasmi) salomlashuv qatorida va profil tugmasida; rasm yuklanmagan bo'lsa bosh harflar.
- **Kun/tun tugmasi profil yonida** — barcha rollar: ota-ona, o'quvchi, ustoz (yuqori panel) va boshqaruv paneli (telefonda ham sarlavha yonida; avval faqat «Ko'proq» ichida edi). Profil tugmasida rasm bo'lsa — rasm.
- Ustoz sahifasidagi qattiq yashil rang tashkilot rangiga o'tkazildi.

## Tashqi zaxira: Telegram (2026-11-23)
- `spetion-tg-backup`: har kecha zaxira @spetion_robot orqali founder Telegramiga yuboriladi — ERP va exam bazalari har kuni, fayllar yakshanba to'liq / boshqa kunlari o'zgarganlari. GPG (AES-256) bilan shifrlangan, 45 MB lik qismlarga bo'linadi, hashtaglar bilan (`#zaxira #erp #d2026_11_23`). Shifrlash → bo'lish → birlashtirish → ochish → `pg_restore` sinovi o'tdi.
- Server ogohlantirishlari va 500 xatolar ham shu chatga keladi (droplet `.env` da `ALERT_BOT_TOKEN`, `ALERT_CHAT_ID`; asosiy `BOT_TOKEN` droplet'ga qo'yilmadi — med.spetion.uz bot webhook'iga tegmaslik uchun).
- Healthcheck: Telegram nusxasi 26 soatdan eski bo'lsa ogohlantiradi.

## Ishonchlilik va ko'p tashkilot kamchiliklari (2026-11-23)
- **Zaxira nusxa tuzatildi:** fayllar arxivi noto'g'ri papkani (`/var/www/erp/media`, bo'sh) olardi — taom/yuz rasmlari va cheklar zaxiraga tushmasdi. Endi `/var/www/erp/app/media` (+ exam storage). Har nusxa `pg_restore -l` bilan tekshiriladi; vaqt 02:30 Toshkent (21:30 UTC; avval 07:30 Toshkent — dars vaqtida edi). rclone'da `spetion-offsite` sozlansa, tashqariga ham nusxa ko'chiriladi.
- **Haftalik tiklash sinovi** (`spetion-restore-test`, yakshanba): oxirgi ERP nusxasi vaqtinchalik bazaga tiklanadi, o'quvchi/foydalanuvchi/to'lov sanaladi, natija `RESTORE_TEST` ga. Birinchi sinov: OK (24 o'quvchi, 35 foydalanuvchi, 57 to'lov).
- **Monitoring** (`spetion-healthcheck`, har 5 daqiqa): ERP va exam javobi, disk, xotira, zaxira yangiligi (26 soat), tiklash sinovi. Holat o'zgarganda (muammo / tuzaldi) Telegramga xabar; qisqa uzilishlar (yangilanishda qayta ishga tushish) ikki tekshiruvda takrorlansagina hisoblanadi. Sozlama: `/root/.spetion-alert` (`ALERT_BOT_TOKEN`, `ALERT_CHAT_ID`).
- **Xatolar jurnali va Telegram:** `LOGGING` sozlandi (journald), 500 xatolar Telegramga (`config/alerts.py`; bir xil xato 10 daqiqada bir marta, shaxsiy ma'lumotsiz). `.env`: `ALERT_CHAT_ID` (va ixtiyoriy `ALERT_BOT_TOKEN`).
- **Xavfsizlik sarlavhalari:** HSTS (30 kun, subdomenlarsiz), `Referrer-Policy: same-origin`.
- **Chiqish xabari vaqti tashkilot bo'yicha** (`Organization.leave_notify_from`; bo'sh bo'lsa umumiy). Panel «Qurilmalar»: ish maydonida tashkilot tanlangan bo'lsa — o'sha tashkilot vaqti. Holat («Tashqarida»/«Ketdi»), Telegram xabarlari va `send_leave_notices` shunga qaraydi.
- **Yuz rasmlari filial bo'yicha:** `tools/push_faces.py` qurilmaga faqat o'z filialining odamlarini yuboradi (`terminals.json` da `"branch"`); filialsiz qurilma uchun ogohlantirish.
- **Telegram xabarlarida tashkilot nomi** («✅ Madina 08:12 da keldi · Tibbiyot»); «maktabga» so'zi bog'cha/markaz uchun noto'g'ri edi.
- **PWA nomi umumiy** «Spetion», o'rnatilgan ilova rangi foydalanuvchining tashkilotidan. Panel shrifti sahifani to'smaydi.
- Deploy tekshiruvi to'g'ri Host bilan (`/login/` 200) va exam `health` ni kutadi.

## Audit 1-bosqichi (2026-11-23)
Loyiha auditidan keyingi tez tuzatishlar (hisobot: claude.ai artifact «Spetion ERP auditi»).
- **Telefonda ish maydoni** (Kritik): telefonda yon menyu yashirin bo'lgani uchun tashkilotni almashtirib bo'lmas edi. Endi sarlavha ostida rangli chip («● Hammasi ⌄») va «Ko'proq» ichida «Ish maydoni» bandi; bosilsa pastdan tashkilot/filiallar varag'i ochiladi.
- **Xavfsiz standartlar:** `DEBUG` faqat `manage.py runserver` da (yoki `DEBUG=1` aniq berilsa) yoqiladi; serverda (gunicorn) `SECRET_KEY` bo'lmasa ilova ishga tushmaydi.
- **Guruh nomi filial ichida noyob:** turli tashkilotda bir xil «7-A» bo'lishi mumkin (`uniq_group_name_per_branch`). Excel import, jadval importi, o'quvchini qayta tiklash va panel formasi filial bo'yicha ishlaydi.
- **Ustoz va xodim filiallari panelda:** ustoz va xodim kartasida «Ish filiallari» — belgilash/olib tashlash. Tahrirlovchi faqat o'z ruxsatidagi filiallarni o'zgartiradi, qolganlari tegilmaydi; kamida bitta filial; o'zini o'zi o'zgartira olmaydi; jurnalga yoziladi.
- Vaqtga bog'liq test (15:40 dan oldin yiqilardi) qat'iy vaqt bilan tuzatildi; exam reposidagi seed tuzatishi commit qilindi.

## 2026-11-22 (exam integratsiyasi)

## Ish maydoni (workspace) va tushunarli founder sahifasi (2026-11-22)
- **Ish maydoni tanlagichi** (panel chap menyusi): Hammasi / tashkilot / filial. Tanlov sessiyada saqlanadi va panelning HAMMA ro'yxati va hisobotiga o'zi qo'llanadi (`org/workspace.py`, `org/middleware.py`; `org.scope.branch_ids` tanlovni hisobga oladi). Panel tanlangan tashkilot rangiga bo'yaladi. Bitta filialga ruxsati bor xodimda tanlagich yo'q; ruxsatsiz tanlov 'Hammasi'ga qaytadi.
- **«Hammasi» rejimida ro'yxat o'rniga tashkilot kartalari** (`panel/hubs.py`): o'quvchilar, ustozlar, xodimlar, ota-onalar — har tashkilotda soni (markaz filiallari alohida); kartani bossangiz o'sha tashkilot ro'yxati ochiladi. Qidiruv (`?q=`) hamma tashkilot bo'yicha ishlaydi. Minglab yozuv bir sahifaga to'kilmaydi.
- **Founder sahifasi soddalashtirildi:** 4 raqam (o'quvchi, tushum, xarajat, foyda) har birining tagida «nima ekani» yozilgan; davr bitta tanlanadi (shu oy / o'quv yili); «to'lovlar holati» (kutilgan / kelgan / kelmagan); «Hammasi»da tashkilot kartalari, tashkilot tanlansa — filiallar jadvali; chegirma/grant tarkibi yig'ma blokda.
- **Hamma bo'lim «Hammasi»da tashkilot kartalari:** sinflar, dars jadvali, to'lovlar (shu oy tushumi), xarajatlar (shu oy), oyliklar (to'lanmagani), e'lonlar, qurilmalar ham.
- To'lovlar holati yorliqlari: kutilgan / to'langan / to'lanmagan. Telefonda «kutilgan tushum tarkibi» ochilganda sahifa kengayib ketishi tuzatildi.
- **Telefonda qisqa summalar:** katta raqamlar telefonda qisqa ko'rinadi (20 900 000 → 20.9 mln, 750 000 → 750 ming), kompyuterda to'liq; to'liq raqam bosib/ushlab turilganda ko'rinadi (`mny` filtri). Telefonda jadvaldan ikkinchi darajali ustunlar yashiriladi — gorizontal surilish yo'q.
- **Yuk sinovi (4000 o'quvchi):** `seed_scale` buyrug'i (~4000 o'quvchi, 3200 ota-ona, 220 ustoz, 12 000 hisob, 9000 to'lov) — faqat sinov bazasida. Ro'yxatlar 60–100 ms, founder sahifasi 80–270 ms, to'lovlar 270 ms, qarzdorlar 230 ms (SQLite, lokal). Tuzatildi: katta to'plam uchun `ensure_charges` natijasi 10 daqiqa eslab qolinadi, `summaries` o'quvchi obyektlarini yuklamaydi, qarzdorlar sahifasi faqat joriy sahifani yuklaydi (1000 ms → 230 ms), founder hisobotida ichki so'rovlar.
- Testlar: `panel/test_workspace.py`, `panel/test_owner.py`.

## Maktab egasi uchun «Raqamlar» sahifasi (2026-11-22)
- Founder (`is_owner`) `/panel/` ga kirganda yangi raqamli sahifa ochiladi (`panel/owner_stats.py`, `views_owner.py`, `templates/panel/owner.html`); eski kundalik panel `?kunlik=1` da qoladi, boshqa xodimlar uchun o'zgarmagan.
- **Foyda = kassaga tushgan tushum − xarajatlar** (oyliklar ham xarajat). Tepada 4 ta raqam: jami o'quvchi, tushum, xarajat, foyda (o'quv yili boshidan + shu oy).
- **Oylik reja:** kutilayotgan tushum (narx − chegirma; grant = 100% chegirma), kelgan pul, % yig'ilish, hali kelmagani, jami qarz, to'lanmagan oyliklar, prognoz foyda.
- Tashkilot va **filial** (markaz filiallari alohida) bo'yicha jadval; har tashkilot uchun kutilayotgan tushum tarkibi (masalan 300 × 2 000 000, 20 × 1 800 000 (−10%), 30 × 1 500 000 (−25%), grant); oylar bo'yicha tushum/xarajat/foyda/kutilgan grafigi; oy tanlash va tashkilot filtri.

## Ota-ona ilovasi: fikrlar asosida tuzatishlar (2026-11-22)

- **Rang tuzatildi (2026-11-22, keyingi):** `_glass.html` (liquid glass) tashkilot rangini qayta yashilga bo'yab yuborayotgan edi. Endi `org/theme.py` glass o'zgaruvchilarining hammasini (fon gradienti, shisha yuzalar, chiziqlar, soyalar, `--rgb`/`--glow`) bitta rangdan hisoblaydi, `org-theme` glassdan KEYIN ulanadi; yon menyu, hero, tugmalar, soyalar o'zgaruvchilarga o'tdi. Holat ranglari (Joyida, davomat %, qarz, baho) tashkilot rangiga bog'liq emas (`--ok`, `--bad`, `--late`). Sahifalar orasi `@view-transition` bilan 0.4 s yumshoq o'tadi; `<html data-org>` va `theme-color` har farzandda yangilanadi.
- **Imtihon bloki bo'shligi:** `.bar` sinfi glass'ning panel `.bar` qoidasi bilan to'qnashib, blok ustini yopib qo'ygan edi (`.xbar` ga o'zgartirildi); SVG atributlarida `var()` ishlamagani uchun chiziqlar ko'rinmasdi (`style=` ga o'tkazildi). Kun rejimida menyu matni ham tuzatildi.
- **Butun sahifa tashkilot rangida:** yuqori panel, pastki menyu faol tugmasi, hero va fon tashkilot rangidan hisoblanadi (oldin hero qattiq yashil edi). Qizil `#E53935` (ochroq), to'q sariq `#F97316` — endi bir-biriga yaqin emas.
- **Menyu jadvalga ko'chdi:** bosh sahifadagi menyu kartasi olib tashlandi; tushlik/poldnik dars jadvalida o'z soatida chiqadi, bosilsa taomlar rasmi bilan modal oyna. Ovqat soati panelda (Taomnoma sozlamalari) o'zgartiriladi (`MealType.at`, standart 12:30 / 15:30).
- **Bog'cha:** baho, imtihon, vazifa yo'q; «Dars jadvali» → «Mashg'ulotlar».
- **Tezlik:** imtihon dinamikasi sahifa bilan birga emas, alohida (`/oquvchi/<id>/imtihon/`) yuklanadi; Google Fonts ekranni to'smaydi; so'rovlar kamaydi. Server javobi ~0.3 s.
- **Imtihon dinamikasi:** chiziqli grafik (o'quvchi va sinf o'rtachasi, fan bo'yicha filtr, nuqtani bosib tafsilot), fanlar bo'yicha ko'rsatkich va o'zgarish, choraklar ustunli grafigi.
- **Exam (`exam-spetion`)**: `/api/v1/integration/students` va `/students/{id}/dynamics` (faqat o'qish, `X-Integration-Key` = `ERP_API_KEY`; kalit bo'sh bo'lsa 404; dinamikada sinf reytingi yo'q). Testlar: `test_integration.py`.
- **ERP `examlink` ilovasi**: `ExamLink` (ERP o'quvchi ↔ exam o'quvchi), `client.py` (5 s timeout, dinamika 10 daqiqa keshlanadi, exam ishlamasa sahifa buzilmaydi), `matching.py` (imlo variantlarini tenglaydi: o'/g', dj→j, x→h, q→k, so'zlar tartibi; ≥0.85, avval sinfi mos juftlar).
- **Panel «Sozlamalar → Exam bilan bog'lash»** (`org.settings` ruxsati): taklif qilingan juftlar, tasdiqlash, bog'lanishni uzish, juft topilmaganlar ro'yxati.
- **Ota-ona ilovasi**: «Baholar» sahifasida «Imtihonlar dinamikasi» (hozirgi %, yil boshidan o'zgarish, fanlar, choraklar).
- **Deploy to'plami** `deploy/droplet/`: `setup.sh` (yangi Ubuntu droplet: Postgres, nginx, systemd, swap, firewall, kunlik backup, secretlar), `push.sh <ip> [--first]` (ERP + exam kodini yuboradi, migratsiya), `MIGRATE_DATA.md` (eski serverdan ma'lumot ko'chirish). Hali hech qayerda ishga tushirilmagan.
- Sozlama: `EXAM_API_URL`, `EXAM_API_KEY`.
- Exam ko'p tashkilotli qilindi (maktab/markaz alohida sinflar bilan) — tafsilot exam `CHANGELOG.md`.

## 2026-11-21

### Qo'shildi
- **Taomnoma moduli** (`meals` ilovasi, Panel → Taomnoma). **Oshpaz platformaga kirmaydi**: menyuni va taom rasmlarini xodim (zavxoz, direktor, hisobchi... `meals.*` ruxsati bor odam) kiritadi. **Taom rasmi bir marta yuklanadi** va menyuning hamma kunlarida, har siklda qayta ishlatiladi (har kuni rasmga olish shart emas). Rasm 1000 px gacha kichraytirilib JPEG saqlanadi; ko'p rasmni bir yo'la yuklash mumkin (fayl nomi taom nomiga mos: `Osh.jpg`). «Non», «Choy» kabi bir xil taom bitta rasmni ulashadi (katta-kichik harfga qaralmaydi).
- **14 kunlik sikl** (uzunligi sozlanadi), ovqat turlari tashkilotda sozlanadi (standart: Tushlik va Ikkinchi tushlik/poldnik; bog'chada «Nonushta» qo'shiladi), «ko'zda tutilmagan» kunlar (6- va 14-kun poldnik). Sikl faqat ovqat beriladigan kunlar bo'yicha ketadi: dam olish va **ovqatsiz kunlar (bayram, ta'til)** da to'xtab turadi. Hafta kunlari o'zgarsa (dekabrdan shanba qo'shilsa) sikl hisobi uzilmaydi. Panelda «Bugun sikldagi nechanchi kun» ni qo'lda tuzatish mumkin. Tashkilot bo'yicha ajratilgan; modulni faqat «Maktab egasi» yoqadi (o'quv markazda o'chiq).
- **Ota-ona sahifasida «Bugungi menyu»:** farzandning tashkiloti menyusi, taom rasmlari bilan, «Farzandingiz bugun maktabda bo'ldi / hali kelmagan» izohi; bugun ovqat berilmasa (dam olish, ta'til) ertangi menyu ko'rsatiladi. Taom rasmini tizimga kirgan har bir foydalanuvchi ko'ra oladi (maxfiy emas).
- **`python manage.py seed_menu [--org "Nomi"] [--force]`** — founder bergan 14 kunlik maktab menyusini (taom nomlari) yuklaydi; menyusi bor tashkilotga tegmaydi. Rasmlardagi AI suratlari ota-onaga ko'rsatilmaydi. Ruxsatlar `meals.view/manage`: Zavxoz, Direktor va Maktab egasida bor; boshqalarga founder beradi. Migratsiya: `meals.0001`, `panel.0007`. Testlar: `meals/tests.py` (28 ta).
- **Xarajatlar moduli** (`finance` ilovasi, Panel → Moliya → Xarajatlar). Kategoriyalar (ijara, kommunal, oziq-ovqat, jihoz va ta'mirlash, reklama, soliq, transport, maosh, boshqa), sana, summa, kimga, to'lov usuli, izoh va chek rasmi (rasm faqat ruxsati va filiali bor xodimga ochiladi). Oy bo'yicha ko'rinish, filial va kategoriya filtri, kategoriya bo'yicha taqsimot va **kirim–chiqim–foyda** (kirim = o'quvchilarning shu oy haqiqiy to'lovlari). **Takroriy xarajatlar** (ijara, kommunal): oyda bir marta yoziladi — paneldagi «Shu oyga yozish» tugmasi yoki `python manage.py generate_recurring_expenses [--month YYYY-MM]` (oyning 1-kuni cron uchun). Tahrirlash/o'chirish jurnalga yoziladi. Filial bo'yicha ajratilgan.
- **Oyliklar moduli** (Panel → Moliya → Oyliklar). **Oylik qoidasi** xodimga kuchga kirish oyi bilan: qat'iy oylik yoki foiz (default 40%, ustozning o'quvchilari shu oy qilgan haqiqiy to'lovdan; bekor qilingan to'lov hisobga olinmaydi; guruhda bir nechta ustoz bo'lsa to'lov teng bo'linadi). Oylik o'zgarsa yangi qoida qo'shiladi, eski oylar o'zgarmaydi. Oy «Hisoblash» tugmasi bilan hisoblanadi (qayta bosish mukofot, ushlanma va to'lovlarga tegmaydi), mukofot/ushlanma qo'shiladi, avans va oylik to'lanadi. **To'langanda avtomatik «Maosh» xarajati yoziladi**, to'lov bekor qilinsa xarajat ham o'chadi. «Maosh» xarajati xarajatlar sahifasidan tahrirlanmaydi.
- **Yangi ruxsatlar:** `expenses.view/add/change/manage`, `payroll.view/manage`, `org.settings`. Xarajat va oyliklar **faqat «Hisobchi» va «Maktab egasi»da**; Direktorda va boshqa lavozimlarda yo'q. Founder xodimlar sahifasida kerakli odamga alohida beradi. Migratsiya: `panel.0006` (mavjud lavozimlarga ruxsatlarni qo'shadi; Direktorga `org.settings`), `finance.0001–0002`. Testlar: `finance/tests.py` (23 ta).
- **Tashkilot brendi (rang):** logo hamma tashkilotda bir xil, ilova va panelning fon/urg'u rangi tashkilotga qarab. Bitta HEX rangdan butun palitra (yorug' va qorong'i rejim, matn o'qilishi) o'zi hisoblanadi (`org/theme.py`, `org/context.py`). Ota-ona farzand sahifasini ochganda ilova rangi o'sha farzand tashkilotiga o'tadi (rang yumshoq almashadi); farzandlar ro'yxatida har kartada tashkilot rangi va nomi, farzandlar almashtirgichida tashkilot rangidagi nuqta; bitta telefon bilan turli tashkilotdagi farzandlar bitta ro'yxatda. Panel xodimning o'z tashkiloti rangida. Boshlang'ich ranglar: tibbiyot `#166534`, asosiy maktab `#1E3A8A`, o'quv markaz `#B91C1C`, bog'cha `#C2410C`.
- **Panel → Sozlamalar → «Tashkilot va brend»** (`org.settings` ruxsati): tashkilot nomi, qisqa nomi va rangi; founder va filial adminlari (Direktor) o'z tashkilotini o'zgartira oladi; taomnoma/xarajat modullarini yoqish-o'chirishni faqat «Maktab egasi». Noto'g'ri rang rad etiladi. Migratsiya: `org.0003`.
- **`python manage.py create_orgs`** — asosiy maktab, bog'cha va o'quv markaz tashkilotlarini (bo'lmasa) yaratadi; qayta ishga tushirish xavfsiz. Testlar: `org/test_theme.py` (18 ta).
- **Narx tashkilot bo'yicha, guruhda ixtiyoriy.** `BillingSettings` endi har tashkilotda bittadan (oylik narx, to'lov muddati, hisob boshlanish oyi, rekvizitlar); yangi tashkilotda narx 0 (hisob yozilmaydi, panelda ogohlantirish chiqadi). `Group.monthly_price`: guruhda o'z narxi bo'lsa shu qo'llanadi (o'quv markazda kursga qarab), bo'sh bo'lsa tashkilot narxi. Narx o'zgarsa faqat joriy oy hisobi yangilanadi (tashkilot yoki guruh bo'yicha), o'tgan oylar o'zgarmaydi. To'lov muddati va qarz hisobi o'quvchining o'z tashkiloti bo'yicha. Panel → To'lovlar → Sozlamalar'da tashkilot tanlagich (bir nechta tashkilotni ko'radigan xodimga); Sinflar → sinf formasida «Oylik narx». Migratsiyalar: `billing.0003–0004`, `academics.0005`. Testlar: `billing/test_multi_org.py` (11 ta).
- **Chegirmalar tashkilot bo'yicha:** `Discount.organization` (bo'sh = hamma tashkilotda); nom tashkilot ichida noyob; xodim faqat o'z tashkiloti chegirmalarini ko'radi va faqat o'quvchining tashkilotiga mos chegirmani biriktira oladi. Chegirma foizi guruh narxidan ham hisoblanadi. Hisobotlarda «chegirmalar» o'quvchining haqiqiy narxidan tejashni ko'rsatadi.
- **Ma'lumotlarni tashkilot/filial bo'yicha ajratish.** `Student.branch` (guruh tanlansa guruh filialiga o'zi tenglashadi), `User.branches` (ustoz va xodimlarning ish filiallari), `Announcement.branch`. Panelda xodim faqat o'z filiallari ma'lumotini ko'radi: o'quvchilar, sinflar, ustozlar, ota-onalar, dars jadvali, to'lovlar va qarzdorlar, hisobotlar, e'lonlar, qurilmalar, xodimlar, faoliyat jurnali, bosh sahifa raqamlari. «Maktab egasi» va superuser hamma filialni ko'radi. Boshqa filial yozuviga to'g'ridan-to'g'ri havola 404 beradi; chek 403. Filiali yo'q xodim hech narsa ko'rmaydi. Yangi yozuvlar (o'quvchi, sinf, qurilma, e'lon, ustoz, xodim) yaratuvchining filialiga tushadi. Yordamchilar: `org/scope.py`. Migratsiyalar: `accounts.0008–0009`, `notices.0005–0006`. Testlar: `org/test_isolation.py` (19 ta).
- **E'lonlar filial bo'yicha:** guruhsiz e'lon endi «shu filialning hammasiga» (avval butun tizimga); qabul qiluvchilar hisobi va ota-ona/ustoz/o'quvchi e'lon ro'yxati shunga moslandi. Ota-onaning farzandlari turli filialda bo'lsa, har ikkala filial e'lonlarini ko'radi.
- **Terminalga faqat o'z filiali odamlari yuboriladi** (`access.sync.eligible_users(device)`): o'quvchilar shu filialdan, ustoz va xodimlar shu filialda ishlaydiganlar. Bog'cha bolalari med maktab terminaliga tushmaydi.
- **`org` ilovasi (ko'p tashkilot asosi):** `Organization` (tur: maktab/bog'cha/o'quv markaz, brend rangi, taomnoma va xarajat modullari yoqilgani) va `Branch` (filial). `Group.branch` va `Device.branch`; mavjud guruh va terminallar migratsiyada «Tibbiyot maktabi / Asosiy» filialga bog'landi, yangi yozuvlar filial ko'rsatilmasa shunga tushadi. Migratsiyalar: `org.0001–0002`, `academics.0003–0004`, `access.0005–0006`. Testlar: `org/tests.py`.
- **`docs/qarorlar.md`** — kengayish bo'yicha qabul qilingan qarorlar va sabablari (bitta baza ko'p tashkilot, brend, ota-ona bitta hisob, xarajat/oylik, taomnoma, exam integratsiyasi, deploy).
- **`TODO.md`** — «Kengayish» reja bo'limi.

## 2026-11-20

### Qo'shildi
- **Yuz rasmlari terminallarga yuklandi.** Bosqichma-bosqich: avval 5, 7, 8, 9-sinflar (62 kishi) va direktor (Face ID 8001), keyin 6 va 10-sinflar (6-sinf 12, 10-sinf 16). Jami 4 ta Hikvision terminalda 91 kishi (90 o'quvchi + direktor), har birida yuz soni tekshirildi.
- **Xodimlar uchun yuz rasmi:** Panel → Xodimlar → xodim sahifasida rasm yuklash/o'chirish. Face ID 8001 dan avtomatik beriladi, xodimlar terminalga ham yuboriladi. Direktor (Umidjon Yusupov) rasmi VPS ga va terminallarga yuklandi.
- **Rasmli avatar:** panelda o'quvchilar, ustozlar, xodimlar, qarzdorlar, ota-onalar ro'yxatida va ota-ona ilovasida (farzand kartasi va sahifasi) bosh harflar o'rniga yuz rasmi. Ro'yxatlarda 96 px kichik nusxa ishlatiladi (diskda keshlanadi), shuning uchun sahifa og'irlashmaydi. Rasmni faqat shu farzandning ota-onasi ko'ra oladi.
- **O'quvchini maktabdan chiqarish / butunlay o'chirish.** Panel → O'quvchi sahifasi → «Maktabdan chiqarish»: o'quvchi sinf, ro'yxatlar, qarzdorlar, hisobotlar va ota-ona ilovasidan yo'qoladi, kirishi yopiladi, terminaldan olinadi; baho, davomat va to'lov tarixi saqlanadi. Ro'yxatda Holat → «Chiqqanlar (arxiv)» da ko'rinadi, u yerdan «Qaytarish» (oxirgi sinfiga) yoki «Butunlay o'chirish» (faqat chiqarilganlar uchun, tasdiq bilan; baho/davomat/to'lov ham o'chadi, ota-ona hisoblari qoladi). Migratsiya: `accounts.0007`.
- **Chiqish xabarlari vaqti (boshlang'ich 16:00), paneldan o'zgartiriladi:** Panel → Qurilmalar → «Chiqish xabarlari». Barcha skanlar saqlanadi. Ota-onaga «keldi» xabari kunning birinchi kirishida, «chiqdi» xabari esa faqat shu vaqtdan keyin va kuniga bittadan boradi (takroriy skan xabar bermaydi). Shu vaqtdan oldingi chiqish skani tanaffus: holat «Tashqarida · HH:MM dan» (ota-ona ilovasi, panel, bot), «Uyga ketdi» emas. Vaqt kelganda oxirgi skani «chiqish» bo'lgan o'quvchilarga xabarni `send_leave_notices` buyrug'i yuboradi. Migratsiya: `access.0004`.
- **`CHANGELOG.md`** yuritila boshlandi.
- **Hujjatlar (`docs/`):** `runbook.md` (server, joylash, zaxira, cron, bot), `terminallar.md` (terminallar, Face ID, rasm yuborish), `kirish-chiqish-qoidalari.md` (holat va xabar qoidalari, qarorlar). README da havolalar.
- **`tools/push_faces.py`** — terminallarga rasm yuborish skripti repoga ko'chirildi (avval vaqtinchalik papkada edi): terminalni MAC bo'yicha topadi (DHCP IP o'zgarsa ham), `test`/`sync`/`status` va `prune` (terminaldan ortiqchalarni ro'yxatlash, `--apply` bilan o'chirish) rejimlari; parol faqat `HIK_PASS` muhit o'zgaruvchisidan. `tools/terminals.json` — terminallar ro'yxati (MAC, IP). `access/hikvision.py` ga `list_users()` va `user_count()` qo'shildi.

### O'zgartirildi
- **Ota-ona boshlang'ich paroli = telefonning oxirgi 4 raqami** (ustozlardagi kabi, birinchi kirishda almashtirish shart). Avval panelda qo'shilgan ota-onaga tasodifiy bir martalik parol berilardi va telefonning oxirgi 4 raqami ishlamasdi. Endi ota-ona qo'shilganda, «Parolni tiklash» (ota-ona sahifasi va o'quvchi sahifasidagi ota-onalar jadvali) va `issue_parent_passwords` buyrug'i shu qoidaga o'tdi (buyruq CSV ustuni: «Boshlang'ich parol (oxirgi 4 raqam)»). Xodimlar (panelga kirish) va Telegram `/parol` oldingidek tasodifiy bir martalik parol beradi.

### Tuzatildi
- **Kirish/chiqish holati:** o'quvchi terminalni ketma-ket (kirish/chiqish) skan qilganda «Uyga ketdi» noto'g'ri chiqardi (oxirgi chiqishdan keyingi kirish hisobga olinmasdi). Endi oxirgi skan hal qiladi (ota-ona sahifasi, panel, Telegram bot).
- **Dars jadvali filtri:** ustoz tanlansa sinf tozalanadi (va aksincha), 5-sinfga qaytib ketmaydi.
- **Tungi rejimda `select` ro'yxati:** ochiladigan menyuning foni va matni ikkalasi ham och bo'lib o'qib bo'lmasdi. Panelga `color-scheme` va `option` ranglari qo'shildi.
- **Terminal bilan aloqa:** Hikvision 401 (eskirgan Digest nonce) bersa, yangi sessiya bilan qayta uriniladi (ko'p rasm yuborishda uzilib qolmasligi uchun).

### Texnik / sozlash
- **VPS:** barcha o'zgarishlar joylandi (migratsiyalar `accounts.0007`, `access.0004`). Zaxiralar: `data/db.sqlite3.before-student-left`, `data/db.sqlite3.before-leave-notice`.
- **Cron:** `/etc/cron.d/med-spetion-leave` — `send_leave_notices` har 5 daqiqada, Toshkent 12:00–21:00 (UTC 07–16), jurnal `/var/www/med-spetion/leave.log`.
- **Telegram bot** (@spetion_robot): webhook tekshirildi (`https://med.spetion.uz/tg/webhook/`, xatosiz), test xabarlar (keldi, chiqdi, baho) yetib keldi. Hozircha botga ulangan ota-ona yo'q (0 / 107); ota-onalar uchun ulanish e'lon matni tayyorlandi.
- **Terminal IP lari o'zgargan (DHCP):** .108, .109 (kirish), .110, .104 (chiqish). Routerda MAC bo'yicha qotirish tavsiya etiladi. Terminallarda vaqt NTP rejimida.
- **Kechikish o'lchovi:** terminal skanidan bazaga yozilishigacha 0.5–2.7 s (o'rtacha 1.6 s). Sahifalar avtomatik yangilanmaydi (serverga yuk uchun), xabar Telegram orqali boradi.
- **Ma'lum cheklov:** terminaldan chiqqan o'quvchini terminaldan olib tashlash hozircha avtomatik emas (VPS terminalga yeta olmaydi), maktab tarmog'idagi skript orqali qo'lda bajariladi.
