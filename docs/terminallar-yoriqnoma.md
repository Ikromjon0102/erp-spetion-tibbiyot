# Terminallar: ko'chirish va yangi terminal ulash — yo'riqnoma

Kim uchun: maktabda Hikvision yuz terminallarini sozlaydigan xodim. Dasturchi bo'lish shart emas.
Bu hujjatda parol yo'q: terminalning `admin` paroli maktab ma'muriyatida saqlanadi.

Tizimning yangi manzili: **https://my.spetion.uz**. Eski manzil **med.spetion.uz** ham ishlashda davom etadi.

---

## A. Ko'chirish kuni: Tibbiyot maktabidagi 4 ta terminal

### Terminalda hech narsani o'zgartirish SHART EMAS
Terminallar skanlarni `med.spetion.uz` ga yuboradi. Ko'chirish kuni bu manzil yangi serverga ulanadi va terminal ma'lumoti
to'g'ridan-to'g'ri qabul qilinadi. Har bir terminalning maxfiy tokeni yangi serverga o'zgarishsiz ko'chiriladi.

### Faqat tekshirish kerak (10 daqiqa, ko'chirish tugagach)
Dasturchi «ko'chirish tugadi» deganidan keyin:

1. Har bir terminaldan (Kirish-1, Kirish-2, Chiqish-1, Chiqish-2) **bitta odam yuzini ko'rsatib o'tsin**. Yuzi terminalda bor ustoz
   yoki o'quvchi bo'lsin.
2. Telefonda yoki kompyuterda **https://my.spetion.uz/panel/** → **Qurilmalar** sahifasini oching:
   - har bir terminal yonida «Oxirgi signal» vaqti **hozirgi daqiqa** bo'lsin;
   - o'tgan odam **Kunlik nazorat**da «keldi» yoki «ketdi» bo'lib ko'rinsin.
3. Shu bolaning ota-onasiga Telegram'da «✅ … keldi» xabari borganini so'rang. Bu ixtiyoriy, xabar 1–3 soniyada keladi.
4. Natijani dasturchiga yozing: «4 ta terminal ishlayapti» yoki qaysi biri ishlamayotganini.

Biror terminal ishlamasa, pastdagi **«D. Muammo bo'lsa»** jadvaliga qarang.

---

## B. Keyinroq (ixtiyoriy): eski terminallarni yangi manzilga o'tkazish
`med.spetion.uz` uzoq vaqt ishlaydi, shuning uchun bu shoshilinch emas. Bir kun hamma terminal to'g'ridan-to'g'ri `my.spetion.uz` ga
yuborsin desak, har bir terminalda **faqat manzil (Host)** o'zgartiriladi. Token va boshqa sozlamalar o'sha-o'sha qoladi.
Qadamlar pastdagi **C** bo'limidagi kabi, faqat 4-qadamda token o'zgarmaydi.

---

## C. Yangi terminal ulash (Asosiy maktab, bog'cha, o'quv markaz va boshqalar)

