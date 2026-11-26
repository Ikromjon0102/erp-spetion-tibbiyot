# spetion.uz landing

Statik sahifa. Server: eski VPS (164.90.162.22), `/var/www/spetion-landing/` (nginx `sites-enabled/spetion-landing`).

- `index.html` — yangi dizayn (2026-11-26): Spetion oilasi (til markazi, Spetion School, tibbiyot maktabi, bog'cha), tarix, My Spetion bo'limi, asoschi.
- 2026-11-26 founder tasdiqladi va joylandi. Oldingi versiya: `/root/backups/spetion-landing-index-before-redesign-20261126.html`.
- Eski sahifa zaxirasi serverda: `/root/backups/spetion-landing-index-20261126.html`.

Joylash:
```bash
scp landing/index.html root@164.90.162.22:/var/www/spetion-landing/index.html
scp landing/assets/* root@164.90.162.22:/var/www/spetion-landing/assets/
```
