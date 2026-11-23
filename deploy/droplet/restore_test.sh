#!/usr/bin/env bash
# Haftalik tiklash sinovi: oxirgi ERP nusxasini vaqtinchalik bazaga tiklaydi, asosiy jadvallarni sanaydi va bazani o'chiradi.
# Natija /var/backups/spetion/RESTORE_TEST ga yoziladi; xato bo'lsa healthcheck ogohlantiradi.
set -uo pipefail
D=/var/backups/spetion; DB=erp_restore_test
LAST=$(ls -1t "$D"/erp-*.dump 2>/dev/null | head -1)
fail() { echo "FAIL $(date -Is) $1" > "$D/RESTORE_TEST"; sudo -u postgres dropdb --if-exists "$DB" >/dev/null 2>&1; exit 1; }
[ -n "$LAST" ] || fail "nusxa topilmadi"
sudo -u postgres dropdb --if-exists "$DB"
sudo -u postgres createdb "$DB" || fail "createdb"
sudo -u postgres pg_restore -d "$DB" --no-owner "$LAST" >/dev/null 2>&1 || fail "pg_restore $LAST"
COUNTS=$(sudo -u postgres psql -d "$DB" -Atc "select (select count(*) from accounts_student)||' oquvchi, '||(select count(*) from accounts_user)||' foydalanuvchi, '||(select count(*) from billing_payment)||' tolov'") || fail "sanash"
sudo -u postgres dropdb "$DB"
echo "OK $(date -Is) $(basename "$LAST"): $COUNTS" > "$D/RESTORE_TEST"
