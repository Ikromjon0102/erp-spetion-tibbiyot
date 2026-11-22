# Qilinadigan ishlar

## Ustoz sahifasi: baho qo'yish

- [x] **Kelmagan o'quvchiga baho qo'yishni taqiqlash.** Hozir darsda "kelmagan" deb belgilangan o'quvchiga ham baho qo'yib bo'ladi. Buni interfeysda ham (tugmalar o'chirilgan bo'lsin), serverda ham (so'rov rad etilsin) taqiqlash kerak.
- [x] **Qo'yilgan bahoni bekor qilish.** Baho tugmasini qayta bosish bahoni olib tashlasin. Masalan: Aliyev Valiga 3 bosildi — baho qo'yildi; yana 3 bosilsa — baho bekor bo'ladi. (Boshqa baho bosilsa, baho o'sha bahoga almashadi.)

## Kengayish (2026-11-21, founder taqdimotidan keyin)

Qaror (yangilandi): **bitta tizim, bitta baza, ko'p tashkilot** (multi-tenant). Sabab: bitta ota-ona (bitta telefon) farzandlarini turli tashkilotdan (med maktab, asosiy maktab, bog'cha, markaz) bitta ilovada ko'radi. Tashkilot > Filial > Guruh. Brend: logo bir xil, fon rangi tashkilotga qarab (med: to'q yashil #166534, asosiy maktab: to'q ko'k, markaz: qizil, bog'cha: to'q sariq).

- [x] 1. `org` ilovasi: `Organization` (tur, brend rangi, modullar), `Branch`; `Group.branch`, `Device.branch`; mavjud yozuvlar «Tibbiyot maktabi / Asosiy»ga bog'landi
- [x] 2. Ma'lumotlarni filial bo'yicha ajratish (panel, e'lonlar, terminallar, hisobotlar) — `org/scope.py`, `org/test_isolation.py`
  - [x] 2a-1. Narx, to'lov muddati, rekvizitlar va chegirmalar tashkilot bo'yicha; guruhda ixtiyoriy narx
  - [ ] 2a-2. Hali global: chiqish xabari vaqti (`AccessSettings`); guruh nomi tizimda noyob (filial ichida noyob qilish kerak); Telegram bot xabarlarida tashkilot nomi
  - [ ] 2b. Panelda ustoz va xodimning filiallarini tanlash/o'zgartirish oynasi (hozir yaratuvchining filialiga tushadi, boshqasini admin orqali)
  - [ ] 2c. `tools/push_faces.py` qurilma filialiga qarab yuborsin
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
- [ ] 8. Deploy: hozir yangi DO droplet (vaqtincha), ota-ona/ustozlarga berishdan oldin founderning yakuniy serveriga ko'chish (pg_dump + media); boshqa loyihalar eski VPS'da qoladi; haftalik backup
