#!/usr/bin/env bash
# Nightly dumps of both databases + media; keeps 14 days. Copy /var/backups/spetion off the server too!
set -euo pipefail
D=/var/backups/spetion; T=$(date +%F)
sudo -u postgres pg_dump -Fc erp > "$D/erp-$T.dump"
sudo -u postgres pg_dump -Fc spetion_exam > "$D/exam-$T.dump"
tar -czf "$D/files-$T.tgz" -C /var/www erp/media exam/storage 2>/dev/null || true
find "$D" -type f -mtime +14 -delete
