"""Yuz rasmlarini maktabdagi Hikvision terminallarga yuborish — maktab tarmog'idagi kompyuterdan.

Server (my.spetion.uz) maktabning ichki tarmog'iga yeta olmaydi, shuning uchun bu skript:
  1) serverdan «shu terminalda kim bo'lishi kerak» ro'yxatini va rasmlarni oladi (API, baza nusxasi kerak emas),
  2) terminallarga ISAPI orqali yuboradi,
  3) natijani serverga qaytaradi — panelda «hammasi yuborilgan / N ta xato» to'g'ri ko'rinadi.

Kerakli muhit o'zgaruvchilari (parollar hech qayerga yozilmaydi):
    HIK_PASS              terminal admin paroli
    SPETION_AGENT_TOKEN   server API kaliti (serverdagi .env dagi FACE_AGENT_TOKEN bilan bir xil)
    SPETION_URL           ixtiyoriy, standart https://my.spetion.uz

PowerShell:
    $env:HIK_PASS = Read-Host "Terminal paroli"
    $env:SPETION_AGENT_TOKEN = Read-Host "API kaliti"
    python tools/push_faces.py status      terminallardagi foydalanuvchi/yuz soni
    python tools/push_faces.py test        1 kishini 1-terminalga (sinov)
    python tools/push_faces.py sync        hammasini (o'zgarmaganlari o'tkazib yuboriladi)
    python tools/push_faces.py prune       terminalda bor, lekin bo'lmasligi kerak odamlar ro'yxati (hech narsa o'chirmaydi)
    python tools/push_faces.py prune --apply

Terminallar ro'yxati: tools/terminals.json (nomi panelda «Qurilmalar»dagi nom bilan bir xil bo'lsin; bir xil nom bir nechta
filialda bo'lsa "branch": "<filial id>" qo'shing). Terminal MAC manzili bo'yicha topiladi (IP o'zgarib tursa ham).
Faqat Python va `requests` kerak (Django o'rnatilmagan kompyuterda ham ishlaydi).
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from access.hikvision import Client, DeviceError  # noqa: E402  (faqat requests ishlatadi, Django kerak emas)

MAC_RE = re.compile(r'(\d+\.\d+\.\d+\.\d+)\)?\s+(?:at\s+)?([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})')
FATAL = ('ulanib bo', 'parol')      # terminalga umuman ulanib bo'lmasa — shu terminalni to'xtatamiz


class Terminal:
    """hikvision.Client kutadigan maydonlar (panel Device modeli o'rniga)."""
    def __init__(self, host, password, port=80, use_https=False):
        self.host, self.port, self.use_https, self.username, self.password = host, port, use_https, 'admin', password


class Server:
    def __init__(self, url, token):
        self.url = url.rstrip('/') + '/api/access/agent'
        self.s = requests.Session()
        self.s.headers['Authorization'] = f'Bearer {token}'

    def _get(self, path, **kw):
        r = self.s.get(self.url + path, timeout=30, **kw)
        if r.status_code == 401:
            sys.exit("Server API kaliti noto'g'ri (SPETION_AGENT_TOKEN)")
        r.raise_for_status()
        return r

    def devices(self):
        return self._get('/devices/').json()['devices']

    def manifest(self, token):
        return self._get(f'/manifest/{token}/').json()

    def photo(self, user_id):
        return self._get(f'/photo/{user_id}/').content

    def report(self, token, payload):
        r = self.s.post(f'{self.url}/report/{token}/', data=json.dumps(payload), headers={'Content-Type': 'application/json'}, timeout=60)
        r.raise_for_status()
        return r.json()


# ---- terminalni tarmoqda topish (DHCP IP ni o'zgartirishi mumkin: MAC bo'yicha) ----------------------------------------

def norm_mac(mac):
    return mac.lower().replace('-', ':')


def local_prefix():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.0.2.1', 9))
        return s.getsockname()[0].rsplit('.', 1)[0]
    finally:
        s.close()


def sweep(prefix):
    def probe(i):
        try:
            socket.create_connection((f'{prefix}.{i}', 80), timeout=0.5).close()
        except OSError:
            pass
    with ThreadPoolExecutor(64) as ex:
        list(ex.map(probe, range(1, 255)))


def arp_table():
    out = subprocess.run(['arp', '-a'], capture_output=True, text=True).stdout
    return {norm_mac(m.group(2)): m.group(1) for m in MAC_RE.finditer(out)}


def resolve(entries):
    sweep(local_prefix())
    table = arp_table()
    for e in entries:
        ip = table.get(norm_mac(e['mac'])) if e.get('mac') else None
        if ip and ip != e.get('ip'):
            print(f"  ! {e['name']}: IP o'zgargan {e.get('ip')} -> {ip} (tools/terminals.json ni yangilang)")
        e['host'] = ip or e.get('ip')
    return entries


# ---- asosiy ish ---------------------------------------------------------------------------------------------------------

def sync_terminal(server, dev, client, only_one=False):
    m = server.manifest(dev['token'])
    results, removed = [], []
    sent = skipped = failed = 0
    for p in m['people']:
        if p['synced'] and not only_one:
            skipped += 1
            continue
        try:
            jpeg = server.photo(p['user_id'])
            if p.get('old_employee_no'):                       # Face ID o'zgargan: eski yozuv olib tashlanadi
                client.delete_user(p['old_employee_no'])
            client.upsert_user(p['employee_no'], p['name'])
            client.set_face(p['employee_no'], jpeg)
        except DeviceError as e:
            if any(f in str(e) for f in FATAL):
                raise
            results.append({'user_id': p['user_id'], 'employee_no': p['employee_no'], 'ok': False, 'error': str(e)})
            failed += 1
            print(f"    xato: {p['name']} ({p['employee_no']}) — {e}")
        except requests.RequestException as e:
            results.append({'user_id': p['user_id'], 'employee_no': p['employee_no'], 'ok': False, 'error': f'rasm olinmadi: {e}'})
            failed += 1
        else:
            results.append({'user_id': p['user_id'], 'employee_no': p['employee_no'], 'digest': p['digest'], 'ok': True})
            sent += 1
        if only_one:
            break
    if not only_one:
        for r in m['remove']:                                    # rasmi olib tashlangan / nofaol bo'lganlar
            try:
                client.delete_user(r['employee_no'])
            except DeviceError as e:
                if any(f in str(e) for f in FATAL):
                    raise
            removed.append(r['user_id'])
    note = f"Maktab kompyuteridan: yuborildi {sent}, o'zgarmagan {skipped}, o'chirildi {len(removed)}, xato {failed}"
    server.report(dev['token'], {'results': results, 'removed': removed, 'note': '' if only_one else note})
    return note


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=['test', 'sync', 'prune', 'status'])
    ap.add_argument('--apply', action='store_true', help="prune: ro'yxatdagilarni haqiqatan o'chiradi")
    ap.add_argument('--config', default=str(ROOT / 'tools' / 'terminals.json'))
    a = ap.parse_args()

    password, token = os.environ.get('HIK_PASS'), os.environ.get('SPETION_AGENT_TOKEN')
    if not password:
        sys.exit("HIK_PASS o'rnatilmagan (terminal paroli)")
    if not token:
        sys.exit("SPETION_AGENT_TOKEN o'rnatilmagan (server API kaliti)")
    server = Server(os.environ.get('SPETION_URL', 'https://my.spetion.uz'), token)

    remote = server.devices()
    entries = resolve(json.loads(Path(a.config).read_text(encoding='utf-8')))
    pairs = []
    for e in entries:
        cand = [d for d in remote if d['name'] == e['name'] and (not e.get('branch') or str(d['branch_id']) == str(e['branch']))]
        if len(cand) != 1:
            print(f"{e['name']}: panelda {'topilmadi' if not cand else 'bir nechta (terminals.json ga branch qo`shing)'} — o'tkazib yuborildi")
            continue
        if not e.get('host'):
            print(f"{e['name']}: tarmoqda topilmadi (MAC {e.get('mac')}) — terminal yoqilganmi?")
            continue
        pairs.append((e, cand[0]))

    for i, (e, dev) in enumerate(pairs):
        label = f"{e['name']} ({e['host']}, {dev['branch'] or 'filialsiz'})"
        client = Client(Terminal(e['host'], password))
        try:
            if a.mode == 'test':
                if i:
                    continue
                print(f'{label}: sinov (1 kishi) —', sync_terminal(server, dev, client, only_one=True))
            elif a.mode == 'sync':
                print(f'{label}:', sync_terminal(server, dev, client), flush=True)
            elif a.mode == 'prune':
                wanted = {p['employee_no'] for p in server.manifest(dev['token'])['people']}
                extra = [(no, name) for no, name in client.list_users() if no not in wanted]
                print(f'{label}: ortiqcha {len(extra)} ta' + (':' if extra else ''))
                for no, name in extra:
                    print(f'    {no}  {name}')
                    if a.apply:
                        client.delete_user(no)
                if extra and a.apply:
                    print("    -> terminaldan o'chirildi")
            users, faces = client.user_count()
            print(f'    terminalda: {users} foydalanuvchi, {faces} yuz')
        except DeviceError as err:
            print(f'{label}: xato — {err}')
    if a.mode == 'prune' and not a.apply:
        print("\nHech narsa o'chirilmadi. O'chirish uchun: prune --apply")


if __name__ == '__main__':
    main()
