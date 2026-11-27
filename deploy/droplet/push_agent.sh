#!/usr/bin/env bash
# Windows agentining yangi versiyasini serverga joylash (agentlar 6 soat ichida o'zini yangilaydi, panelda yuklab olish).
#   python tools/spetion_agent/build.py && bash deploy/droplet/push_agent.sh <droplet-ip>
set -euo pipefail
HOST="${1:?droplet IP}"
KEY="${SSH_KEY:-$HOME/.ssh/spetion_deploy_ed25519}"
DIR="$(cd "$(dirname "$0")/../.." && pwd)/dist/agent"
[ -f "$DIR/SpetionAgent.exe" ] && [ -f "$DIR/SpetionAgent.json" ] || { echo "Avval: python tools/spetion_agent/build.py"; exit 1; }
tar -C "$DIR" -czf - SpetionAgent.exe SpetionAgent.json | ssh -i "$KEY" root@"$HOST" \
  'set -e; mkdir -p /var/www/erp/agent.tmp && tar -xzf - -C /var/www/erp/agent.tmp && chown -R erp:erp /var/www/erp/agent.tmp &&
   rm -rf /var/www/erp/agent.old && { [ -d /var/www/erp/agent ] && mv /var/www/erp/agent /var/www/erp/agent.old || true; } &&
   mv /var/www/erp/agent.tmp /var/www/erp/agent && cat /var/www/erp/agent/SpetionAgent.json && echo'
echo "OK"
