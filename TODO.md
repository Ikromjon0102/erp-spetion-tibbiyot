# Qilinadigan ishlar

## Ustoz sahifasi: baho qo'yish

- [x] **Kelmagan o'quvchiga baho qo'yishni taqiqlash.** Hozir darsda "kelmagan" deb belgilangan o'quvchiga ham baho qo'yib bo'ladi. Buni interfeysda ham (tugmalar o'chirilgan bo'lsin), serverda ham (so'rov rad etilsin) taqiqlash kerak.
- [x] **Qo'yilgan bahoni bekor qilish.** Baho tugmasini qayta bosish bahoni olib tashlasin. Masalan: Aliyev Valiga 3 bosildi — baho qo'yildi; yana 3 bosilsa — baho bekor bo'ladi. (Boshqa baho bosilsa, baho o'sha bahoga almashadi.)

## Kengayish (2026-11-21, founder taqdimotidan keyin)

Qaror (yangilandi): **bitta tizim, bitta baza, ko'p tashkilot** (multi-tenant). Sabab: bitta ota-ona (bitta telefon) farzandlarini turli tashkilotdan (med maktab, asosiy maktab, bog'cha, markaz) bitta ilovada ko'radi. Tashkilot > Filial > Guruh. Brend: logo bir xil, fon rangi tashkilotga qarab (med: to'q yashil #166534, asosiy maktab: to'q ko'k, markaz: qizil, bog'cha: to'q sariq).

