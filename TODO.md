# Qilinadigan ishlar

## Ustoz sahifasi: baho qo'yish

- [x] **Kelmagan o'quvchiga baho qo'yishni taqiqlash.** Hozir darsda "kelmagan" deb belgilangan o'quvchiga ham baho qo'yib bo'ladi. Buni interfeysda ham (tugmalar o'chirilgan bo'lsin), serverda ham (so'rov rad etilsin) taqiqlash kerak.
- [x] **Qo'yilgan bahoni bekor qilish.** Baho tugmasini qayta bosish bahoni olib tashlasin. Masalan: Aliyev Valiga 3 bosildi — baho qo'yildi; yana 3 bosilsa — baho bekor bo'ladi. (Boshqa baho bosilsa, baho o'sha bahoga almashadi.)

## Kengayish (2026-11-21, founder taqdimotidan keyin)

Qaror (yangilandi): **bitta tizim, bitta baza, ko'p tashkilot** (multi-tenant). Sabab: bitta ota-ona (bitta telefon) farzandlarini turli tashkilotdan (med maktab, asosiy maktab, bog'cha, markaz) bitta ilovada ko'radi. Tashkilot > Filial > Guruh. Brend: logo bir xil, fon rangi tashkilotga qarab (med: to'q yashil #166534, asosiy maktab: to'q ko'k, markaz: qizil, bog'cha: to'q sariq).

- [x] 1. `org` ilovasi: `Organization` (tur, brend rangi, modullar), `Branch`; `Group.branch`, `Device.branch`; mavjud yozuvlar «Tibbiyot maktabi / Asosiy»ga bog'landi
- [x] 2. Ma'lumotlarni filial bo'yicha ajratish (panel, e'lonlar, terminallar, hisobotlar) — `org/scope.py`, `org/test_isolation.py`
  - [ ] 2a. Hali global qolganlar: oylik narx/to'lov muddati/rekvizitlar (`BillingSettings`), chegirmalar, chiqish xabari vaqti (`AccessSettings`) — tashkilot bo'yicha bo'lishi kerak; guruh nomi hozircha tizimda noyob (filial ichida noyob qilish kerak)
  - [ ] 2b. Panelda ustoz va xodimning filiallarini tanlash/o'zgartirish oynasi (hozir yaratuvchining filialiga tushadi, boshqasini admin orqali)
  - [ ] 2c. `tools/push_faces.py` qurilma filialiga qarab yuborsin
- [ ] 3. Ota-ona ilovasi: farzandlar turli tashkilotdan bitta ro'yxatda, farzand almashganda ilova fon rangi o'zgaradi (tashkilot brendi), bitta telefon = bitta hisob (sinov: 3 farzand 3 tashkilotda)
- [ ] 4. Xarajatlar: kategoriya, takrorlanuvchi shablon, chek rasmi, kirim-chiqim-foyda hisoboti (ma'muriyat/buxgalter, tashkilot bo'yicha)
- [ ] 5. Oyliklar: qat'iy oylik (kuchga kirish sanasi bilan) yoki foiz (default 40%, ustozning o'quvchilari qilgan to'lovdan); to'langanda avtomatik xarajat
- [ ] 6. Taomnoma: 14 kunlik sikl (tushlik + poldnik, ba'zi kunlar poldnik yo'q), sikl o'quv kunlari bo'yicha (med: Du–Sha; asosiy maktab: dekabrdan Sha ham), oshpaz roli, haqiqiy rasm yuklash, ota-ona sahifasida «bugun nima yedi». Maktab menyusi founderdan olingan (2 ta rasm), bog'chaniki hali yo'q
- [ ] 7. Exam bilan integratsiya: SSO (ERP asosiy hisob), sinf/o'quvchi/ustozlarni ERP'dan olish, ota-ona ilovasida o'quvchi portfoliosi: imtihon natijalari dinamikasi
- [ ] 8. Deploy: 2 GB droplet (~$18), Postgres, med + exam ko'chiriladi, boshqa loyihalar eski VPS'da qoladi; haftalik backup
