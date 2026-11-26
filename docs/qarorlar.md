# Qabul qilingan qarorlar (kengayish)

Founder taqdimotidan keyin (2026-11-21) loyiha 4 turdagi tashkilotga kengaymoqda. Bu hujjatda qarorlar va sabablari yoziladi. Yangi qaror yuqoridan qo'shiladi.

## Tashkilotlar (qamrov)
| Tashkilot | O'quvchi | Izoh |
|---|---|---|
| Tibbiyot maktabi | 500+ (ikki maktab jami) | hozirgi loyiha, Du–Sha o'qiydi |
| Asosiy maktab | | dekabrdan shanba ham dars |
| Bog'cha | ~100 | 1–3 mahal ovqat |
| O'quv markaz | 3000+ | 4–5 filial, haftada 3 kun 2 soatdan yoki har kuni 2 soat; ovqat yo'q |

Markaz va bog'cha jarayonlari maktabnikiga deyarli bir xil: oylik to'lov, qarzdorlik, davomat, baho, ota-ona sahifasi, vazifalar, xabarnomalar.

## 1. Bitta tizim, bitta baza, ko'p tashkilot (2026-11-21)
- Tuzilma: **Tashkilot (`org.Organization`) → Filial (`org.Branch`) → Guruh**. Terminal (`Device`) ham filialga bog'lanadi.
- Alohida instance (har tashkilotga alohida deploy) rad etildi. **Sabab:** bitta ota-ona bitta telefon raqam bilan farzandlarini turli tashkilotdan bitta ilovada ko'rishi kerak; umumiy hisobot; 2 GB serverga bitta jarayon yengilroq.
- Xavf: ma'lumotlar ajratilishi kodda ta'minlanadi (boshqa tashkilot ma'lumotini ko'rmaslik). Bu alohida qadam (TODO 2).
- Mavjud ma'lumot migratsiyada «Tibbiyot maktabi / Asosiy» ga bog'langan; yangi guruh/terminal filial ko'rsatilmasa shunga tushadi (`org.models.default_branch`).
- Guruh nomi hozircha butun tizimda noyob (ko'p kod shunga tayanadi); tashkilot ichida noyob qilish TODO 2 da.

## 1a. Ma'lumotlarni ajratish qoidalari (2026-11-21)
- **Kim nimani ko'radi:** «Maktab egasi» (founder) va superuser — hamma filial. Boshqa xodim va ustoz — faqat `User.branches` dagi filiallar. Filiali yo'q xodim hech narsa ko'rmaydi (xavfsiz tomon). Ota-ona va o'quvchi panelga kirmaydi: ota-ona faqat o'z farzandlarini (turli tashkilotdan bo'lishi mumkin), o'quvchi o'zini ko'radi.
- **O'quvchi** o'z `branch` iga ega (sinfsiz o'quvchi ham tashkilotga bog'langan qoladi); guruh tanlansa guruh filialiga tenglashadi.
- **Boshqa filial yozuvi** havola orqali ham ochilmaydi (404; chek 403). Barcha `get_object_or_404` shu qoidadan o'tadi; testlar buni tekshiradi.
- **E'lon:** guruhsiz e'lon = shu filialning hammasi. Ota-ona farzandlari filiallari e'lonlarini ko'radi.
- **Terminal:** qurilmaga faqat shu qurilma filialining odamlari yuboriladi.
- **Ota-onalar ro'yxati:** xodim faqat o'z filialida farzandi bor (yoki hali farzandi biriktirilmagan) ota-onani ko'radi; ota-ona kartasida boshqa tashkilotdagi farzandlar yashiriladi.
- **Yangi yozuvlar** yaratuvchining filialiga tushadi. Yangi ustoz/xodim hisobi asosiy filialga biriktiriladi (signal), keyin aniqlashtiriladi.
- **Hali global:** oylik narx va to'lov sozlamalari, chegirmalar, chiqish xabari vaqti, guruh nomi noyobligi (TODO 2a).

