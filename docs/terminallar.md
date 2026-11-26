# Terminallar (Hikvision yuz tanish)

Bu hujjatda parol yo'q. Terminallarning `admin` paroli (4 tasida bir xil) maktab ma'muriyatida saqlanadi; skriptlar uni faqat `HIK_PASS` muhit o'zgaruvchisidan oladi.

## Qurilmalar

4 ta **Hikvision DS-K1T343EFWX** (dasturiy ta'minot V4.48.0), maktab Wi-Fi tarmog'ida (`192.168.68.0/24`), login `admin`. Vaqt: **NTP**, zona Toshkent (`CST-5:00:00`).

| Nomi | Yo'nalish | MAC | IP (2026-11-20) |
|---|---|---|---|
| Kirish-1 | kirish | `88:de:39:8e:19:83` | 192.168.68.108 |
| Kirish-2 | kirish | `88:de:39:8e:19:50` | 192.168.68.109 |
| Chiqish-1 | chiqish | `88:de:39:8e:19:8d` | 192.168.68.110 |
| Chiqish-2 | chiqish | `88:de:39:8e:19:81` | 192.168.68.104 |

- **IP lar DHCP** (dinamik): router ularni o'zgartirib turadi. Eng yaxshisi routerda MAC bo'yicha qotirish (DHCP reservation) — hali qilinmagan.
  Shu vaqtgacha skript terminalni **MAC bo'yicha** topadi (`tools/terminals.json`; IP o'zgargan bo'lsa ogohlantiradi, faylni yangilang).
- **Yo'nalish** terminalning o'zidan aniqlanadi: har bir terminal o'z tokeniga yuboradi, token → `Device.direction`.

## Ikki yo'nalishli aloqa

```
 Terminal ──(1) HTTPS push: har skan──▶ VPS  /api/access/hikvision/<token>/  → AccessEvent (baza)
 Maktab kompyuteri ──(2) ISAPI (lokal tarmoq): rasm/foydalanuvchi yuborish──▶ Terminal
```

1. **Voqealar (terminal → server).** Terminalda *HTTP Listening* sozlangan: host `med.spetion.uz`, port 443, HTTPS, JSON, `/api/access/hikvision/<token>/`
   (token — Panel → Qurilmalar dagi har bir qurilmaning maxfiy tokeni; har terminalniki alohida). Terminal har skanni darhol yuboradi, heartbeat har 30 soniyada.
   Server `occurred_at` ni terminal soatidan oladi, `(qurilma, Face ID, vaqt)` bo'yicha takrorlanmaydi. O'lchangan kechikish: **0.5–2.7 s** (o'rtacha 1.6 s).
   Terminal xotirasidagi eski jurnal qayta yuborilsa, `ACCESS_IGNORE_EVENTS_BEFORE` dan eskilari tashlab yuboriladi.
2. **Rasmlar (kompyuter → terminal).** VPS maktabning ichki tarmog'iga yeta olmaydi, shuning uchun rasmlar **maktab tarmog'idagi kompyuterdan**
   `tools/push_faces.py` bilan yuboriladi (VPS bazasining nusxasi va rasmlari asosida).

## Face ID (Employee ID) qoidalari

| Kim | Diapazon | Qayerda |
|---|---|---|
| O'quvchi | 9001 dan | o'quvchi kartasi (`Student.access_id`) |
| Ustoz | 7001 dan | ustoz sahifasi (`User.access_id`) |
| Xodim (direktor va b.) | 8001 dan | xodim sahifasi (`User.access_id`) |

Raqam har doim diapazondagi eng kattasidan keyingisi (bo'shab qolgan raqamlar qayta berilmaydi), shuning uchun terminalda qolgan eski odam bilan adashib ketmaydi.
Rasm yuklanganda Face ID bo'sh bo'lsa, avtomatik beriladi.

## Rasm talablari

Rasm yuklanganda `accounts/photos.py` uni avtomatik tayyorlaydi: **JPEG, RGB, ≤ 200 KB, katta tomoni ≤ 1024 px, kichik tomoni ≥ 200 px**. Qo'shimcha moslashtirish kerak emas.
Rasmda yuz aniq (old tomondan) bo'lmasa, terminal rad etadi; bunday odam skript natijasida «xato» sifatida ko'rinadi, boshqa rasm bilan qayta urinish mumkin.
Faqat **rasmi va Face ID si bor faol** o'quvchi/ustoz/xodim yuboriladi (`access/sync.py: eligible_users`).

## Rasmlarni terminallarga yuborish (qadamlar) — my.spetion.uz

Server maktabning ichki tarmog'iga yeta olmaydi, shuning uchun rasmlarni **maktab tarmog'idagi kompyuter** yuboradi:
`tools/push_faces.py` serverdan API orqali «shu terminalda kim bo'lishi kerak» ro'yxati va rasmlarni oladi, terminallarga yuboradi
va natijani serverga qaytaradi (panel → Qurilmalar: «hammasi yuborilgan / N ta xato» va oxirgi sync izohi shu bilan yangilanadi).
Baza nusxasi kerak emas. Kompyuterda faqat Python 3 va `requests` bo'lsa yetadi (`pip install requests`), loyiha papkasi kerak.

Tayyorgarlik (bir marta):
- Panelda har bir terminal **Qurilmalar**da qo'shilgan bo'lsin (nomi va filiali to'g'ri). `tools/terminals.json` dagi nom panel
  nomi bilan bir xil bo'lsin; bir xil nom bir nechta filialda bo'lsa yozuvga `"branch": <filial id>` qo'shing.
- **API kaliti**: serverdagi `/var/www/erp/.env` da `FACE_AGENT_TOKEN`. Uni faqat shu kompyuterdagi xodimga bering, chatga yozmang.

```powershell
# parollar muhit o'zgaruvchisida (tarixga va faylga yozilmaydi)
$env:HIK_PASS = Read-Host "Terminal paroli"
$env:SPETION_AGENT_TOKEN = Read-Host "API kaliti"

python tools/push_faces.py status      # terminallardagi son
python tools/push_faces.py test        # 1 kishi, 1-terminalga (sinov)
python tools/push_faces.py sync        # hammasi (o'zgarmaganlari o'tkazib yuboriladi)
python tools/push_faces.py status      # tekshiring: foydalanuvchi soni = yuz soni = kutilgan son
```

- Rasmi yoki Face ID si o'zgargan odam qayta yuboriladi, o'zgarmaganlar o'tkazib yuboriladi (holat serverda saqlanadi).
- Nofaol bo'lgan yoki rasmi olib tashlangan odam `sync` da terminaldan avtomatik o'chiriladi.
- Ko'p so'rovdan keyin terminal vaqtincha 401 qaytarishi mumkin: `access/hikvision.py` yangi sessiya bilan 3 martagacha qayta urinadi.
- API: `/api/access/agent/{devices,manifest/<token>,photo/<id>,report/<token>}/` (`access/agent.py`), kalit `Authorization: Bearer`.

**Eski server (med.spetion.uz, ko'chirishgacha):** `tools/push_faces_sqlite.py <baza nusxasi papkasi> sync` — avvalgi usul
(sqlite nusxa + `media/faces`). Ko'chirishdan keyin ishlatilmaydi.

## Chiqqan o'quvchilarni terminaldan olib tashlash

`sync` nofaol odamlarni o'zi o'chiradi (agar ular oldin shu skript bilan yuborilgan bo'lsa). Terminalda panelga umuman
bog'lanmagan eski odamlar qolgan bo'lsa:

```powershell
python tools/push_faces.py prune            # terminalda bor, lekin bo'lmasligi kerak odamlar RO'YXATI (hech narsa o'chirmaydi)
python tools/push_faces.py prune --apply    # ro'yxatni ko'rib chiqqach, shularni o'chiradi
```
Avval **ro'yxatni ko'zdan kechiring**, keyin `--apply`.

## Terminalga qo'lda murojaat (ISAPI)

Digest autentifikatsiya (`admin`). Foydali yo'llar (parolni muhit o'zgaruvchisidan oling):

| Maqsad | So'rov |
|---|---|
| Qurilma ma'lumoti / vaqti | `GET /ISAPI/System/deviceInfo`, `GET /ISAPI/System/time` |
| Foydalanuvchi va yuz soni | `GET /ISAPI/AccessControl/UserInfo/Count?format=json` |
| Voqea yuborish sozlamasi | `GET /ISAPI/Event/notification/httpHosts` |
| Terminal jurnali (skanlar) | `POST /ISAPI/AccessControl/AcsEvent?format=json` (major 5, minor 75) |

Terminal o'z jurnalini ham saqlaydi (har skan, `serialNo` bilan). Internet uzilganda yo'qolgan skanlarni shu jurnaldan tiklash mumkin
(avtomatik «to'ldirish» buyrug'i hali yozilmagan — `docs/kirish-chiqish-qoidalari.md` oxirida ro'yxatda).
Eski voqealar jurnalini ISAPI bilan tozalab bo'lmaydi (faqat zavod sozlamasiga qaytarish).
