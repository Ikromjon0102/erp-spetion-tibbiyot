#!/usr/bin/env bash
# One-time provisioning of a fresh Ubuntu 22.04/24.04 droplet for ERP (med/maktab) + Exam.
# Run as root ON THE DROPLET:  bash setup.sh
# Safe to re-run: existing users, DBs, env files and secrets are kept.
set -euo pipefail

ERP_DOMAIN="${ERP_DOMAIN:-med.spetion.uz}"
EXAM_DOMAIN="${EXAM_DOMAIN:-exam.spetion.uz}"
SECRETS=/root/.spetion-secrets
HERE="$(cd "$(dirname "$0")" && pwd)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y nginx postgresql postgresql-contrib python3-venv python3-dev build-essential libpq-dev \
  certbot python3-certbot-nginx ufw rsync fail2ban unattended-upgrades tesseract-ocr poppler-utils

# --- swap (2 GB) so a small droplet survives memory spikes
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# --- firewall
ufw allow OpenSSH && ufw allow 'Nginx Full' && ufw --force enable

# --- app user + dirs
id erp >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash erp
mkdir -p /var/www/erp/{app,data,media,staticfiles} /var/www/exam/{backend,frontend/dist,storage} /var/backups/spetion
chown -R erp:erp /var/www/erp /var/www/exam

# --- secrets (generated once)
touch "$SECRETS"; chmod 600 "$SECRETS"
gen() { grep -q "^$1=" "$SECRETS" || echo "$1=$(openssl rand -hex 24)" >> "$SECRETS"; }
gen ERP_DB_PASSWORD; gen EXAM_DB_PASSWORD; gen ERP_SECRET_KEY; gen EXAM_JWT_SECRET; gen ERP_API_KEY
set -a; . "$SECRETS"; set +a

# --- postgres
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='erp'" | grep -q 1 || sudo -u postgres psql -c "CREATE ROLE erp LOGIN PASSWORD '$ERP_DB_PASSWORD'"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='exam'" | grep -q 1 || sudo -u postgres psql -c "CREATE ROLE exam LOGIN PASSWORD '$EXAM_DB_PASSWORD'"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='erp'" | grep -q 1 || sudo -u postgres createdb -O erp erp
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='spetion_exam'" | grep -q 1 || sudo -u postgres createdb -O exam spetion_exam
# small-RAM tuning
cat > /etc/postgresql/conf.d-spetion.tmp <<'PG'
shared_buffers = 256MB
effective_cache_size = 768MB
work_mem = 8MB
maintenance_work_mem = 64MB
max_connections = 60
PG
PGCONF_DIR="$(ls -d /etc/postgresql/*/main/conf.d | head -1)"
mv /etc/postgresql/conf.d-spetion.tmp "$PGCONF_DIR/spetion.conf"
systemctl restart postgresql

# --- env files (never overwritten)
if [ ! -f /var/www/erp/.env ]; then
cat > /var/www/erp/.env <<ENV
SECRET_KEY=$ERP_SECRET_KEY
DEBUG=0
ALLOWED_HOSTS=$ERP_DOMAIN
CSRF_TRUSTED_ORIGINS=https://$ERP_DOMAIN
DB_NAME=erp
DB_USER=erp
DB_PASSWORD=$ERP_DB_PASSWORD
DB_HOST=localhost
EXAM_API_URL=https://$EXAM_DOMAIN
EXAM_API_KEY=$ERP_API_KEY
ENV
fi
if [ ! -f /var/www/exam/backend/.env ]; then
cat > /var/www/exam/backend/.env <<ENV
DATABASE_URL=postgresql+psycopg2://exam:$EXAM_DB_PASSWORD@localhost:5432/spetion_exam
JWT_SECRET=$EXAM_JWT_SECRET
STORAGE_BACKEND=local
LOCAL_STORAGE_DIR=/var/www/exam/storage
CELERY_EAGER=true
ERP_API_KEY=$ERP_API_KEY
# ANTHROPIC_API_KEY=   (copy from the old server if AI grading is used)
ENV
fi
chown erp:erp /var/www/erp/.env /var/www/exam/backend/.env; chmod 600 /var/www/erp/.env /var/www/exam/backend/.env

# --- systemd + nginx
install -m 644 "$HERE/erp.service" /etc/systemd/system/erp.service
install -m 644 "$HERE/exam-api.service" /etc/systemd/system/exam-api.service
install -m 644 "$HERE/exam-sweep.service" /etc/systemd/system/exam-sweep.service
sed "s/__ERP_DOMAIN__/$ERP_DOMAIN/g" "$HERE/nginx-erp.conf" > /etc/nginx/sites-available/erp
sed "s/__EXAM_DOMAIN__/$EXAM_DOMAIN/g" "$HERE/nginx-exam.conf" > /etc/nginx/sites-available/exam
ln -sf /etc/nginx/sites-available/erp /etc/nginx/sites-enabled/erp
ln -sf /etc/nginx/sites-available/exam /etc/nginx/sites-enabled/exam
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
systemctl daemon-reload

# --- nightly Postgres backup (14 days) + recurring expenses cron
install -m 755 "$HERE/backup.sh" /usr/local/bin/spetion-backup
cat > /etc/cron.d/spetion <<'CRON'
30 2 * * * root /usr/local/bin/spetion-backup
10 1 * * * erp cd /var/www/erp/app && /var/www/erp/venv/bin/python manage.py generate_recurring_expenses >> /var/www/erp/cron.log 2>&1
CRON

echo
echo "DONE. Secrets: $SECRETS"
echo "Next: from your computer run deploy/droplet/push.sh <droplet-ip>, then point DNS and run: certbot --nginx -d $ERP_DOMAIN -d $EXAM_DOMAIN"
