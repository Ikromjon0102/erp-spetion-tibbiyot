#!/usr/bin/env bash
# Windows agentining yangi versiyasini serverga joylash (agentlar 6 soat ichida o'zini yangilaydi; panelda «Agentni yuklab olish»).
#   python tools/spetion_agent/build.py && bash deploy/droplet/push_agent.sh <droplet-ip>
set -euo pipefail
HOST="${1:?droplet IP}"
KEY="${SSH_KEY:-$HOME/.ssh/spetion_deploy_ed25519}"
DIR="$(cd "$(dirname "$0")/../.." && pwd)/dist/agent"
[ -f "$DIR/SpetionAgent.exe" ] && [ -f "$DIR/SpetionAgent.json" ] || { echo "Avval: python tools/spetion_agent/build.py"; exit 1; }
OPTS=(-i "$KEY" -o ConnectTimeout=20 -o ServerAliveInterval=10)
for i in 1 2 3; do       # ~20 MB: sekin tarmoqda uzilishi mumkin
  scp "${OPTS[@]}" "$DIR/SpetionAgent.exe" "$DIR/SpetionAgent.json" root@"$HOST":/root/ && break
  [ "$i" = 3 ] && { echo "Yuklab bo'lmadi"; exit 1; }; sleep 10
done
want=$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['sha256'])" "$DIR/SpetionAgent.json")
ssh "${OPTS[@]}" root@"$HOST" "set -e; got=\$(sha256sum /root/SpetionAgent.exe | cut -c1-64); [ \"\$got\" = '$want' ] || { echo 'sha256 mos emas'; exit 1; }
  mkdir -p /var/www/erp/agent && mv /root/SpetionAgent.exe /root/SpetionAgent.json /var/www/erp/agent/ && chown -R erp:erp /var/www/erp/agent
  cat /var/www/erp/agent/SpetionAgent.json; echo"
echo "OK"
