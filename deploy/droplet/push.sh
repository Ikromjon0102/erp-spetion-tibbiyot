#!/usr/bin/env bash
# Run on YOUR computer (Git Bash): bash deploy/droplet/push.sh <droplet-ip> [--first]
# Ships ERP + Exam code (tar over ssh, no rsync needed), installs deps, migrates, restarts.
# --first: also runs the one-time ERP bootstrap (create_orgs, seed_menu) - do NOT use on later updates.
set -euo pipefail
HOST="${1:?usage: push.sh <droplet-ip> [--first]}"; FIRST="${2:-}"
SSH="ssh root@$HOST"
ERP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
EXAM_DIR="${EXAM_DIR:-$ERP_DIR/../exam-spetion}"

echo ">> build exam frontend"
(cd "$EXAM_DIR/frontend" && npm ci --silent && npm run build --silent)

echo ">> ship ERP"
tar -C "$ERP_DIR" --exclude='.git' --exclude='*.sqlite3' --exclude='db.backup*' --exclude='media' --exclude='__pycache__' \
    --exclude='*_credentials.csv' --exclude='tunl.exe' --exclude='datalar' --exclude='rasmlar' --exclude='staticfiles' -cf - . \
  | $SSH 'tar -C /var/www/erp/app -xf - && chown -R erp:erp /var/www/erp'

echo ">> ship Exam backend + frontend"
tar -C "$EXAM_DIR/backend" --exclude='__pycache__' --exclude='.env' --exclude='local_storage' -cf - . \
  | $SSH 'tar -C /var/www/exam/backend -xf -'
tar -C "$EXAM_DIR/frontend/dist" -cf - . | $SSH 'rm -rf /var/www/exam/frontend/dist/* && tar -C /var/www/exam/frontend/dist -xf - && chown -R erp:erp /var/www/exam'

echo ">> install + migrate on the droplet"
$SSH "FIRST='$FIRST' bash -s" <<'REMOTE'
set -euo pipefail
chown -R erp:erp /var/www/exam
[ -d /var/www/erp/venv ] || sudo -u erp python3 -m venv /var/www/erp/venv
[ -d /var/www/exam/venv ] || sudo -u erp python3 -m venv /var/www/exam/venv
sudo -u erp /var/www/erp/venv/bin/pip install -q -r /var/www/erp/app/requirements.txt
sudo -u erp /var/www/exam/venv/bin/pip install -q -r /var/www/exam/backend/requirements.txt
set -a; . /var/www/erp/.env; set +a
cd /var/www/erp/app
sudo -E -u erp /var/www/erp/venv/bin/python manage.py migrate --noinput
sudo -E -u erp /var/www/erp/venv/bin/python manage.py collectstatic --noinput >/dev/null
if [ "$FIRST" = "--first" ]; then
  sudo -E -u erp /var/www/erp/venv/bin/python manage.py create_orgs
  sudo -E -u erp /var/www/erp/venv/bin/python manage.py seed_menu
fi
cd /var/www/exam/backend
sudo -u erp /var/www/exam/venv/bin/alembic upgrade head
systemctl enable --now erp exam-api exam-sweep
systemctl restart erp exam-api exam-sweep
sleep 3; systemctl is-active erp exam-api exam-sweep
curl -s -o /dev/null -w "ERP local: %{http_code}\n" http://127.0.0.1:8010/ || true
curl -s -o /dev/null -w "Exam local: %{http_code}\n" http://127.0.0.1:8002/api/v1/auth/classes || true
REMOTE
echo "OK"
