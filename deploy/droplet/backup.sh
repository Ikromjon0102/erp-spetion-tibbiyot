#!/usr/bin/env bash
# Har kecha: ikkala baza (pg_dump) + fayllar (ERP media: taom/yuz rasmlari, cheklar; exam storage). 14 kun saqlanadi.
# Tashqi nusxa: rclone'da "spetion-offsite" nomli remote sozlangan bo'lsa (DO Spaces, Google Drive, boshqa server) — o'sha yerga ham.
# Muvaffaqiyatli tugasa LAST_OK fayliga vaqt yoziladi (healthcheck shuni tekshiradi).
set -euo pipefail
D=/var/backups/spetion; T=$(date +%F); mkdir -p "$D"
sudo -u postgres pg_dump -Fc erp > "$D/erp-$T.dump"
sudo -u postgres pg_dump -Fc spetion_exam > "$D/exam-$T.dump"
# MUHIM: ERP media /var/www/erp/app/media da (MEDIA_ROOT = BASE_DIR/media), exam fayllari /var/www/exam/storage da
tar -czf "$D/files-$T.tgz" -C /var/www erp/app/media exam/storage
# bo'sh yoki buzilgan nusxa — xato
for f in "$D/erp-$T.dump" "$D/exam-$T.dump"; do [ -s "$f" ] && pg_restore -l "$f" >/dev/null; done
find "$D" -type f -name '*-*.dump' -mtime +14 -delete
find "$D" -type f -name 'files-*.tgz' -mtime +14 -delete
if command -v rclone >/dev/null && rclone listremotes 2>/dev/null | grep -q '^spetion-offsite:'; then
  rclone copy "$D" spetion-offsite:spetion-backups --include "*-$T.*" && echo "offsite $(date -Is)" > "$D/LAST_OFFSITE"
fi
date -Is > "$D/LAST_OK"
