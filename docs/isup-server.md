# ISUP 5.0 server: terminallarni kompyutersiz, serverdan boshqarish

Holat: **loyiha (taklif), 2026-11-28.** Ishlab chiqarishga hali hech narsa qo'yilmagan. Prototip: `tools/isup_server/` (SDK'siz, testlar bilan).
Bu hujjatda parol va kalit yo'q.

## 1. Qisqacha

- **Maqsad:** binodagi Windows agent (`SpetionAgent.exe`, dalada ishlamadi) o'rniga terminallarni to'g'ridan-to'g'ri my.spetion.uz serveridan boshqarish —
  eduschool.uz qanday qilgan bo'lsa, shunday: terminalning o'zi **ISUP 5.0** (eski nomi EHome) orqali serverga tashqariga ulanadi,
  server shu ulanish orqali ISAPI buyruqlarini yuboradi va hodisalarni qabul qiladi. Maktab routerida port ochish, binoda kompyuter kerak emas.
- **Tanlangan yo'l:** Hikvision'ning **rasmiy ISUP SDK** (Linux x64 `.so` kutubxonalari: `libHCISUPCMS.so`, `libHCISUPAlarm.so`, kerak bo'lsa
  `libHCISUPSS.so`) ustida o'zimizning kichik **Python shlyuzi** (`isup-gateway`, alohida systemd xizmati, ~100–150 MB RAM).
  Django bilan faqat ichki HTTP (127.0.0.1) orqali gaplashadi; hodisalar **mavjud** `/api/access/hikvision/<token>/` manziliga tushadi
  (Django'da hodisa uchun o'zgarish kerak emas); rasm sync `access/sync.py` dagi mavjud mantiq bilan, faqat mijoz almashadi.
