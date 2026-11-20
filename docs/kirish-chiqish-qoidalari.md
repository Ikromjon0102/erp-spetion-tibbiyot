# Kirish-chiqish: holatlar va xabarlar qoidalari

Terminal skanlari qanday saqlanishi, ota-onaga qanday ko'rinishi va qachon xabar ketishi.

## 1. Ma'lumot oqimi

1. Terminal skanni VPS ga yuboradi → `AccessEvent` (qurilma, Face ID, vaqt, **yo'nalish = qurilma yo'nalishi**, o'quvchi, xom JSON). **Barcha skanlar saqlanadi**, hech biri tashlanmaydi
   (faqat `ACCESS_IGNORE_EVENTS_BEFORE` dan eskilari va takroriy `(qurilma, ID, vaqt)`).
2. Skan saqlanishi bilan `tgbot/signals.py: on_access` ishlaydi (ota-onaga xabar, qoidalar pastda).
3. Sahifalar (ota-ona ilovasi, panel) ochilganda holatni skanlardan hisoblaydi. **Avtomatik yangilanish yo'q** (server yengil qolishi uchun):
   ma'lumot bazada ~1–3 soniyada paydo bo'ladi, lekin sahifa qayta ochilganda/yangilanganda ko'rinadi. Tezkor xabar — Telegram.

## 2. Holat (ota-ona ilovasi, panel, bot `/bugun`)

**Oxirgi skan hal qiladi** (kirish va chiqish skanlari ketma-ket bo'lsa ham):

| Oxirgi skan | Hozir ≥ chiqish vaqti? | Holat |
|---|---|---|
| kirish | — | **Maktabda** (kelgan vaqti = kunning birinchi kirishi) |
| chiqish | yo'q (tanaffus) | **Tashqarida · HH:MM dan** |
| chiqish | ha | **Uyga ketdi · HH:MM** |
| skan yo'q | — | «Hali kelmagan» (9:00 dan keyin) / dam olish kuni (yakshanba) |

«Chiqish vaqti» — paneldan sozlanadigan chegara (**boshlang'ich 16:00**): Panel → Qurilmalar → «Chiqish xabarlari».
Shu vaqtdan oldin chiqib ketgan va qaytmagan o'quvchi, vaqt kelganda «Uyga ketdi» ga o'tadi.

Kod: `access/services.py` (`day_summaries`, `is_break_time`), `accounts/child_data.py: presence`, `panel/views_students.py: _presence_state`, `tgbot/bot.py: today`.

## 3. Telegram xabarlari (ota-onaga)

Faqat botga ulangan ota-onaga boradi. Har o'quvchi uchun **kuniga har turdan bittadan** (`PresenceNotice`, `(o'quvchi, sana, tur)` unikal):

| Xabar | Qachon |
|---|---|
| ✅ «… HH:MM da maktabga keldi» | kunning **birinchi kirish** skani. Keyingi kirishlar xabar bermaydi |
| 🚪 «… HH:MM da maktabdan chiqdi» | **chiqish vaqtidan keyingi** birinchi chiqish skani |

- Chiqish vaqtidan oldingi chiqish skani **jim** (tanaffus). Agar o'quvchi qaytmasa, `send_leave_notices` buyrug'i (cron, har 5 daqiqada) vaqt kelganda
  oxirgi skani «chiqish» bo'lgan o'quvchilarga xabarni yuboradi (xabardagi vaqt — o'sha oxirgi chiqish skani vaqti). Qaytib kirgan (oxirgi skani kirish) o'quvchiga yuborilmaydi.
- 30 daqiqadan eski skan uchun «keldi/chiqdi» xabari yuborilmaydi (eski jurnal qayta kelsa, ota-onalarga eski xabarlar to'planib ketmasin).
- Skan 10–15 marta takrorlansa ham ota-onaga **bitta** xabar boradi; barcha skanlar bazada qoladi.
- Baho, uy vazifasi va e'lon xabarlari alohida (`tgbot/signals.py`).

## 4. Chiqqan o'quvchi

«Maktabdan chiqarish» (`Student.leave`): o'quvchi nofaol (`user.is_active=False`), sinfdan olinadi (oxirgi sinf nomi saqlanadi), chiqqan sana yoziladi.
Ro'yxatlar, qarzdorlar, hisobotlar, ota-ona ilovasi, Telegram bot va e'lon oluvchilardan yo'qoladi. Baho, davomat, to'lov tarixi **saqlanadi**.
«Qaytarish» oxirgi sinfiga qaytaradi; «Butunlay o'chirish» faqat chiqarilganlar uchun (baho/davomat/to'lov ham o'chadi, ota-onalar qoladi).
Terminaldan olib tashlash qo'lda: `docs/terminallar.md`.

## 5. Qarorlar (nima uchun shunday)

- **Nima uchun avtomatik yangilanish (polling) yo'q?** VPS 1 CPU/1 GB va umumiy. Har ochiq sahifaning har 30 soniyada qayta hisoblanishi serverni zo'riqtiradi.
  Tezkor xabar uchun Telegram: faqat skan bo'lganda ishlaydi.
- **Nima uchun dars jadvaliga bog'lanmadi?** Oddiy sozlanadigan vaqt chegarasi (16:00) tushunarliroq va yetarli. Jadvalga bog'lash (har sinfning oxirgi dars tugashi,
  «darsdan oldin chiqib ketdi» ogohlantirishi) keyinga qoldirildi.
- **Nima uchun «chiqdi» faqat 16:00 dan keyin?** Tanaffusda chiqish terminaliga qiziqib skan qilgan o'quvchi «uyga ketdi» deb ko'rinmasligi va ota-onaga ortiqcha xabar bormasligi uchun.
- **Nima uchun o'quvchi avval chiqariladi, keyin o'chiriladi?** O'chirish baho, davomat va to'lov tarixini ham o'chiradi (qaytarib bo'lmaydi); chiqarish tarixni saqlaydi.

## 6. Hozircha qilinmagan g'oyalar

- Terminal jurnalidan yo'qolgan skanlarni tiklash («to'ldirish») buyrug'i (internet uzilganda).
- «Darsdan oldin chiqib ketdi» ogohlantirishi (dars jadvaliga bog'lash).
- Ustoz ilovasida o'z sinfi uchun «bugun kelganlar».
- Chiqqan o'quvchini terminaldan avtomatik olib tashlash.
