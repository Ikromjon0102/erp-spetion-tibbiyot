"""Demo: terminallarning 'oxirgi signal'ini yangilaydi (Django'ni yuklamasdan, tez va yengil)."""
import sqlite3
import sys
from datetime import datetime, timezone

db = sys.argv[1] if len(sys.argv) > 1 else '/var/www/med-spetion/data/db.sqlite3'
con = sqlite3.connect(db)
con.execute('update access_device set last_seen=?', (datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f'),))
con.commit()