- **Nega SDK:** ISUP 5.0 protokoli yopiq va shifrlangan (har terminalning ISUP kaliti + sessiya kaliti). Ishonchli ochiq kodli server topilmadi (3-bo'lim).
  SDK bepul, lekin **Hikvision hisobi bilan yuklab olinadi** — buni founder o'z nomidan qiladi (litsenziya shartlarini u qabul qiladi).
- **Hajm:** ~10–13 ish kuni (SDK kelgandan keyin), 5 bosqich (12-bo'lim). Birinchi bosqich (M0) SDK'siz ham boshlanadi.

## 2. Hozirgi holat

| | Tibbiyot | Asosiy maktab |
|---|---|---|
| Terminal | 4 × DS-K1T343EFWX, V4.48.0 | 4 × DS-K1T341CM, V3.3.200 (192.168.1.190–193) |
| Hodisalar bizga | HTTP listening → `my.spetion.uz` (ishlayapti) | httpHosts 1-slot eduschool'da, **2-slot bo'sh** |
| ISUP markazi (1 ta slot) | eduschool: 135.181.103.251:7661 | eduschool: 135.181.103.251:7661, ID `spetionkirish01/02`, `spetionchiqish01/02` |
| Rasm yuborish | maktab kompyuteri (agent / `push_faces.py`) | hali yo'q |

- Har terminalda ISUP markazi **faqat bitta** (`/ISAPI/System/Network/Ehome`, id ≤ 1). Bizga o'tkazilsa eduschool shu terminalni boshqara olmaydi.
- Asosiy maktab terminallarida eduschool yozgan **190 kishi (123 yuzli)** bor; ularning employeeNo — 24 belgili hex (bizniki raqam: 9001+, 7001+, 8001+),
  ya'ni raqamlar to'qnashmaydi. Founder qarori (2026-11-28): eduschool shartnomasi bekor qilinadi, **bu 190 kishi o'chirilmaydi** (ular Asosiy maktab o'quvchilari).

## 3. Variantlar

| Variant | ISUP 5.0 kalit bilan ro'yxatdan o'tish | ISAPI pass-through | Hodisa (alarm) | Litsenziya / holat | Xulosa |
|---|---|---|---|---|---|
| **(a) Rasmiy ISUP SDK** (HCISUPCMS / HCISUPAlarm / HCISUPSS, Linux x64) | ha (`ENUM_DEV_AUTH` da kalit, `ENUM_DEV_SESSIONKEY`) | ha (`NET_ECMS_ISAPIPassThrough`) | ha (`NET_EALARM_*`, ISUP 5.0 — MQTT turi) | bepul, Hikvision litsenziyasi, yopiq kod; hisob kerak | **tanlandi** |
| (b1) `norches/hikvision-isup` (Python, 2026-09, 0 yulduz, litsenziya yo'q) | da'vo qiladi, lekin sarlavha formati o'zaro zid (20 vs 40 bayt), kalit/shifrlash tavsifi yo'q | yo'q | o'ylab topilgan format | faqat o'z simulyatori bilan sinalgan | ishlatib bo'lmaydi |
| (b2) `schnupfeldjack-lgtm/isup-server` (Java/Spring, 2026-10, litsenziya yo'q) | rasmiy SDK orqali (JNA) | ha | video uchun | SDK'ni baribir talab qiladi; litsenziyasiz kodni ko'chirib bo'lmaydi | faqat g'oya sifatida foydali (SDK Linux'da ishlashini tasdiqlaydi) |
| (b3) `stefan-golinschi/Hikvision-ISUP5.0-SDK` | — | — | — | Hikvision SDK'ning ruxsatsiz nusxasi | **ishlatilmaydi** (manba va litsenziya noaniq) |
| (b4) `tsingeye/FreeEhome` (Go) | faqat EHome 2.x | — | — | GitHub'da hozir ochilmaydi (451) | ISUP 5.0 yo'q |
| (c) Protokolni o'zimiz yozish (teskari muhandislik) | ochiq spetsifikatsiya yo'q, shifrlangan, proshivka bilan o'zgaradi | — | — | litsenziya xavfi | 4–8+ hafta va ishonchsiz — yo'q |
| (d) Binodagi Windows agent | — | LAN orqali | HTTP listening | o'zimizniki | dalada ishlamadi (founder) |
| (e) HikCentral / Hik-Gateway (Hikvision platformasi) | ha | API orqali | ha | pullik/litsenziya, Windows server | droplet'ga mos emas, ortiqcha |

**Til tanlovi:** SDK C kutubxonasi; rasmiy namunalar Java (JNA) va C. Biz **Python `ctypes`** dan foydalanamiz: alohida JVM (+200–300 MB) kerak emas,
loyiha venv'i va testlar bir xil qoladi. Struct'lar SDK bilan keladigan header'lardan (`incEn/HCISUPCMS.h` va b.) aniq ko'chiriladi — taxmin qilinmaydi.
Agar ctypes bilan muammo chiqsa, zaxira yo'l: shu shlyuzni Java'da (rasmiy demo asosida) yozish — Django tomoni o'zgarmaydi (ichki API bir xil).

## 4. Arxitektura

```
 Maktab tarmog'i (NAT ortida)                          Droplet 46.101.207.23 (my.spetion.uz / isup.spetion.uz)
 ┌──────────────┐  TCP 7660 ro'yxatdan o'tish (CMS)    ┌───────────────────────── isup-gateway (systemd, user isup) ─┐
 │  Terminal    │ ───────────────────────────────────▶ │ libHCISUPCMS.so  ── register cb: device ID + ISUP kalit    │
 │  ISUP 5.0    │ ◀── ISAPI pass-through (shu ulanish) │                   ── NET_ECMS_ISAPIPassThrough             │
 │              │  TCP 7663 hodisalar (alarm, MQTT)    │ libHCISUPAlarm.so ── alarm cb ─▶ navbat ─▶ Forwarder       │
 │              │ ───────────────────────────────────▶ │                                                              │
 │              │  HTTPS 443 GET /isup-face/<token>.jpg│ ichki API 127.0.0.1:7690   rasm berish 127.0.0.1:7691        │
 │              │ ───────▶ nginx ────────────────────▶ │                                                              │
 │              │  HTTPS 443 HTTP listening (zaxira)   └──────────┬───────────────────────────▲────────────────────┘
 └──────────────┘ ───────▶ nginx ─▶ gunicorn                      │ POST /api/access/hikvision/<token>/   │ POST /isapi, /face
                                     127.0.0.1:8010 ◀─────────────┘ (hodisa, «tirik» signali)            │ (Bearer ISUP_API_TOKEN)
                                     Django: AccessEvent, Telegram xabarlari, sync_device ───────────────┘
```

- Terminal → server: faqat **chiquvchi** ulanishlar (hozir eduschool'ga ham shunday ulanadi), maktab routerida hech narsa ochilmaydi.
- Shlyuzda biznes mantiq yo'q: kim qaysi terminalda bo'lishi kerakligini Django hal qiladi (hozirgidek `access/sync.py`).

## 5. Portlar va firewall

| Port | Kim ochadi | Nima | Izoh |
|---|---|---|---|
| **7660/tcp** (+ 7660/udp) | ufw, tashqariga | CMS — terminal ro'yxatdan o'tishi va ISAPI pass-through | standart port; eduschool 7661 ishlatgan — bizga ahamiyati yo'q. M1 da `ss -lntup` bilan qaysi biri haqiqatan ishlatilishi ko'riladi, keragi yo'g'i yopiladi |
| **7663/tcp** | ufw, tashqariga | alarm (hodisalar) — ISUP 5.0 da «MQTT» turi (`dwAlarmServerType=2`) | manzil terminalga ro'yxatdan o'tishda serverdan beriladi (`NET_EHOME_SERVER_INFO_V50`) |
| 6011/tcp | **faqat kerak bo'lsa** | SDK rasm serveri (SS, «bulutli ombor» turi) | faceURL nginx orqali ishlasa — kerak emas (9-bo'lim) |
| 443/tcp | mavjud | nginx: `/isup-face/` (terminal rasmni yuklab oladi) va HTTP listening | yangi `location` qo'shiladi |
| 7690/tcp | yo'q (127.0.0.1) | shlyuz ichki API | tashqaridan ko'rinmaydi |
| 7691/tcp | yo'q (127.0.0.1) | rasm berish (nginx proxy qiladi) | tashqaridan faqat nginx orqali |

```bash
ufw allow 7660/tcp && ufw allow 7660/udp && ufw allow 7663/tcp      # M1 da; DO cloud firewall bo'lsa — o'sha yerda ham
```

- **Domen:** terminallarga IP emas, alohida nom yoziladi: `isup.spetion.uz` (A → droplet, proxy'siz). Server founderning yakuniy serveriga ko'chganda
  20 ta terminalni qayta sozlash shart bo'lmaydi — faqat DNS. Terminal domen qabul qilishi M0 da tekshiriladi (qabul qilmasa — IP).
- Maktablar statik IP'ga ega bo'lsa, 7660/7663 ni faqat shu IP'larga ochish mumkin (ixtiyoriy; asosiy himoya — ISUP kaliti).

## 6. Droplet'da ishlashi

- **Joylashuv:** SDK — `/opt/isup-sdk/lib/` (root egasi, faqat o'qish; **git'ga qo'yilmaydi**), holat/navbat — `/var/lib/isup-gateway/`,
  SDK jurnali — `/var/log/isup-sdk/` (logrotate, 14 kun). Kod — mavjud `/var/www/erp/app/tools/isup_server/` (deploy bilan birga yangilanadi).
- **Xizmat** (`deploy/droplet/isup-gateway.service`, M1 da qo'shiladi):

```ini
[Unit]
Description=Spetion ISUP shlyuzi (Hikvision terminallari)
After=network.target erp.service

[Service]
User=isup
Group=isup
WorkingDirectory=/var/www/erp/app
EnvironmentFile=/var/www/erp/isup.env          # ISUP_API_TOKEN, ISUP_PUBLIC_HOST, ISUP_FACE_BASE, ...
Environment=LD_LIBRARY_PATH=/opt/isup-sdk/lib:/opt/isup-sdk/lib/HCAapSDKCom
ExecStart=/var/www/erp/venv/bin/python -m tools.isup_server --registry /var/lib/isup-gateway/registry.json
Restart=always
RestartSec=5
MemoryMax=300M
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/isup-gateway /var/log/isup-sdk

[Install]
WantedBy=multi-user.target
```

- **Resurs:** 20 terminal uchun Python + SDK oqimlari + OpenSSL ≈ 100–150 MB RAM (cheklov 300 MB), CPU deyarli nol (heartbeat 30 s da bir,
  ertalabki tig'iz paytda ham sekundiga < 1 hodisa). SDK o'zi 64-bit Linux'da 10 000 tagacha qurilmani ko'taradi. Droplet (2 CPU / 2 GB) yetadi.
- Bitta jarayon (SDK tinglovchisi bitta bo'lishi kerak). SDK callback'lari o'z oqimlarida chaqiriladi: ular ichida faqat navbatga qo'yiladi,
  HTTP/IO alohida oqimda. ctypes callback obyektlari GC o'chirmasligi uchun saqlab qo'yiladi.
- Deploy: `push.sh` dan keyin `systemctl restart isup-gateway` (terminallar ~30–60 s da o'zi qayta ulanadi; shu vaqtdagi hodisalar HTTP listening
  orqali baribir keladi, 10-bo'lim).

## 7. Django bilan aloqa

| Yo'nalish | Qanday | Django'da o'zgarish |
|---|---|---|
| Hodisa: shlyuz → Django | `POST http://127.0.0.1:8010/api/access/hikvision/<Device.token>/` (Host: my.spetion.uz), HTTP listening bilan **bir xil JSON** | **yo'q** (mavjud view) |
| «Tirik» signali | o'sha manzilga bo'sh `{}` har daqiqa — view `Device.last_seen` ni yangilaydi | yo'q |
| ISAPI: Django → terminal | `POST 127.0.0.1:7690/isapi {device_id, method, path, body}` (`Authorization: Bearer ISUP_API_TOKEN`) | M3: `RemoteClient` |
| Yuz rasmi | `POST 127.0.0.1:7690/face {device_id, employee_no, jpeg}` — shlyuz rasmni vaqtincha manzilga qo'yadi, terminalga `faceURL` beradi | M3 |
| Qurilmalar ro'yxati (device ID → kalit → token) | M3: `manage.py isup_registry` bazadan `/var/lib/isup-gateway/registry.json` yozadi, shlyuz qayta o'qiydi (yoki ichki endpoint) | M3 |
| Holat | `GET 127.0.0.1:7690/devices` — panelda «ISUP: ulangan / yo'q» | M3 |

M3 dagi Django o'zgarishlari (kichik):
- `Device` ga: `transport` (`lan` / `agent` / `isup`), `isup_device_id` (noyob), `isup_key` (shlyuz autentifikatsiya uchun ochiq ko'rinishda kerak —
  xesh bilan saqlab bo'lmaydi; faqat `devices.manage` huquqi bor xodimga ko'rsatiladi). Migratsiya.
- `access/sync.py: sync_device` — `Client(device)` o'rniga `client_for(device)`: `isup` bo'lsa `tools.isup_server.isapi.RemoteClient`
  (`access.hikvision.Client` bilan bir xil usullar — testda tekshirilgan). Qolgan mantiq (digest, FaceSync, o'chirish) o'zgarmaydi.
- Panel → Qurilmalar: ISUP terminallar uchun «Tekshirish/Yuborish» tugmalari yana ishlaydi (server terminalga yeta oladi).
- `manage.py check_isup` (cron, `check_agents` kabi): ish vaqtida terminal 30 daqiqa ulanmasa — ogohlantirish.

## 8. Xavfsizlik

- **Har terminalga alohida ISUP kaliti** (12 belgi, harf+raqam, `registry.generate_key`). Ro'yxatda yo'q device ID ro'yxatdan o'tish bosqichida rad etiladi
  (`on_register` → False); kalit mos kelmasa SDK ulanishni rad etadi. Kalit chiqib ketsa — faqat o'sha terminal kaliti almashtiriladi.
  ISUP 5.0 trafigi sessiya kaliti bilan shifrlanadi.
- **Ichki API** faqat 127.0.0.1 da, `ISUP_API_TOKEN` (≥ 24 belgi, `hmac.compare_digest`). Faqat `/ISAPI/...` yo'llari va GET/PUT/POST/DELETE uzatiladi;
  har terminalga bir vaqtda bitta so'rov.
- **Rasm manzillari:** tasodifiy 32 belgili token, 5 daqiqa amal qiladi va terminal javob bergach darhol o'chadi; ro'yxati yo'q; nginx'da shu
  `location` uchun `access_log off` (token jurnalga tushmaydi). Bolalar rasmlari ochiq papkada turmaydi.
- **SDK — yopiq kod va tarmoqqa ochiq.** Eski versiyalarida xatolar topilgan (CVE-2021-42260: HTTP sarlavha/XML tahlilida stack overflow). Shuning uchun:
  eng yangi SDK versiyasi; root'siz alohida `isup` foydalanuvchi; systemd cheklovlari (`ProtectSystem=strict`, `MemoryMax`); faqat kerakli portlar;
  SDK yangilanishini kuzatish.
- Biometrik ma'lumot endi maktab kompyuteridan emas, to'g'ridan-to'g'ri serverdan HTTPS orqali boradi (yaxshiroq). Lokalizatsiya bo'yicha huquqshunos
  xulosasi (qarorlar §8) baribir kerak.

## 9. Yuz rasmlari terminalga qanday boradi

ISUP pass-through matnli so'rov uzatadi; LAN'dagidek multipart bilan rasm yuborish kafolatlanmagan. ISUP 5.0 da odatiy yo'l — **faceURL**:

1. Django `sync_device` → `RemoteClient.set_face(employee_no, jpeg)` → shlyuz `/face`.
2. Shlyuz rasmni `FaceStore` ga qo'yadi (≤ 200 KB JPEG — `accounts/photos.py` allaqachon shunday qiladi), manzil: `https://isup.spetion.uz/isup-face/<token>.jpg`.
3. Pass-through: `PUT /ISAPI/Intelligent/FDLib/FDSearch/Delete` (eski rasm), keyin
   `POST /ISAPI/Intelligent/FDLib/FaceDataRecord?format=json {"faceLibType":"blackFD","FDID":"1","FPID":"9001","faceURL":"https://…"}`.
4. Terminal rasmni nginx → shlyuz (127.0.0.1:7691) dan yuklab oladi, yuzni tahlil qiladi, javob beradi; token o'chiriladi.

Xavflar va zaxira (M0 da LAN orqali, SDK'siz tekshiriladi):
- Eski proshivka (DS-K1T341CM V3.3) HTTPS faceURL'ni qo'llamasligi yoki Let's Encrypt ildiz sertifikatini tanimasligi mumkin.
  Unda: (1) shu `location` ni 80-portda ham ochish (HTTP; token bir martalik va 5 daqiqalik), yoki (2) SDK'ning rasm serveri (SS, 6011, «bulutli ombor»):
  rasm `NET_ESS_ClientDoUpload` bilan SS'ga yuklanadi, terminalga SS manzili beriladi.
- SDK cheklovi: SS sekundiga 20 tagacha rasm, har biri ≤ 200 KB.

Birinchi to'liq sync: ~420 kishi × ~1–2 s ≈ 10–15 daqiqa bitta terminalga; terminallar parallel.

## 10. Hodisalar qanday tushadi

1. Terminal yuzni taniydi → ISUP alarm (7663) → SDK callback (`EHOME_ISAPI_ALARM` yoki `EHOME_ALARM_ACS`, JSON yoki XML).
2. `events.parse_alarm` uni HTTP listening JSON shakliga keltiradi (`dateTime`, `AccessControllerEvent.employeeNoString`, `subEventType`).
3. `Forwarder` → `POST 127.0.0.1:8010/api/access/hikvision/<token>/` → mavjud mantiq: `AccessEvent`, yo'nalish qurilmadan, eski jurnal filtri,
   ota-onaga Telegram xabarlari.
4. Django javob bermasa (deploy, qayta ishga tushish) → diskdagi navbat (`spool.jsonl`), har daqiqa qayta yuboriladi, tartib saqlanadi.
   4xx (noto'g'ri token) — qayta urinilmaydi, jurnalga yoziladi.

- **Ikki yo'l — bitta yozuv.** HTTP listening (terminal → 443) **o'chirilmaydi**: shlyuz to'xtasa ham hodisalar keladi. Ikkala yo'ldan kelgan bir xil skan
  `(qurilma, Face ID, vaqt)` noyobligi tufayli bitta yozuv bo'ladi (testda tekshirilgan). Asosiy maktabda httpHosts **2-slot bo'sh** — uni hoziroq
  bizga yo'naltirish mumkin (eduschool 1-slotiga tegmasdan).
- **Yo'qolganlarni tiklash (M5):** terminal qayta ulanganda pass-through bilan `POST /ISAPI/AccessControl/AcsEvent` (major 5, minor 75) — oxirgi soatlar
  jurnali o'qiladi va yuboriladi; takrorlar baribir tushib qoladi.

## 11. Terminalni o'tkazish tartibi (har terminal alohida)

**Muhim qoidalar:** terminalda «Restore / Default», foydalanuvchi yoki yuz kutubxonasini o'chirish **qilinmaydi**; eduschool yozgan odamlar (hex employeeNo)
qoladi; bizning sync faqat o'zi yozgan yozuvlarni (FaceSync'da bor) o'chiradi; `push_faces.py prune --apply` ISUP terminallarida ishlatilmaydi.

Tayyorgarlik (bir marta): shlyuz M1–M2 ishlayapti, portlar ochiq, `isup.spetion.uz` DNS, bitta sinov terminali bilan sinalgan.

1. **Yozib olish (o'zgartirishdan oldin).** Terminal web-sahifasi (maktab tarmog'idan, masalan `http://192.168.1.190`) → Configuration → Network →
   Advanced → **Platform Access (ISUP)**: server manzili, port, device ID, protokol versiyasi — skrinshot. Kalit maydoni odatda ko'rinmaydi:
   qaytarish kerak bo'lsa uni eduschool'dan olish kerak. HTTP listening sozlamalari ham skrinshot.
2. **Panelda:** qurilma → «Ulanish usuli: ISUP» → device ID (masalan `spt-a1`) → «Kalit yaratish». Device ID va kalit ko'rsatiladi.
3. **Terminalda:** Platform Access → Enable; Protocol = ISUP 5.0; Server address = `isup.spetion.uz` (yoki 46.101.207.23); Port = 7660;
   Device ID; Encryption/ISUP key → Save. Boshqa hech narsaga tegilmaydi.
4. **Tekshirish (1–2 daqiqa):** terminalda Register status = Online; panelda «ISUP: ulangan». Pass-through bilan faqat o'qish:
   `deviceInfo`, `UserInfo/Count` — o'tkazishdan oldingi son bilan bir xil bo'lishi kerak.
5. **Inventarizatsiya:** terminaldagi ro'yxat (`list_users`) saqlanadi va `collision_report`: bizning raqam terminalda **boshqa ismli** odamda bo'lsa —
   avtomatik yozilmaydi (begona yozuv ustidan yozilmasin), qo'lda hal qilinadi. Asosiy maktabda hex raqamlar sabab to'qnashuv kutilmaydi.
6. **Sinov:** 1 kishi (sinov xodimi) yozish + yuz → shu odam skanerlaydi → hodisa panelda bir necha soniyada. Ikki yo'ldan kelsa ham 1 yozuv.
7. **To'liq sync**, natija panelda (yuborildi / xato). Keyingi terminal — kamida 1 kun kuzatuvdan keyin.

Tartib: avval Tibbiyot (4 terminal, HTTP listening allaqachon bizda — xavf kam), keyin Asosiy maktab (4).

**Qaytarish:** terminalda Platform Access'ga 1-qadamdagi qiymatlar qaytariladi (eduschool kaliti kerak). HTTP listening bizda qoladi — hodisalar to'xtamaydi.
Bizning shlyuzda hech narsa o'chirish shart emas (ro'yxatdan chiqarilgan terminal ulanolmaydi).

**Asosiy maktab — eduschool yuzlaridan foydalanish (ixtiyoriy):** eduschool yozgan 123 yuz bizning o'quvchilarimizniki. Ism bo'yicha moslab,
o'quvchi kartasida `Face ID` ga terminaldagi hex raqam yozilsa (maydon 32 belgigacha), mavjud yuz bilan skanlar darhol bizda o'quvchiga bog'lanadi va
qayta rasmga olish shart bo'lmaydi. Moslash ro'yxatini founder tasdiqlaydi (alohida kichik ish, M5).

## 12. Bosqichlar va baho

| # | Ish | Baho | SDK kerakmi |
|---|---|---|---|
| **M0** | LAN orqali (maktab kompyuteri/AnyDesk) bitta terminalda faceURL sinovi: `FaceDataRecord` + `https://my.spetion.uz/...` sinov rasmi (ikkala model); ISUP kaliti talablari, domen qabul qilinishi; eski ISUP sozlamalarini yozib olish. Founder SDK'ni yuklab oladi | 0,5–1 kun | yo'q |
| **M1** | ctypes bog'lamlari (CMS: init, listen, register callback — ID/kalit/sessiya kaliti, pass-through), systemd, ufw, nginx `/isup-face/`, registry. 1 sinov terminali ulanadi, faqat o'qish | 3–4 kun | ha |
| **M2** | Alarm (EAlarm, ISUP 5.0 / 7663), ro'yxatdan o'tishda alarm manzilini berish, Forwarder + navbat + «tirik» signali; HTTP listening bilan takror tekshiruvi | 2 kun | ha |
| **M3** | Django: `Device.transport/isup_device_id/isup_key` + migratsiya, panel formasi, `RemoteClient` sync'da, to'qnashuv himoyasi, `isup_registry`, `check_isup`, testlar | 2–3 kun | yo'q |
| **M4** | O'tkazish: Tibbiyot 4 → Asosiy maktab 4; hujjatlar (`terminallar.md`, yo'riqnoma); agentni nafaqaga chiqarish | 1–2 kun + kuzatuv | — |
| M5 | (ixtiyoriy) jurnaldan yo'qolgan hodisalarni tiklash; eduschool yuzlarini o'quvchilarga moslash | 1–2 kun | — |

**Jami ≈ 10–13 ish kuni** (2–3 hafta kalendar), SDK'ni olish vaqti bundan tashqari. M0 va M3 SDK'siz parallel boshlanishi mumkin.

## 13. Founder qo'lda qiladigan ishlar

1. **SDK'ni yuklab olish** (biz hisob ochmaymiz va litsenziyani biz qabul qilmaymiz):
   - Hikvision Open Platform: `open.hikvision.com` → 下载 (Download) → 设备集成SDK → **ISUP SDK**, Linux 64-bit (ISUP 5.0 qo'llaydigan eng oxirgi versiya)
     + inglizcha «ISUPSDK (General) Development Guide». Bepul hisob kerak; ba'zi resurslar korxona tasdig'ini so'raydi.
   - Yoki xalqaro: Hikvision TPP (`tpp.hikvision.com`, OneHikID hisobi; integratsiya hujjatlari uchun kompaniya ma'lumoti yoki mintaqaviy
     integratsiya bo'limi orqali).
   - Bo'lmasa: O'zbekistondagi rasmiy Hikvision distribyutori/integratoridan so'rash.
   - Litsenziya matnini o'qib, nusxasini saqlang (tijoriy foydalanish va tarqatish shartlari). SDK arxivini bizga xavfsiz kanal orqali bering
     yoki serverga `/opt/isup-sdk/` ga o'zingiz qo'ying. Repoga qo'yilmaydi.
2. **eduschool bilan:** terminallar ulardan uzilishi haqida xabar (shartnoma bekor qilinmoqda); qaytarish ehtimoli uchun ularning ISUP kalitini olib qo'yish.
3. **Har binoda odam:** terminal web-sahifasiga kira oladigan kishi (yoki AnyDesk bilan maktab kompyuteri) + terminal admin paroli; o'tkazish vaqti
   (darsdan keyin) kelishiladi.
4. **Maktab interneti:** chiquvchi TCP 7660 va 7663 bloklanmaganini tasdiqlash (hozir 7661 ishlayapti — odatda muammo yo'q). Statik IP bo'lsa — bizga ayting.
5. **DNS:** `isup.spetion.uz` A-yozuvi (biz qiymatini beramiz) — agar DNS boshqaruvi founderda bo'lsa.
6. Biometrik ma'lumot bo'yicha huquqshunos xulosasi (ochiq savol, qarorlar §8).

## 14. Ochiq savollar va xavflar

- **SDK olinmasa** — butun reja to'xtaydi (protokolni o'zimiz yozish tavsiya etilmaydi). Shu vaqtgacha: HTTP listening (hodisalar) ishlayveradi,
  rasmlar — `push_faces.py` qo'lda.
- DS-K1T341CM V3.3 da faceURL va alarm formati (JSON yoki XML) — M0/M2 da tekshiriladi; `parse_alarm` ikkalasini ham o'qiydi.
- ISUP pass-through javob/hajm cheklovlari — biz faqat JSON yuboramiz (rasm URL orqali), muammo kutilmaydi.
- Wi-Fi terminallarda heartbeat uzilishlari: `dwKeepAliveSec=30`, `dwTimeOutCount=6` (≈ 3 daqiqada «uzildi»), kuzatib sozlanadi.

## 15. Prototip: `tools/isup_server/`

SDK'siz ishlaydigan qismlar yozilgan va `python manage.py test tools.isup_server` bilan tekshiriladi (tarmoqsiz, 24 test):

| Fayl | Nima |
|---|---|
| `registry.py` | device ID → ISUP kaliti → panel tokeni; kalit generatsiyasi va tekshiruvi; noma'lum ID rad |
| `events.py` | `parse_alarm` (JSON/XML → HTTP listening shakli), `Forwarder` (Django'ga, navbat, qayta yuborish, «tirik» signali) |
| `isapi.py` | `PassthroughClient` (= `access.hikvision.Client` usullari, rasm faceURL bilan), `RemoteClient` (Django → shlyuz), `collision_report` |
| `faces.py` | `FaceStore`: bir martalik, 5 daqiqalik rasm manzillari |
| `backend.py` | `FakeBackend` + `FakeTerminal` (testlar), `HikSdkBackend` — SDK yo'qligini aniq aytadi; ctypes qismi M1 da |
| `gateway.py` | hammasini bog'laydi; ichki API (`/health`, `/devices`, `/isapi`, `/face`) va `/isup-face/<token>.jpg` |
| `tests.py` | ro'yxatdan o'tish (noto'g'ri ID/kalit rad), pass-through, foydalanuvchi + yuz faceURL bilan, begona yozuvlarga tegmaslik, navbat, Django: hodisa mavjud view'ga tushadi va takrorlanmaydi |

Mahalliy sinov: `python -m tools.isup_server --fake --registry registry.json` (`ISUP_API_TOKEN` o'rnatilgan bo'lsin).

## Manbalar

- Rasmiy ISUP SDK Java namunasi (`config.properties`: CMS 7660, alarm 7662/7663 va `AlarmServerType=2 — MQTT (ISUP5.0)`, rasm serveri 6011 «ISUP5.0 uchun
  bulutli ombor turi», `CmsDemo`: `ENUM_DEV_AUTH` da ISUPKey, `NET_ECMS_ISAPIPassThrough`) — GitHub'dagi nusxasidan **faqat o'qildi**, yuklab olinmadi.
- «ISUPSDK (General) Development Guide» (V2.5, 2021-09): Windows/Linux 64-bit; CMS 64-bit'da 10 000 qurilma; AMS sekundiga 2000 hodisa; SS 20 rasm/s, ≤ 200 KB;
  `NET_EHOME_SERVER_INFO_V50` (`dwAlarmServerType`: 0-UDP, 1-UDP+TCP, 2-MQTT; `dwPicServerType`: 2-bulutli ombor, 4-ISUP5.0); `NET_ECMS_SetAliveTimeout`.
- cossack9989, «A glance at Hikvision ISUP SDK» (2021): SDK tarkibi (`libHCISUPCMS.so`, `libHCISUPAlarm.so`, `libHCISUPSS.so`, …), CVE-2021-42260.
- `schnupfeldjack-lgtm/isup-server` `sdk/README.md`: SDK manbasi — open.hikvision.com, ISUP SDK, Linux x86_64 ishlab chiqarishda.
- Hikvision TPP «Open Capabilities» sahifasi: OneHikID ro'yxatdan o'tish, integratsiya hujjatlari.
