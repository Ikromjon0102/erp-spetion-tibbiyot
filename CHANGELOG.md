# O'zgarishlar tarixi

Yangi o'zgarishlar yuqoridan qo'shiladi.

## 2026-11-21

### Qo'shildi
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