- [x] 1. `org` ilovasi: `Organization` (tur, brend rangi, modullar), `Branch`; `Group.branch`, `Device.branch`; mavjud yozuvlar «Tibbiyot maktabi / Asosiy»ga bog'landi
- [x] 2. Ma'lumotlarni filial bo'yicha ajratish (panel, e'lonlar, terminallar, hisobotlar) — `org/scope.py`, `org/test_isolation.py`
  - [x] 2a-1. Narx, to'lov muddati, rekvizitlar va chegirmalar tashkilot bo'yicha; guruhda ixtiyoriy narx
  - [x] 2a-2. (bajarildi 2026-11-23) Chiqish xabari vaqti tashkilot bo'yicha; Telegram xabarlarida tashkilot nomi; guruh nomi filial ichida noyob
  - [x] 2b. (bajarildi 2026-11-23) Panelda ustoz va xodimning filiallarini tanlash/o'zgartirish oynasi (hozir yaratuvchining filialiga tushadi, boshqasini admin orqali)
  - [x] 2c. (bajarildi 2026-11-23) `tools/push_faces.py` qurilma filialiga qarab yuboradi
- [x] 3. Ota-ona ilovasi: farzandlar turli tashkilotdan bitta ro'yxatda, farzand almashganda ilova rangi o'zgaradi; panelda «Tashkilot va brend» sozlamasi. Qolgan: telefon ilovasi (PWA) ikonka/manifest rangi hali bitta (yashil); `create_orgs` ni serverda ishga tushirish (deploy bilan)
- [x] 4. Xarajatlar: kategoriya, takroriy xarajat, chek rasmi, kirim-chiqim-foyda (faqat hisobchi va founder; `expenses.*`)
  - [ ] 4a. Keyin: kategoriyalarni panelda qo'shish/tahrirlash (hozir faqat admin orqali); xarajatlarni Excel'ga yuklash; takroriy xarajatlar uchun serverda cron
- [x] 5. Oyliklar: qat'iy oylik (kuchga kirish sanasi bilan) yoki foiz (default 40%); to'langanda avtomatik «Maosh» xarajati (`payroll.*`)
  - [ ] 5a. Keyin: oylik qaydnomasi (PDF/Excel), xodimga oylik xabari (Telegram), ustoz va xodim kartasida oylik qoidasi
- [x] 6. Taomnoma: 14 kunlik sikl, tushlik + poldnik, sikl ovqat beriladigan kunlar bo'yicha, taom rasmi bir marta yuklanadi (oshpaz platformaga kirmaydi), ota-ona sahifasida «Bugungi menyu»
  - [ ] 6a. Bog'cha menyusi founderdan hali olinmagan (1–3 mahal); serverda `create_orgs` va `seed_menu` ishga tushirish; keyin: menyuni Telegram orqali ota-onaga yuborish, allergiya/alohida ovqat belgisi, taom rasmlarini birinchi marta yuklash (xodim)
- [ ] 7. Exam bilan integratsiya: SSO (ERP asosiy hisob), sinf/o'quvchi/ustozlarni ERP'dan olish, ota-ona ilovasida o'quvchi portfoliosi: imtihon natijalari dinamikasi
- [x] 7. Exam integratsiyasi (o'qish API + bog'lash ekrani + ota-ona dinamikasi) — bajarildi 2026-11-22. Qolgan: qo'lda juftlash (taklif topmaganlar uchun), exam'ni ko'p tashkilotli qilish (7a), serverda `ERP_API_KEY`/`EXAM_API_*` sozlash
- [x] 7a. (asosi bajarildi 2026-11-22: exam'da maktab yaratish, sinf maktabga bog'lanadi; qolgan: ustoz/admin ko'rinishini maktab bo'yicha cheklash, ERP tashkiloti ↔ exam maktabi moslashtirish) Exam: ko'p tashkilotli (maktab/markaz), ERP o'quvchisi bilan bog'lash (sinf+ism, tasdiqlash ekrani), o'zlashtirish dinamikasi; chiqib ketganlarni founder o'zi o'chiradi
- [ ] 8. (tayyorlov bajarildi 2026-11-22: `deploy/droplet/` setup.sh, push.sh, MIGRATE_DATA.md; serverda hali ishga tushirilmagan, droplet kerak) Deploy: hozir yangi DO droplet (vaqtincha), ota-ona/ustozlarga berishdan oldin founderning yakuniy serveriga ko'chish (pg_dump + media); boshqa loyihalar eski VPS'da qoladi; haftalik backup

## Taqdimot takliflari (2026-11-26)

- [x] O'quv markazda guruhdan-guruhga o'tkazish — faqat filial rahbari (`students.move`)
- [x] Bog'cha galereyasi: ota-ona faqat o'z farzandi belgilangan rasmlarni ko'radi
- [x] Avans summasi qo'lda (foiz olib tashlandi); ko'p filialli ustozda qat'iy oylik birinchi filialga — tasdiqlandi
- [x] Galereya: tarbiyachi o'z telefonidan (ustoz ilovasidan) rasm yuklaydi
- [x] Galereya: yangi rasm belgilanganda ota-onaga Telegram xabari; «Fotograf» lavozimi
- [x] Galereya: video qilinmaydi (founder qarori — server diski)

## Ko'chirish (my.spetion.uz) — 2026-11-26

- [x] my.spetion.uz: DNS, SSL, hostlar, yangi SECRET_KEY, gunicorn 3 worker, galereya yuklash chegarasi
- [x] Terminal sozlovchi uchun yo'riqnoma (`docs/terminallar-yoriqnoma.md`); qurilmada filial tanlash
- [x] `tools/push_faces.py` — server API bilan (baza nusxasisiz), natija panelga qaytadi
- [x] Agent 1-bosqich (server): ulash kodi, filial kaliti, heartbeat va iz, panelda agentlar holati, `check_agents` ogohlantirishi
- [x] Agent 2-bosqich: Windows dasturi `SpetionAgent.exe` (fonda, tray, SADP qidiruv, biriktirish, avto-sync, DPAPI, o'zini yangilash)
- [ ] Agentni binoda sinash: Tibbiyot (4 terminal), keyin Asosiy maktab; so'ng bog'cha va markaz terminallari kelgach
- [ ] Founder javoblari: Excel (narx/chegirma, «Grand/Free/tibbiyot/bol-y/Yozda», sentabr–noyabr to'lovlari, kirill ismlar)
- [x] Mock ma'lumotlarni o'chirish (2026-11-28; zaxira `/var/backups/erp/erp-before-mock-wipe-20261128.dump`)
- [x] Asosiy maktab: 25 sinf, 420 o'quvchi, ota-onalar, 61 xodim (2026-11-28)
- [x] Asosiy maktab: oylik badal, chegirma, grant, Free, sentabr–noyabr to'lovlari (2026-11-28)
- [ ] Asosiy maktab: `korib_chiqish.txt` dagi 30 holat (badalsiz 20, bol-y/spravka 4, «Shoxsanam opa», «25-da», «100$», 200 000)
- [x] Asosiy maktab: dars jadvali (1000 dars, 2026-11-28); o'quvchi rasmlari Telegramdan 305 / 415, ustozlar 25 / 47
- [ ] Asosiy maktab: dushanba (30.11) 110 o'quvchi va 22 ustoz suratga olinadi (`datalar/asosiy maktab/rasmsizlar_dushanba.txt`); dushanba: Abdullayeva Xilola (Mental arifmetika, hisobi ochilgan, telefonsiz) telefoni; 8-Ingliz va 8-Med rus sinf rahbarlari
- [ ] Tibbiyot ko'chirilganda: «Ra'no Madaminova», «Yakubova Nigora» rasmlari (`datalar/asosiy maktab/ustozlar rasmi`)
- [ ] Asl ma'lumotlarni `datalar/` ga yig'ish va kiritish: Tibbiyot (eski serverdan), Asosiy maktab (Excel + terminaldagi 190 kishi/123 yuz), bog'cha, markaz
- [ ] Terminallarni panelga qayta qo'shish: Tibbiyot 4, Asosiy maktab 4 (192.168.1.190–193)
- [ ] **ISUP server** (`docs/isup-server.md`): founder ISUP SDK (Linux64) ni o'z hisobi bilan yuklab oladi → M0 faceURL sinovi (LAN) → M1 CMS + pass-through → M2 hodisalar → M3 Django (`Device.transport`, `RemoteClient`) → M4 terminallarni o'tkazish (Tibbiyot, keyin Asosiy maktab). Asosiy maktab: httpHosts 2-slotini hoziroq bizga yo'naltirish mumkin
- [ ] Exam platformasidagi sinov o'quvchilarini tozalash (ERP tomonidagi bog'lanishlar o'chirildi)
- [ ] Ko'chirish kuni: med.spetion.uz sertifikatini nusxalash → DNS → `nginx-med-legacy.conf`; ALLOWED_HOSTS ga med.spetion.uz; BOT_TOKEN va webhook; SITE_URL=my.spetion.uz; terminal tekshiruvi