## 1b. Narx va chegirmalar (2026-11-21)
- **Oylik narx tashkilot bo'yicha** (`BillingSettings` har tashkilotda bittadan), **guruhda ixtiyoriy o'zgartiriladi** (`Group.monthly_price`): bo'sh bo'lsa tashkilot narxi, to'lgan bo'lsa guruhniki. Maktab va bog'chada guruh narxi bo'sh qoladi, o'quv markazda kursga qarab to'ldiriladi. Rad etilgan: o'quvchi bo'yicha alohida narx (buning o'rniga chegirma tizimi).
- **Chegirmalar saqlanadi** va tashkilot bo'yicha ishlaydi (`Discount.organization`; bo'sh = hamma tashkilotda). Chegirma foizi guruh narxidan ham hisoblanadi; bir necha bo'lsa eng kattasi.
- Yangi tashkilotda narx 0 bo'ladi: narx kiritilmaguncha hisob yozilmaydi (xato summa chiqmasligi uchun). To'lov muddati va qarz hisobi o'quvchining o'z tashkiloti sozlamasi bo'yicha.
- Narx o'zgarsa faqat joriy oy hisobi yangilanadi; o'tgan oylar o'zgarmaydi (eski qoida saqlandi).

## 1c. Xarajat va oyliklar ruxsati (2026-11-21)
- **Faqat hisobchi (buxgalter) va founder** ko'radi va boshqaradi. Direktor, zam, reception, ustoz va ota-ona ko'rmaydi. Ruxsatlar alohida: `expenses.*` va `payroll.*`.
- **Founder xohlagan odamga alohida bera oladi:** Panel → Xodimlar → xodim sahifasida ruxsatlarni belgilaydi (mavjud ruxsat tizimi). Direktor lavozimida bu ruxsatlar boshidan yo'q.
- Hisobchi o'z filialidagi xarajat va oyliklarni ko'radi; founder hamma tashkilotni. Kirim = o'quvchilarning haqiqiy to'lovlari; chiqim = xarajatlar (oyliklar ham «Maosh» sifatida shu yerga tushadi); foyda = kirim − chiqim.
- **Oylik qoidasi:** maktab va bog'chada qat'iy, markazda foiz (default 40%, ustozning o'quvchilari shu oy qilgan haqiqiy to'lovdan). Kuchga kirish sanasi bilan saqlanadi. Guruhda bir nechta ustoz bo'lsa o'quvchi to'lovi ustozlar o'rtasida teng bo'linadi.
- Oylik to'lovi avtomatik «Maosh» xarajatini yaratadi (qo'lda ikki marta kiritilmaydi).

