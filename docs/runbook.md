# Runbook: server, joylash, zaxira

Bu hujjat parol yoki token saqlamaydi. Maxfiy qiymatlar serverdagi `.env` faylida turadi.

## Server (med.spetion.uz)

- **VPS:** DigitalOcean, Ubuntu 24.04, **1 CPU / ~1 GB RAM**, SSH kalit bilan (`root@164.90.162.22`). Server vaqti **UTC** (Toshkent = UTC+5).
- **Server umumiy:** boshqa loyihalar ham ishlaydi (spetion.uz, exam.spetion.uz, ishonch.spetion.uz, qarzdaptar.uz, norin.kodyoz.uz, tunl.uz, te_report_bot). **Ularga tegmang.**
  `nginx` ni faqat `nginx -t` dan keyin `reload` qiling. `certbot` ni faqat o'z domenimiz uchun (`-d med.spetion.uz` yoki `--cert-name`) ishlating.
- **Joylashuv:** `/var/www/med-spetion/`

  | Yo'l | Nima |
  |---|---|
  | `app/` | loyiha kodi (`git archive` bilan yangilanadi) |
  | `app/media/faces/` | yuz rasmlari (o'quvchi/ustoz/xodim), `media/faces_thumbs/` — 96 px kichik nusxalar (qayta yaratiladi) |
  | `venv/` | Python muhiti |
  | `data/db.sqlite3` | **baza (SQLite)** |
  | `.env` | maxfiy sozlamalar (git da yo'q) |
  | `leave.log` | chiqish xabarlari cron jurnali |

- **Xizmat:** `med-spetion.service` (foydalanuvchi `medspetion`, gunicorn `127.0.0.1:8010`, **1 worker, 2 thread**, `MemoryMax=260M`). Nginx: `sites-enabled/med.spetion.uz`.
  Namunalar repoda: `deploy/med-spetion.service`, `deploy/nginx-med.spetion.uz.conf`.
- **`.env` kalitlari** (qiymatlari serverda): `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SQLITE_PATH`, `BOT_TOKEN` (Telegram bot),
  `ACCESS_IGNORE_EVENTS_BEFORE` (shu vaqtdan eski terminal voqealari hisobga olinmaydi; terminal xotirasidagi eski jurnal qayta kelganda himoya).

## Joylash (yangilash)

Mahalliy kompyuterdan, `main` commit qilingan bo'lishi kerak:

```bash
# 1) testlar
python manage.py test

# 2) bazaning zaxirasi + kodni yuborish + migratsiya + qayta ishga tushirish
git archive HEAD | ssh root@164.90.162.22 'tar -x -C /var/www/med-spetion/app \
  && chown -R medspetion:medspetion /var/www/med-spetion/app \
  && cp /var/www/med-spetion/data/db.sqlite3 /var/www/med-spetion/data/db.sqlite3.before-<nom> \
  && cd /var/www/med-spetion/app && set -a && . ../.env && set +a \
  && sudo -u medspetion -E ../venv/bin/python manage.py migrate --noinput \
  && systemctl restart med-spetion && sleep 3 && systemctl is-active med-spetion'

# 3) tekshirish
curl -s -o /dev/null -w "%{http_code}\n" https://med.spetion.uz/login/      # 200 bo'lishi kerak
```

- Yangi paket qo'shilgan bo'lsa (`requirements.txt`), `migrate` dan oldin `../venv/bin/pip install -r requirements.txt` ni `medspetion` nomidan ishga tushiring.
- Statik fayllar o'zgargan bo'lsa: `manage.py collectstatic --noinput` (`medspetion` nomidan, `.env` yuklangan holda).
- `manage.py` ni doim `.env` yuklab va `medspetion` foydalanuvchisi nomidan ishga tushiring: `sudo -u medspetion -E ../venv/bin/python manage.py ...`.
- Restartdan keyin 1–3 soniya sayt javob bermasligi mumkin; `is-active` va 200 ni kuting.
- **Xotira:** 1 GB serverda og'ir amallar (katta import, ko'p worker) qilmang; `free -m` bilan qarab turing.

## Zaxira

- Joylashdan oldin `data/db.sqlite3.before-<nom>` nusxasi olinadi (migratsiya bor-yo'qligidan qat'i nazar). Eski nusxalarni vaqti-vaqti bilan o'chirib turing.
- Asosiy baza zaxirasi avtomatik emas. Tavsiya: kamida haftada bir mahalliy kompyuterga nusxa olish:
  ```bash
  scp root@164.90.162.22:/var/www/med-spetion/data/db.sqlite3 ./zaxira-$(date +%F).sqlite3
  scp -r root@164.90.162.22:/var/www/med-spetion/app/media/faces ./zaxira-faces-$(date +%F)
  ```
- Bazada o'quvchilarning shaxsiy ma'lumoti bor: zaxira fayllarini repoga qo'ymang va ochiq joyda saqlamang (`.gitignore` da `*.sqlite3` bor).
- Eski zaxiralar serverda: `/root/backups/` (eski demo bazasi, eski `smartschool`). Kerak bo'lmasa o'chirish mumkin.

## Cron

`/etc/cron.d/med-spetion-leave` — har 5 daqiqada **12:00–21:00 Toshkent (UTC 07–16)**:

```
*/5 7-16 * * * medspetion cd /var/www/med-spetion/app && set -a && . ../.env && set +a && ../venv/bin/python manage.py send_leave_notices >> /var/www/med-spetion/leave.log 2>&1
```
U «chiqdi» xabarlarini yuboradi (qoidalar: `docs/kirish-chiqish-qoidalari.md`). Vaqt `leave.log` da ko'rinadi. Chiqish vaqti paneldan 21:00 dan keyinga o'zgartirilsa, cron soatlarini ham kengaytiring.

## Telegram bot

- Bot: **@spetion_robot**. Webhook: `https://med.spetion.uz/tg/webhook/` (`manage.py tg_webhook` o'rnatadi). Tekshirish (token serverda, ekranga chiqarmang):
  ```bash
  ssh root@164.90.162.22 'set -a; . /var/www/med-spetion/.env; set +a; curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"'
  ```
  `pending_update_count` ~0 va `last_error_message` yo'q bo'lsa sog'lom.
- Ota-onani ulash: botga `/start` → «Raqamni yuborish» (raqam maktab ro'yxatida bo'lishi kerak). Qo'lda havola: `manage.py tg_link +998XXXXXXXXX` (3 kun amal qiladi).
- `BOT_TOKEN` bo'lmasa xabar yuborish jim o'tkazib yuboriladi.

## Nosozlikda

| Belgi | Tekshirish |
|---|---|
| Sayt ochilmayapti | `systemctl status med-spetion`, `journalctl -u med-spetion -n 50`, `nginx -t`, `free -m` (xotira) |
| Terminaldan voqea kelmayapti | Panel → Qurilmalar → «Oxirgi signal»; terminalning HTTP Listening manzili/tokeni; `docs/terminallar.md` |
| Xabar bormayapti | `BOT_TOKEN`, `getWebhookInfo`, ota-ona botga ulanganmi (`TelegramLink`), `leave.log` |
| Migratsiya xatosi | zaxiradan qaytaring: `cp data/db.sqlite3.before-<nom> data/db.sqlite3` va servisni qayta ishga tushiring |
| Qo'lda tekshirish | `manage.py check`, `manage.py send_leave_notices` (xavfsiz, faqat kutilayotganini yuboradi) |
