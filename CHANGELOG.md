# O'zgarishlar tarixi

Yangi o'zgarishlar yuqoridan qo'shiladi.

## 2026-11-20

### Qo'shildi
- **Yuz rasmlari terminallarga yuklandi.** Bosqichma-bosqich: avval 5, 7, 8, 9-sinflar (62 kishi) va direktor (Face ID 8001), keyin 6 va 10-sinflar (6-sinf 12, 10-sinf 16). Jami 4 ta Hikvision terminalda 91 kishi (90 o'quvchi + direktor), har birida yuz soni tekshirildi.
- **Xodimlar uchun yuz rasmi:** Panel → Xodimlar → xodim sahifasida rasm yuklash/o'chirish. Face ID 8001 dan avtomatik beriladi, xodimlar terminalga ham yuboriladi. Direktor (Umidjon Yusupov) rasmi VPS ga va terminallarga yuklandi.
- **Rasmli avatar:** panelda o'quvchilar, ustozlar, xodimlar, qarzdorlar, ota-onalar ro'yxatida va ota-ona ilovasida (farzand kartasi va sahifasi) bosh harflar o'rniga yuz rasmi. Ro'yxatlarda 96 px kichik nusxa ishlatiladi (diskda keshlanadi), shuning uchun sahifa og'irlashmaydi. Rasmni faqat shu farzandning ota-onasi ko'ra oladi.
- **O'quvchini maktabdan chiqarish / butunlay o'chirish.** Panel → O'quvchi sahifasi → «Maktabdan chiqarish»: o'quvchi sinf, ro'yxatlar, qarzdorlar, hisobotlar va ota-ona ilovasidan yo'qoladi, kirishi yopiladi, terminaldan olinadi; baho, davomat va to'lov tarixi saqlanadi. Ro'yxatda Holat → «Chiqqanlar (arxiv)» da ko'rinadi, u yerdan «Qaytarish» (oxirgi sinfiga) yoki «Butunlay o'chirish» (faqat chiqarilganlar uchun, tasdiq bilan; baho/davomat/to'lov ham o'chadi, ota-ona hisoblari qoladi). Migratsiya: `accounts.0007`.
- **Chiqish xabarlari vaqti (boshlang'ich 16:00), paneldan o'zgartiriladi:** Panel → Qurilmalar → «Chiqish xabarlari». Barcha skanlar saqlanadi. Ota-onaga «keldi» xabari kunning birinchi kirishida, «chiqdi» xabari esa faqat shu vaqtdan keyin va kuniga bittadan boradi (takroriy skan xabar bermaydi). Shu vaqtdan oldingi chiqish skani tanaffus: holat «Tashqarida · HH:MM dan» (ota-ona ilovasi, panel, bot), «Uyga ketdi» emas. Vaqt kelganda oxirgi skani «chiqish» bo'lgan o'quvchilarga xabarni `send_leave_notices` buyrug'i yuboradi. Migratsiya: `access.0004`.
- **`CHANGELOG.md`** yuritila boshlandi.

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
