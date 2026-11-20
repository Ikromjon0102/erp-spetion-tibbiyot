# O'zgarishlar tarixi

Yangi o'zgarishlar yuqoridan qo'shiladi.

## Joylanmagan

### Qo'shildi
- **Chiqish xabarlari vaqti (boshlang'ich 16:00), paneldan o'zgartiriladi:** Panel → Qurilmalar → «Chiqish xabarlari». Barcha skanlar saqlanadi. Ota-onaga «keldi» xabari kunning birinchi kirishida, «chiqdi» xabari esa faqat shu vaqtdan keyin va kuniga bittadan boradi (takroriy skan xabar bermaydi). Shu vaqtdan oldingi chiqish skani tanaffus: holat «Tashqarida · HH:MM dan» (ota-ona ilovasi, panel, bot), «Uyga ketdi» emas. Vaqt kelganda oxirgi skani «chiqish» bo'lgan o'quvchilarga xabarni `send_leave_notices` buyrug'i (cron, har 5 daqiqada) yuboradi. Migratsiya: `access.0004`.

## 2026-11-20 (kechqurun)

### Qo'shildi
- **O'quvchini maktabdan chiqarish / butunlay o'chirish.** Panel → O'quvchi sahifasi → «Maktabdan chiqarish»: o'quvchi sinf, ro'yxatlar, qarzdorlar, hisobotlar va ota-ona ilovasidan yo'qoladi, kirishi yopiladi, terminaldan olinadi; baho, davomat va to'lov tarixi saqlanadi. Ro'yxatda Holat → «Chiqqanlar (arxiv)» da ko'rinadi, u yerdan «Qaytarish» (oxirgi sinfiga) yoki «Butunlay o'chirish» (faqat chiqarilganlar uchun, tasdiq bilan; baho/davomat/to'lov ham o'chadi, ota-ona hisoblari qoladi). Migratsiya: `accounts.0007`.

## 2026-11-20

### Qo'shildi
- **6 va 10-sinf o'quvchilari terminallarga yuklandi** (6-sinf 12, 10-sinf 16): endi 4 ta terminalda jami 91 kishi (o'quvchilar 90 + direktor).
- **Yuz rasmlari terminallarga yuklandi:** 62 ta o'quvchi/ustoz (5, 7, 8, 9-sinflar) va direktor (Face ID 8001) — jami 63 kishi, 4 ta Hikvision terminalda.
- **Xodimlar uchun yuz rasmi:** Panel → Xodimlar → xodim sahifasida rasm yuklash/o'chirish. Face ID 8001 dan avtomatik beriladi, xodimlar terminalga ham yuboriladi.
- **Rasmli avatar:** panelda o'quvchilar, ustozlar, xodimlar, qarzdorlar, ota-onalar ro'yxatida va ota-ona ilovasida (farzand kartasi va sahifasi) bosh harflar o'rniga yuz rasmi. Ro'yxatlarda 96 px kichik nusxa ishlatiladi (diskda keshlanadi), shuning uchun sahifa og'irlashmaydi.

### Tuzatildi
- **Kirish/chiqish holati:** o'quvchi terminalni ketma-ket (kirish/chiqish) skan qilganda "Uyga ketdi" noto'g'ri chiqardi. Endi oxirgi skan hal qiladi (ota-ona sahifasi, panel, Telegram bot).
- **Dars jadvali filtri:** ustoz tanlansa sinf tozalanadi (va aksincha), 5-sinfga qaytib ketmaydi.
- **Tungi rejimda `select` ro'yxati:** ochiladigan menyuning foni va matni ikkalasi ham och bo'lib o'qib bo'lmasdi. Panelga `color-scheme` va `option` ranglari qo'shildi.
- **Terminal bilan aloqa:** Hikvision 401 (eskirgan Digest nonce) bersa, yangi sessiya bilan qayta uriniladi (ko'p rasm yuborishda uzilib qolmasligi uchun).

### Texnik
- Terminal IP lari o'zgargan (DHCP): .108, .109 (kirish), .110, .104 (chiqish). Routerda MAC bo'yicha qotirish tavsiya etiladi.
