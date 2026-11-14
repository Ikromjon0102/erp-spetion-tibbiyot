# Tibbiyot maktabi — boshqaruv tizimi (Django)

Rollar: **Ma'muriyat** (Django admin), **Ustoz** (dars jadvali, davomat, baholar), **Ota-ona** (farzandlari ta'limi,
maktabga kelish-ketish vaqti, to'lovlar), **O'quvchi** (o'z natijalari).

## Ishga tushirish
    pip install -r requirements.txt
    python manage.py migrate
    python manage.py createsuperuser          # ma'muriyat uchun (admin panel: /admin/)
    python manage.py runserver

## Dars jadvalini Excel'dan yuklash
    python manage.py import_schedule "Dars_Jadvali(Noyabr).xlsx"
- Sinflar, fanlar, ustozlar va darslar yaratiladi. Yangi ustozlarning login/parollari `teachers_credentials.csv` ga yoziladi
  (tarqatib bo'lgach faylni o'chiring).
- Keyingi oy uchun yangi fayl bilan qayta ishga tushirsangiz jadval **yangilanadi**: o'zgargan darslar almashadi,
  yo'qolganlari yashiriladi, davomat tarixi saqlanadi, ustozlarning parollari o'zgarmaydi.
- Jadvaldagi vaqt to'qnashuvlari (bir ustoz bir vaqtda ikki sinfda) ogohlantirish sifatida chiqadi.

## O'quvchilar ro'yxatini yuklash
    python manage.py import_students "10-sinf o'quvchilari ro'yxati.xlsx"
- Guruh nomi fayl nomidan olinadi (`10-sinf` -> `10-Sinf`), kerak bo'lsa `--group "9-Sinf"`.
- Kirill/lotin aralash harflar va turli apostroflar lotinga tenglashtiriladi.
- Telefon ota-onaniki: shu raqam bo'yicha ota-ona hisobi (login = raqam) yaratilib, o'quvchiga bog'lanadi. Bir raqamli aka-uka bitta ota-onaga bog'lanadi.
  Ota-ona parolini admin panelda "telefonning oxirgi 4 raqami" amali bilan o'rnating.
- Qayta ishga tushirsangiz takrorlanmaydi.

Namuna (mock) o'quvchilar: `python manage.py mock_students` — o'quvchisi yo'q sinflarga 10 tadan qo'shadi (login `namuna_...`);
`python manage.py mock_students --remove` ularni o'chiradi (haqiqiy o'quvchilarga tegmaydi).

## Boshqaruv paneli (`/panel/`)
Maktab xodimlari (direktor, zam, reception, hisobchi, zavxoz...) uchun kompyuterga mo'ljallangan panel; telefonda muhim narsalarni ko'rish
mumkin. Django admin (`/admin/`) endi faqat texnik administrator uchun (panel menyusida "Texnik admin" havolasi).
- **Bo'limlar:** Bosh sahifa (kelganlar, davomat olinmagan darslar, qurilmalar holati, qarzdorlar, oxirgi e'lonning o'qilishi),
  O'quvchilar (qidiruv, filtr, to'liq karta, ota-ona biriktirish, bir martalik parol, Excel'dan yuklash, CSV), Sinflar, E'lonlar
  (yuborish va kim o'qiganini ✓/✓✓ bilan ko'rish), Xodimlar, Lavozimlar, Faoliyat jurnali.
- **Ruxsatlar har bir xodimga alohida** belgilanadi (modul × amal + maxfiy ma'lumotlar: telefonlar, baholar, to'lovlar).
  Lavozim — yorliq va boshlang'ich namuna: tanlanganda belgilar oldindan qo'yiladi, keyin har birini o'zgartirish mumkin.
- **Xavfsizlik qoidalari:** o'z ruxsatlarini o'zi o'zgartira olmaydi; o'zida yo'q ruxsatni boshqaga bera olmaydi; "maktab egasi"ni
  faqat boshqa ega o'zgartiradi; oxirgi egani chetlatib bo'lmaydi. Har bir o'zgarish Faoliyat jurnaliga yoziladi (kim, nima, qachon).
- **Xodim qo'shish:** Xodimlar -> Xodim qo'shish (telefon = login). Yangi hisobga bir martalik parol beriladi (faqat bir marta
  ko'rsatiladi, birinchi kirishda almashtiriladi). Shu raqam bilan ustoz allaqachon bo'lsa, unga panel ruxsati qo'shiladi (paroli o'zgarmaydi).
