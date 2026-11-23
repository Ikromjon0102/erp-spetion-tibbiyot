#!/usr/bin/env bash
# Har 5 daqiqada: ERP va exam javob beradimi, disk/xotira, zaxira yangiligi, tiklash sinovi. Holat O'ZGARGANDA Telegramga xabar
# (muammo paydo bo'lsa va tuzalsa). Sozlama: /root/.spetion-alert  ->  ALERT_BOT_TOKEN=...  ALERT_CHAT_ID=...
set -uo pipefail
CONF=/root/.spetion-alert; STATE=/var/lib/spetion-health; mkdir -p "$STATE"
[ -f "$CONF" ] && . "$CONF"
HOST=$(hostname)
problems=()
code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' -H "Host: ${ERP_HOST:-localhost}" http://127.0.0.1:8010/login/)
[ "$code" = 200 ] || problems+=("ERP javob bermayapti (HTTP $code)")
code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' http://127.0.0.1:8002/api/v1/health)
[ "$code" = 200 ] || problems+=("Exam javob bermayapti (HTTP $code)")
disk=$(df --output=pcent / | tail -1 | tr -dc '0-9'); [ "$disk" -lt 85 ] || problems+=("Disk ${disk}% to'lgan")
avail=$(free -m | awk '/^Mem:/{print $7}'); [ "$avail" -gt 80 ] || problems+=("Xotira kam: ${avail} MB bo'sh")
last=/var/backups/spetion/LAST_OK
if [ ! -f "$last" ] || [ $(( $(date +%s) - $(stat -c %Y "$last") )) -gt $((26*3600)) ]; then problems+=("Zaxira nusxa 26 soatdan beri yozilmagan"); fi
rt=/var/backups/spetion/RESTORE_TEST
[ -f "$rt" ] && grep -q '^FAIL' "$rt" && problems+=("Tiklash sinovi xato: $(cut -c1-120 "$rt")")

msg=$(printf '%s\n' "${problems[@]:-}" | sed '/^$/d')
# qisqa uzilish (masalan yangilanishda xizmat qayta ishga tushishi) xabar bermasin: holat ketma-ket ikki tekshiruvda bir xil bo'lsagina qabul qilinadi
seen=$(cat "$STATE/seen" 2>/dev/null || true); echo "$msg" > "$STATE/seen"
[ "$msg" = "$seen" ] || exit 0
prev=$(cat "$STATE/last" 2>/dev/null || true)
if [ "$msg" != "$prev" ]; then
  echo "$msg" > "$STATE/last"
  if [ -n "$msg" ]; then text="⚠️ $HOST: muammo
$msg"; else text="✅ $HOST: hammasi joyida"; fi
  echo "$(date -Is) $text" >> "$STATE/log"
  if [ -n "${ALERT_BOT_TOKEN:-}" ] && [ -n "${ALERT_CHAT_ID:-}" ]; then
    curl -s -m 10 "https://api.telegram.org/bot${ALERT_BOT_TOKEN}/sendMessage" --data-urlencode "chat_id=${ALERT_CHAT_ID}" --data-urlencode "text=${text}" >/dev/null || true
  fi
fi
exit 0
