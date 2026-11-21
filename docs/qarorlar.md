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

## 2. Brend
- Logo hamma tashkilotda bir xil; **ilova fon rangi** tashkilotga qarab: tibbiyot to'q yashil `#166534`, asosiy maktab to'q ko'k, o'quv markaz qizil, bog'cha to'q sariq. Rang `Organization.brand_color` da.
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

## 6. Exam loyihasi bilan integratsiya
- Exam (FastAPI + React) alohida tizim bo'lib qoladi; ERP u bilan SSO va server-server API orqali bog'lanadi (ERP asosiy hisob; sinf/o'quvchi/ustozlar ERP'dan olinadi).
- Ota-ona ilovasida o'quvchi portfoliosi: imtihon natijalari dinamikasi.

## 7. Deploy
- DigitalOcean droplet 2 GB / 2 CPU (~$18/oy), imtihon kunlari vaqtincha 4 GB ga ko'tariladi; diskni oshirmaymiz. Haftalik backup yoqiladi. Faqat med va exam eski VPS'dan ko'chiriladi, qolgan loyihalar joyida qoladi. **Deploy hozircha to'xtatilgan** (boshqa masalalar bor).
- 2 GB ga sig'dirish: swap 2 GB, Postgres kichik sozlama, 2+2 gunicorn worker, Docker'siz (systemd), MinIO o'rniga disk/DO Spaces, Celery 1 jarayon.