- **Telefonda panel ilova ko'rinishida:** pastda tab paneli (Bosh, O'quvchilar, E'lonlar, Ko'proq), sahifaning asosiy amali suzuvchi "+" tugmasi (bosh sahifada yo'q — e'lon E'lonlar bo'limidan yuboriladi), "Ko'proq" bosilsa pastdan varaq (qolgan bo'limlar, rejimlar, parol, chiqish); jadvallar karta ko'rinishida. Tab paneli faqat ruxsat berilgan bo'limlarni ko'rsatadi.
- **Rejimlar:** ustoz / ota-ona / boshqaruv paneli — bitta hisob, menyudan (yuqori o'ngdagi harf) almashtiriladi.
- Texnik administrator (superuser) panelda hamma narsani ko'radi. Sinov hisobining namunaviy ma'lumotlari (`sinov_...`, `[Sinov]`) panelda ko'rinmaydi.


## Ustozlar, ota-onalar, dars jadvali va yuz rasmlari (panel)
- **Ustozlar / Ota-onalar:** ro'yxat (avtomatik qidiruv), karta, qo'shish, tahrirlash, parolni tiklash. Ota-ona kartasida farzand biriktirish/ajratish.
  Ustoz kartasida fan va sinf biriktirish. Ustoz boshlang'ich paroli — telefonning oxirgi 4 raqami; ota-onaga bir martalik parol beriladi.
- **Dars jadvali:** sinf yoki ustoz bo'yicha haftalik jadval; dars qo'shish/o'zgartirish (sinf va ustoz vaqti to'qnashsa rad etiladi).
  Olib tashlangan dars o'chmaydi, faqat jadvaldan yashirinadi (davomat va baho tarixi saqlanadi).
- **Yuz rasmlari (Hikvision):** o'quvchi va ustoz kartasidan rasm yuklanadi (JPG/PNG -> avtomatik ~200 KB gacha JPEG). Qurilmada odam **Face ID** bilan
  tanishadi (o'quvchida — kartadagi Face ID, ustozda — rasm yuklanganda 7001 dan beriladi yoki qo'lda yoziladi). Ko'p rasm: panel -> Qurilmalar -> ZIP
  (fayl nomi = Face ID, masalan `1001.jpg`).
- **Qurilmalarga yuborish (sync):** panel -> Qurilmalar -> "Sozlash"da qurilma IP, port, login va parolini kiriting; "Tekshirish" ulanishni sinaydi.
  Rasm yuklanganda server qurilmalarga ISAPI orqali o'zi yuboradi; faqat o'zgarganlari yuboriladi, rasmi o'chirilgan yoki nofaol odamlar qurilmadan ham olib tashlanadi.
  Qo'lda: "Sync" tugmasi yoki `python manage.py sync_faces` (cron bilan davriy). **Server qurilmalar bilan bir tarmoqda (yoki VPN) bo'lishi kerak.**
- Rasmlar `media/` papkasida saqlanadi (ommaga ochiq emas, faqat ruxsatli ko'rinish orqali beriladi). Qurilma parollari bazada saqlanadi — bazani himoyalang.
- ISAPI yo'llari qurilma modeliga qarab farq qilishi mumkin; haqiqiy qurilmada birinchi marta "Tekshirish" va bitta rasm bilan sinab ko'ring.

## To'lovlar (moliya) — panel: `To'lovlar`
- **Sozlamalar:** bitta oylik narx (hamma sinf uchun), to'lov muddati (oyning X-kunigacha), hisob boshlanadigan oy. O'quv yili **sentabr–iyun (10 oy)**.
  Har oy uchun o'quvchiga hisob yoziladi (`narx − chegirma`); narx o'zgarsa faqat joriy oy yangilanadi, o'tgan oylar o'zgarmaydi.
- **Chegirmalar katalogi:** nomi + foiz (masalan, "2+ farzand", "Xodim farzandi", boshqalar). Standart holatda hech kimda chegirma yo'q;
  o'quvchi kartasidagi "To'lov" yorlig'ida qo'lda biriktiriladi (ixtiyoriy davr va sabab bilan). Bir nechta bo'lsa **eng kattasi** qo'llanadi (qo'shilmaydi).
- **To'lov qabul qilish:** summa, usul (naqd / to'lov tizimi / plastik karta / bank o'tkazmasi), sana, izoh. Qisman to'lov mumkin; to'lovlar eng eski oydan
  boshlab taqsimlanadi, ortiqcha summa (avans) keyingi oylar hisobiga o'tadi. Har to'lovga chek raqami beriladi (`CH2611-00042`), chek sahifasi chop etiladi/PDF.
- **Muddati o'tgan** qarz alohida ko'rsatiladi (jarima yo'q). To'lovni bekor qilish (sabab bilan) — yozuv o'chmaydi, hisobga olinmaydi.
- **Hisobotlar (Excel va PDF):** qarzdorlar, tushum/kunlik kassa (davr bo'yicha, usul kesimida), sinflar bo'yicha hisob, chegirmalar ro'yxati.
- **Ota-ona:** qarz/avans, muddati o'tgan summa, oylar bo'yicha holat, chegirma izohi, to'lovlar tarixi va har bir chek.
- **Ruxsatlar:** `payments.view / accept / discounts / settings / reports / void` (Direktor — hammasi, Reception — ko'rish va qabul qilish, Hisobchi — ko'rish va hisobotlar).
- PDF uchun `reportlab` kerak (`pip install -r requirements.txt`); kirill/o' harflari uchun tizim shrifti (Arial yoki DejaVu) ishlatiladi.
- Hozirgi to'lov ma'lumotlari sinov; haqiqiy ma'lumotlar ishga tushgandan keyin kiritiladi.

## Kirish (ustoz, ota-ona, o'quvchi)
**Login — telefon raqam** (istalgan formatda: `+998 94 604-80-62`, `94-604-80-62`, `946048062`), admin va eski loginlar (`diyora`) ham ishlayveradi.
- **Ustozlar:** admin panel -> Foydalanuvchilar -> telefon raqamlarni ro'yxatning o'zida kiriting -> ustozlarni belgilab
  "Ustozlar: parolni telefonning oxirgi 4 raqamiga o'rnatish". Boshlang'ich parol — oxirgi 4 raqam; **birinchi kirishdan keyin
  yangi parol qo'yish majburiy**.
- **Ota-onalar:** `python manage.py issue_parent_passwords` (bir martalik parol, birinchi kirishda almashtiriladi) yoki
  admin panelda "Bir martalik parol berish".
- 5 ta xato urinishdan keyin 10 daqiqa blok (`python manage.py unlock_logins`). Kirgach 30 kun tizimda qoladi.

### Ustoz ham ota-ona bo'lsa
Bitta hisob, bitta login. Ustozning telefon raqami ota-ona hisobidagi raqam bilan bir xil bo'lsa, hisoblar **avtomatik
birlashadi** (farzandlar ustoz hisobiga o'tadi). `import_students` ham shu raqamli ustozni topib, yangi hisob ochmaydi.
Qo'lda ham bo'ladi: o'quvchi sahifasida "Ota-onalari" ro'yxatiga ustozni qo'shing.
- Kirgach ustoz sahifasi ochiladi; yuqoridagi menyudan **Ustoz sahifasi / Farzandlarim** almashtiriladi (oxirgi rejim eslab qolinadi).
- Ustoz sahifasining tepasida farzandlarning bugungi holati ko'rinadi (● Maktabda / Ketdi / Kelmagan), bosilsa farzand sahifasi ochiladi.
- Farzandining to'lovi va e'lonlari faqat ota-ona rejimida; ustozlik e'lonlari esa ustoz sahifasida.

## Ustoz sahifasi (`/ustoz/`)
Telefon uchun ilova ko'rinishida. Kirgach darrov **bugungi** holat ko'rinadi.
- **Bugun:** hozirgi (yoki keyingi) dars katta kartada, "Davomat olish" va "Baho" tugmalari bilan. Davomat olinmagan darslar
  sariq "Olinmagan" belgisi bilan ko'rinadi. Darslar orasidagi bo'sh vaqt bitta qatorga yig'iladi.
- **Davomat:** hamma "Keldi" deb boshlanadi; kelmagan o'quvchini bosish kifoya (Kech/Sababli — shu qatorning ichida).
  Pastdagi tugma "Hammasi keldi — saqlash" yoki "Saqlash · 2 ta yo'q" bo'ladi: hamma kelgan bo'lsa, bitta bosish yetadi.
- **Baho:** o'quvchini bosing -> baho tugmasini bosing (shu zahoti saqlanadi, keyingi o'quvchi o'zi ochiladi). 4 soniya ichida "Bekor qilish" mumkin.
- **Hafta / Sinflar:** o'z haftalik jadvali va istalgan sinf jadvali. **E'lonlar:** yangi e'lon bo'lsa qo'ng'iroqda qizil nuqta.
- **Davomat ham, baho ham** faqat dars kuni va dars boshlangach qo'yiladi (o'tgan va kelgusi haftalarda faqat ko'rish). Bir darsga bitta baho: qayta qo'yilsa almashadi. Yakshanba kuni Hafta bo'limi keyingi haftani ko'rsatadi.
- O'quvchilar ro'yxati admin panelda yoki `import_students` bilan kiritiladi.

## Uy vazifasi (matn)
**Ustoz:** dars varag'ini oching (bosh sahifadagi "Davomat olish" yoki dars qatori) -> **Vazifa** bo'limi: matn va topshirish
sanasini yozib "Yuborish". Topshirish sanasi avtomatik taklif qilinadi — shu fanning jadvaldagi keyingi dars kuni (o'zgartirsa bo'ladi).
- Vazifani istalgan vaqtda berish mumkin (dars kuni bo'lishi shart emas).
- Tahrirlash va o'chirish faqat **berilgan kunning oxirigacha**; ertasi kuni o'zgarmaydi (ma'muriyat admin panelda o'zgartira oladi).
- Admin panel -> Vazifalar: sinf, fan, ustoz va sana bo'yicha filtr.

**Ota-ona:** farzand sahifasida vazifasi bor fanlar jadvalda (Bosh va Jadval) **Vazifa** belgisi bilan chiqadi. Fan qatori bosilsa, shu
fandan berilgan vazifalar ochiladi (topshirish sanasi, ustoz, matn). O'qilmagan vazifa **qizil nuqta** bilan ko'rinadi (fan qatorida
va "Jadval" tabida); ochilgach nuqta yo'qoladi. Hozircha faqat ko'rish (bajarildi belgisi, rasm/fayl keyingi bosqichlarda).

## E'lonlar va o'qilganlik (✓ / ✓✓)
Ma'muriyat e'lonni admin panelda yozadi (kimlar uchun va ixtiyoriy guruh). Ustoz va ota-onada e'lon **sarlavha** ko'rinishida
chiqadi, bosilsa matni ochiladi. Ochilgan zahoti u **o'qildi** deb belgilanadi (birinchi o'qilgan vaqt saqlanadi).
- O'qilmagan e'lonlar qizil nuqta bilan ko'rinadi (ro'yxatda, qo'ng'iroqda, ustoz sahifasida E'lonlar tabida).
- Admin panel -> E'lonlar: ro'yxatda **O'qilgan** ustuni (`✓✓ 5/12` — hammasi o'qigan, `✓ 3/12` — hali hammasi emas).
  E'lonni ochsangiz pastda **Kim o'qidi** jadvali: ✓✓ o'qigan (sana va vaqti bilan), ✓ yuborilgan, hali ochmagan.
- Qabul qiluvchilar: e'lon yo'naltirilgan, kira oladigan (paroli bor) foydalanuvchilar; admin va hali kirmagan (parolsiz)
  hisoblar sanalmaydi. Ham ustoz, ham ota-ona bo'lgan hisob bir marta sanaladi. Ma'muriyatning o'zi ochgani sanalmaydi.

## Hikvision yuz tanish (kirish/chiqish)
Har bir qurilma (2 kirish + 2 chiqish) admin panelda **Qurilmalar** bo'limida alohida yoziladi; kirish/chiqish yo'nalishi
qurilmaning o'zidan olinadi. Har qurilmaning maxfiy manzili (`/api/access/hikvision/<token>/`) o'sha bo'limda ko'rinadi.

Qurilma veb-sozlamalarida: **Configuration → Network → Advanced → HTTP Listening** (yoki *Event Notification*):
- Event Alarm IP / Domain: server manzili (IP yoki domen)
- URL: qurilma uchun ko'rsatilgan `/api/access/hikvision/<token>/`
- Port: serverning porti (masalan 8000), Protocol: HTTP

O'quvchini bog'lash: qurilmada o'quvchi uchun kiritilgan **Employee ID** ni admin panelda o'quvchining *Face ID* maydoniga yozing.
ID keyinroq kiritilsa ham, oldin kelgan hodisalar avtomatik bog'lanadi. Ota-ona sahifasida kunlik **kelgan** (birinchi kirish)
va **ketgan** (oxirgi chiqish) vaqt ko'rinadi. Qurilmaning "Oxirgi signal" vaqti ulanishni tekshirishga yordam beradi.

## PostgreSQL
`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` muhit o'zgaruvchilarini bering (`.env.example`). Berilmasa SQLite.

## Testlar
    python manage.py test