## 2. Brend
- Logo hamma tashkilotda bir xil; **ilova fon rangi** tashkilotga qarab: tibbiyot to'q yashil `#166534`, asosiy maktab to'q ko'k `#1E3A8A`, o'quv markaz qizil `#E53935`, bog'cha to'q sariq `#F97316` (2026-11-22: qizil ochroq, sariqdan ajralib turishi uchun o'zgartirildi) (boshlang'ich; tasdiqlandi 2026-11-21). Rang `Organization.brand_color` da; butun palitra (och/qorong'i rejim) shu bitta rangdan hisoblanadi.
- **Keyin o'zgartirish:** founder va filial adminlari panelda (Sozlamalar → Tashkilot va brend) o'z tashkilotining nomi va rangini o'zgartira oladi (`org.settings` ruxsati). Modullarni (taomnoma, xarajat) yoqish-o'chirish faqat «Maktab egasi»da.
- Ota-ona farzandni almashtirsa, ilova rangi o'sha farzand tashkilotiga o'tadi.

## 3. Ota-ona: bitta hisob
- Bitta telefon raqam = bitta ota-ona hisobi; farzandlari turli tashkilotda bo'lishi mumkin va hammasi bitta ilovada ko'rinadi (bitta raqam hammasiga berilgan).

## 4. Xarajatlar va oyliklar
- Xarajatlar moduli: kategoriya, takrorlanuvchi shablon, chek rasmi, kirim–chiqim–foyda hisoboti. Faqat ma'muriyat/buxgalter ko'radi.
- **Ustoz va xodimlar oyligi xarajatga kiradi.** Maktab va bog'chada oylik **qat'iy** (kelajakda o'zgarishi mumkin: summa «qaysi sanadan kuchga kiradi» bilan saqlanadi). O'quv markazda **foiz**: ustozning o'zi o'qitgan o'quvchilar **haqiqatda qilgan to'lovdan**; har bir ustozga alohida foiz, boshlang'ich **40%**. Oylik to'langanda avtomatik «Maosh» xarajati yoziladi.

## 5. Taomnoma
- Maktabda (va bog'chada) 1–3 mahal ovqat; **o'quv markazda yo'q** (`Organization.meals_enabled`).
- Maktab menyusi: **14 kunlik aylanma sikl**, ikki turi: tushlik va ikkinchi tushlik (poldnik); poldnik ba'zi kunlarda yo'q (6- va 14-kun). Sikl **o'quv kunlari** bo'yicha ketadi (tibbiyot: Du–Sha; asosiy maktab: dekabrdan Sha ham).
- Taom pishganda mas'ul (**oshpaz roli**) **haqiqiy taom rasmini** yuklaydi; ota-ona «bugun farzandim nima yedi» bo'limida rasmni ko'radi (founderning tayyor menyu rasmlari AI surat, ota-onaga ko'rsatilmaydi, faqat taom nomlari olinadi). Rejadan farq qilsa oshpaz haqiqiy nomni o'zgartiradi. Farzand kelmagan bo'lsa «bugun maktabda emas» deb chiqadi.
- Bog'cha menyusi founderdan hali olinmagan.
- **Yangilanish (2026-11-22): oshpaz platformaga kirmaydi.** Alohida «Oshpaz» roli va har kungi haqiqiy rasm yuklash rad etildi (oshpazlarning ishi ko'p). Menyuni va taom rasmlarini xodim (zavxoz, direktor, hisobchi... `meals.*`) bir marta kiritadi; **har taomning rasmi bir marta yuklanadi** va har siklda qayta ishlatiladi. Ota-onaga «Bugungi menyu» (reja + taom rasmlari) ko'rsatiladi; «bola nima yedi» emas, «bugun menyuda nima» — chunki har kuni tasdiqlanmaydi.
- Sikl faqat ovqat beriladigan kunlar bo'yicha ketadi; ovqatsiz kunlar (bayram, ta'til) panelda belgilanadi, sikl shu kunlarda to'xtaydi. Hafta kunlari o'zgarsa hisob bugundan qayta bog'lanadi (sikl uzilmaydi).

## 6. Exam loyihasi bilan integratsiya
- Exam (FastAPI + React) alohida tizim bo'lib qoladi; ERP u bilan SSO va server-server API orqali bog'lanadi (ERP asosiy hisob; sinf/o'quvchi/ustozlar ERP'dan olinadi).
- Ota-ona ilovasida o'quvchi portfoliosi: imtihon natijalari dinamikasi.

## 7. Deploy
- DigitalOcean droplet 2 GB / 2 CPU (~$18/oy), imtihon kunlari vaqtincha 4 GB ga ko'tariladi; diskni oshirmaymiz. Haftalik backup yoqiladi. Faqat med va exam eski VPS'dan ko'chiriladi, qolgan loyihalar joyida qoladi. **Deploy hozircha to'xtatilgan** (boshqa masalalar bor).
- 2 GB ga sig'dirish: swap 2 GB, Postgres kichik sozlama, 2+2 gunicorn worker, Docker'siz (systemd), MinIO o'rniga disk/DO Spaces, Celery 1 jarayon.

## 8. Yangilanish (2026-11-22): o'quvchilar, exam va server
- **O'quvchilar:** exam ro'yxati = eski yagona maktab. 1-noyabrdan tibbiyot yo'nalishi ajralgan (examdagi ~43 ta mos o'quvchi tibbiyotga), qolganlari **Asosiy maktab**ga biriktiriladi. Ikkala maktabda ham yo'q (chiqib ketgan) o'quvchilarni founder/admin o'zi o'chiradi. Imtihon natijalari bog'langan o'quvchini o'chirishdan oldin nofaol qilish tavsiya etiladi.
- **Exam hamma tashkilot uchun:** maktablar va o'quv markazlarda ham imtihon bo'ladi; natijalardan o'quvchi o'zlashtirishi dinamikasi shakllantiriladi (ma'lumot yig'iladi). Exam ko'p tashkilotli bo'ladi (maktab/tashkilot bo'yicha ajratish).
- **Server:** hozircha DigitalOcean'da yangi droplet olib ishga tushiriladi. Ota-ona va ustozlarga berishdan oldin (to'liq taqdimotdan keyin) founderning yakuniy serveriga (o'z serveri/boshqa hosting) ko'chiriladi. Shuning uchun deploy skripti ko'chiriladigan (bitta buyruq, `pg_dump` + media) bo'lishi kerak. Biometrik (yuz) ma'lumot lokalizatsiyasi bo'yicha huquqshunos xulosasi kerak.

## 9. Rollar va ruxsatlar (2026-11-23 — 2026-11-26, rollar bo'yicha sharhdan)
- **Founder hech kimga ko'rinmaydi:** quyi xodimlar ro'yxatida, jurnalda va xodim kartasida founder va uning ishlari ko'rsatilmaydi. Tashkilot va filial qo'shish — faqat founder.
- **Yangi filial avtomatik:** tashkilotning hamma filialini ko'radigan xodimlarga (markaz direktori, hisobchi) yangi filial o'zi qo'shiladi; bitta filialdagi xodim va ustozlarga qo'shilmaydi.
- **«Filial rahbari»** — o'z filialida kundalik boshqaruv. Narx, chegirma, to'lovni bekor qilish, xarajat/oylik, jurnal — markazda (founder). **Sabab:** narx markaz bo'yicha bir xil; to'lovni bekor qilish — o'g'rilik xavfi.
- **O'quv markazda guruhdan-guruhga o'tkazish — faqat filial rahbari** (`students.move`, 2026-11-26). Maktab va bog'chada sinf o'zgartirish oddiy tahrir.

## 10. Oylik (2026-11-23, yangilandi 2026-11-26)
- Oylik ustoz/xodim qo'shishda kiritiladi, kartada o'zgartiriladi («qaysi oydan» — eski oylar o'zgarmaydi).
- **Avans — summasi qo'lda** (hisobchi yoki rahbar yozadi), foiz bilan rejalanmaydi. Avans kuni tashkilot bo'yicha (standart 15), yakuniy hisob — oyning oxirgi kuni. Eslatma bosh sahifada.
- Ko'p filialda ishlovchi: foiz — har filialga, **qat'iy oylik — faqat birinchi filialga** (ikki marta hisoblanmasin). Tasdiqlangan.

## 11. Bog'cha galereyasi (2026-11-26)
- Albom (guruh, nom, sana) va rasmlar; **har rasmda kim borligi qo'lda belgilanadi**. Ota-ona faqat o'z farzandi belgilangan rasmni ko'radi; belgilanmagan rasm hech kimga ko'rinmaydi. Fayllar ochiq emas — ruxsat tekshiradigan view orqali.
- Yuklaydiganlar: tarbiyachi (ustoz ilovasidan, faqat o'z guruhi), «Fotograf» lavozimi (faqat galereya), direktor / filial rahbari.
- Belgilangach ota-onaga Telegram xabari — bir albom bo'yicha bolaga bitta xabar (spam bo'lmasin).
- **Video yo'q** — videolar serverni tez to'ldiradi (founder qarori). Rasmlar 1600 px gacha kichraytiriladi (~200–400 KB).

## 12. Domen va server (2026-11-26)
- **spetion.uz** — landing sahifa. **my.spetion.uz** — hamma tashkilot uchun yagona tizim (panel, ustoz va ota-ona ilovasi, Telegram Mini App). «kundalik.spetion.uz» rad etildi: davlat elektron kundaligi (kundalik.com) bilan adashtirish xavfi.
- **med.spetion.uz saqlanadi:** ota-ona va ustozlarga tarqatilgan. Ko'chirish kuni DNS yangi serverga o'tkaziladi va nginx 301 bilan my.spetion.uz ga (yo'li bilan) yo'naltiradi; foydalanuvchi bir marta qayta kiradi.
- Server: DigitalOcean droplet 46.101.207.23 — 2 CPU / 2 GB / 60 GB (2026-11-26 kattalashtirildi). Gunicorn 3 worker. Galereya yuklash yo'llarida nginx 400 MB / 300 s.
- med-new.spetion.uz — sinov manzili sifatida vaqtincha qoladi.
