# Moving data from the old server (run only when you decide to cut over)

Old server: root@164.90.162.22 (keep it running until the new one is verified).

## Exam (PostgreSQL -> PostgreSQL)
```
ssh root@OLD "sudo -u postgres pg_dump -Fc spetion_exam" > exam.dump
scp exam.dump root@NEW:/tmp/
ssh root@NEW "sudo -u postgres pg_restore --clean --if-exists --no-owner -d spetion_exam /tmp/exam.dump && sudo -u postgres psql -d spetion_exam -c 'GRANT ALL ON ALL TABLES IN SCHEMA public TO exam; GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO exam;' && systemctl restart exam-api exam-sweep"
# uploaded question images (if STORAGE_BACKEND=local on the old server):
ssh root@OLD "tar -C /var/www/spetion-exam/backend -cf - local_storage" | ssh root@NEW "tar -C /var/www/exam -xf - && cp -rn /var/www/exam/local_storage/* /var/www/exam/storage/ && chown -R erp:erp /var/www/exam"
```
(Check LOCAL_STORAGE_DIR in the old .env for the real path.)

## ERP (old SQLite -> new PostgreSQL)
The old ERP is several migrations behind, so migrate the copy FIRST (locally or on NEW), then move rows:
```
scp root@OLD:/var/www/med-spetion/data/db.sqlite3 old.sqlite3
# on your computer, in the ERP repo (current code):
SQLITE_PATH=old.sqlite3 python manage.py migrate
SQLITE_PATH=old.sqlite3 python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e sessions --indent 1 > erp.json
# ship erp.json + media to NEW, then on NEW (as erp, env loaded):
python manage.py migrate && python manage.py loaddata erp.json
python manage.py create_orgs && python manage.py seed_menu     # only if not run with push.sh --first
rsync/tar the old media folder to /var/www/erp/media
```
Then: log in, check student/payment counts match the old panel, run `manage.py test`-free smoke checks (parent app, panel, exam login), only then switch DNS.

## Cutover
1. Lower DNS TTL a day before. 2. Final dump/restore (above) at a quiet hour. 3. Point `med.` and `exam.` A records to NEW. 4. `certbot --nginx -d med.spetion.uz -d exam.spetion.uz`. 5. Keep OLD for a week as fallback.
