#!/usr/bin/env bash
# Zaxira nusxani Telegramga (tashqi joy) yuborish. `spetion-backup` oxirida chaqiriladi.
#
# - Har fayl GPG (AES-256) bilan SHIFRLANADI: ichida bolalarning shaxsiy ma'lumoti va yuz rasmlari bor. Parol: /root/.spetion-secrets
#   dagi BACKUP_PASSPHRASE — uni server tashqarisida (parol menejerida) saqlang, aks holda server yo'qolsa nusxani ochib bo'lmaydi.
# - Bot 50 MB dan katta fayl yubora olmaydi: katta fayl 45 MB lik qismlarga bo'linadi (.part01, .part02 ...).
# - Har kuni: ERP va exam bazalari; fayllar (rasmlar, cheklar): yakshanba — to'liq, boshqa kunlari — oxirgi 2 kunda o'zgarganlari.
# - Topish oson: izohda #zaxira #erp|#exam|#fayllar #dYYYY_MM_DD hashtaglari.
# Sozlama: /root/.spetion-alert -> ALERT_BOT_TOKEN, ALERT_CHAT_ID (yoki alohida BACKUP_CHAT_ID). Muvaffaqiyatli bo'lsa LAST_OFFSITE yoziladi.
set -uo pipefail
CONF=/root/.spetion-alert; SECRETS=/root/.spetion-secrets
[ -f "$CONF" ] && . "$CONF"
CHAT=${BACKUP_CHAT_ID:-${ALERT_CHAT_ID:-}}
[ -n "${ALERT_BOT_TOKEN:-}" ] && [ -n "$CHAT" ] || { echo "tg-backup: sozlanmagan, o'tkazib yuborildi"; exit 0; }
touch "$SECRETS"; chmod 600 "$SECRETS"
grep -q '^BACKUP_PASSPHRASE=' "$SECRETS" || echo "BACKUP_PASSPHRASE=$(openssl rand -base64 30 | tr -d '/+=')" >> "$SECRETS"
PASS=$(grep '^BACKUP_PASSPHRASE=' "$SECRETS" | cut -d= -f2-)

D=/var/backups/spetion; T=$(date +%F); TAG="d${T//-/_}"; WHO=${ERP_HOST:-$(hostname)}; DAY=$(date +%d.%m.%Y)
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT

send() {   # fayl, izoh
  curl -s -m 600 -F "chat_id=$CHAT" -F "document=@$1" -F "caption=$2" \
       "https://api.telegram.org/bot${ALERT_BOT_TOKEN}/sendDocument" | grep -q '"ok":true'
}

ship() {   # manba fayl, nomi, hashtag
  local src=$1 label=$2 tag=$3 base enc parts n i=0 name
  base=$(basename "$src"); enc="$W/$base.gpg"
  printf '%s' "$PASS" | gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 0 \
      --symmetric --cipher-algo AES256 -o "$enc" "$src" || return 1
  split -b 45m -d -a 2 "$enc" "$enc.p" && rm -f "$enc"
  parts=("$enc".p*); n=${#parts[@]}
  for p in "${parts[@]}"; do
    i=$((i + 1))
    if [ "$n" -gt 1 ]; then name="$base.gpg.part$(printf %02d "$i")"; else name="$base.gpg"; fi
    mv "$p" "$W/$name"
    send "$W/$name" "💾 $label · $WHO · $DAY · $i/$n
#zaxira #$tag #$TAG" || return 1
    rm -f "$W/$name"
  done
}

ok=1
ship "$D/erp-$T.dump" "ERP bazasi" erp || ok=0
ship "$D/exam-$T.dump" "Exam bazasi" exam || ok=0
if [ "$(date +%u)" = 7 ] || [ ! -f "$D/LAST_TG_FULL" ]; then
  if ship "$D/files-$T.tgz" "Fayllar (to'liq)" fayllar; then date -Is > "$D/LAST_TG_FULL"; else ok=0; fi
else
  (cd /var/www && find erp/app/media exam/storage -type f -mtime -2 2>/dev/null) > "$W/changed.txt"
  if [ -s "$W/changed.txt" ]; then
    tar -czf "$W/files-changed-$T.tgz" -C /var/www -T "$W/changed.txt" && ship "$W/files-changed-$T.tgz" "Fayllar (2 kunda o'zgarganlar)" fayllar || ok=0
  fi
fi
if [ "$ok" = 1 ]; then date -Is > "$D/LAST_OFFSITE"; echo "tg-backup: OK"; else echo "tg-backup: XATO"; exit 1; fi