### 1. Panelda qurilmani qo'shing (direktor yoki founder)
1. **my.spetion.uz/panel/** → **Qurilmalar** → **Qurilma qo'shish**.
2. Nomi (masalan «Kirish-1»), yo'nalishi (**kirish** yoki **chiqish**) va **filiali**ni tanlang. Filial to'g'ri bo'lishi shart:
   skanlar shu filial o'quvchilari bilan solishtiriladi.
   «Manzil» (terminal IP) va parol maydonlari faqat rasm yuborish uchun kerak, ularni keyin to'ldirsa ham bo'ladi.
3. Saqlang. So'ng ro'yxatda shu qurilmaning **«Sozlash»** tugmasini bosing. Formaning pastida terminalga yoziladigan
   **URL** chiqadi: `/api/access/hikvision/<token>/`. Uni nusxalang. Token har bir terminalga alohida beriladi. Boshqa terminalga
   bermang va chatga yozmang.

### 2. Terminalni tarmoqqa ulang
- Terminal maktab Wi-Fi yoki LAN'iga ulangan bo'lsin, internet bo'lsin.
- **Tavsiya:** routerda terminal MAC manzili bo'yicha **doimiy IP** bering (DHCP reservation). Aks holda IP o'zgarib turadi va
  rasm yuborish skripti terminalni qidirib topishga majbur bo'ladi.

### 3. Vaqtni sozlang
Kompyuter brauzerida terminal IP manzilini oching (masalan `http://192.168.68.108`) va `admin` bilan kiring.
- **Configuration → System → Time Settings** (yoki «Время»):
  - Time Zone: **(GMT+05:00) Tashkent**;
  - **NTP** yoqilgan, server `pool.ntp.org`.
- Vaqt noto'g'ri bo'lsa, o'quvchi «kech keldi» yoki «erta ketdi» bo'lib ko'rinadi.

### 4. Skanlarni serverga yuborishni sozlang (HTTP Listening)
**Configuration → Network → Advanced Settings → HTTP Listening.** Ba'zi versiyalarda bu «Event Alarm» yoki «Alarm Host»
ichida turadi. Menyu nomi dasturiy ta'minot versiyasiga qarab biroz farq qilishi mumkin.

| Maydon | Qiymat |
|---|---|
| Event Alarm IP / Domain (Host) | `my.spetion.uz` |
| Protocol | **HTTPS** |
| Port | **443** |
| URL | `/api/access/hikvision/<token>/` (1-qadamda nusxalangan) |
| Format / Data Type | **JSON** |
| Heartbeat | yoqilgan (30 soniya) |

**Save** bosing. Ba'zi terminallarda «Test» tugmasi bor: bosilsa, panelda «Oxirgi signal» yangilanadi.

### 5. Yuz rasmlarini terminalga yuklang
O'quvchi, ustoz va xodimlarning rasmi panelda yuklanadi. Rasm va Face ID avtomatik tayyorlanadi.
Terminalga yuborishni **binodagi kompyuterdagi Spetion agent** qiladi: server maktab ichki tarmog'iga yeta olmaydi.
Har binoda bir marta o'rnatiladi (panel → Qurilmalar → «Ulash kodi olish» va «Agentni yuklab olish»; qadamlar —
`tools/spetion_agent/README.md`). Shundan keyin yangi rasmlar bir daqiqa ichida o'zi yuboriladi; natija panelda «Qurilmalar»da.

### 6. Tekshiring
**A** bo'limidagi tekshiruv kabi: bitta odam o'tsin → panelda «Oxirgi signal» va «Kunlik nazorat».

---

## D. Muammo bo'lsa

| Belgi | Sabab | Nima qilish |
|---|---|---|
| Panelda «Oxirgi signal» eski (5 daqiqadan ko'p) | Terminalda internet yo'q yoki manzil xato | Terminaldan internet borligini tekshiring. HTTP Listening'da Host, Port 443, HTTPS va URL'ni qayta tekshiring |
| Signal bor, lekin odam «keldi» bo'lmayapti | Yuz terminalda yo'q yoki Face ID mos emas | Terminalda shu odam bormi? Agent oynasidagi «Terminalda» ustuni (yoki panel → Qurilmalar) |
| Odam boshqa filialda ko'rinyapti | Panelda qurilmaning filiali xato | Qurilmalar → qurilma → filialni to'g'rilang |
| Vaqt 5 soatga farq qiladi | Vaqt zonasi xato | 3-qadam: GMT+05:00 Tashkent va NTP |
| Bitta terminal ishlamayapti, qolganlari ishlayapti | Shu terminalning tokeni yoki URL'i xato | 1-qadamdagi manzilni qaytadan nusxalab yozing (bo'sh joy va oxiridagi `/` ham kerak) |
| Hech bir terminal ishlamayapti | Server yoki maktab internetida muammo | Dasturchiga yozing |

Terminal o'z xotirasida ham har bir skanni saqlaydi. Internet uzilib qolsa, yozuvlar yo'qolmaydi va keyin tiklash mumkin.
