"""Yuz rasmlarini maktabdagi Hikvision terminallarga yuborish (maktab tarmog'idan ishga tushiriladi).

VPS maktabning ichki tarmog'iga yeta olmaydi, shuning uchun rasmlar shu skript orqali lokal kompyuterdan yuboriladi.
Batafsil: docs/terminallar.md

    set HIK_PASS=<terminal paroli>                       (PowerShell: $env:HIK_PASS='...')
    python tools/push_faces.py <papka> test              1 kishini 1-terminalga yuboradi (sinov)
    python tools/push_faces.py <papka> sync              hammasini hamma terminalga yuboradi (o'zgarmaganlari o'tkazib yuboriladi)
    python tools/push_faces.py <papka> prune             terminalda bor, lekin bo'lmasligi kerak odamlar ro'yxati (hech narsa o'chirmaydi)
    python tools/push_faces.py <papka> prune --apply     shularni terminaldan o'chiradi
    python tools/push_faces.py <papka> status            terminallardagi foydalanuvchi/yuz soni

<papka> — VPS bazasining NUSXASI: ichida db.sqlite3 va media/faces/ bo'lsin (docs/runbook.md dagi nusxa olish buyruqlari).
Asl loyiha bazasi (db.sqlite3) bilan ISHLATMANG: skript unga Device/FaceSync yozuvlarini qo'shadi.
Parol faqat HIK_PASS muhit o'zgaruvchisidan olinadi, hech qayerga yozilmaydi.
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MAC_RE = re.compile(r'(\d+\.\d+\.\d+\.\d+)\)?\s+(?:at\s+)?([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})')


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
    """Tarmoqdagi hamma manzilga ulanib ko'radi (ARP jadvali to'lishi uchun)."""
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
    """DHCP IP ni o'zgartirishi mumkin: terminal MAC manzili bo'yicha topiladi, topilmasa fayldagi IP ishlatiladi."""
    sweep(local_prefix())
    table = arp_table()
    for e in entries:
        ip = table.get(norm_mac(e['mac'])) if e.get('mac') else None
        if ip and ip != e.get('ip'):
            print(f"  ! {e['name']}: IP o'zgargan {e.get('ip')} -> {ip} (tools/terminals.json ni yangilang)")
        e['host'] = ip or e.get('ip')
        if not e['host']:
            sys.exit(f"{e['name']} topilmadi (MAC {e.get('mac')}). Terminal yoqilgan va shu tarmoqdami?")
    return entries


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('data_dir', help="VPS bazasi nusxasi: ichida db.sqlite3 va media/ bor papka")
    ap.add_argument('mode', choices=['test', 'sync', 'prune', 'status'])
    ap.add_argument('--apply', action='store_true', help='prune: ro\'yxatdagilarni haqiqatan o\'chiradi')
    ap.add_argument('--config', default=str(ROOT / 'tools' / 'terminals.json'))
    a = ap.parse_args()

    data = Path(a.data_dir).resolve()
    if not (data / 'db.sqlite3').is_file():
        sys.exit(f'{data}/db.sqlite3 topilmadi')
    own_db = ROOT / 'db.sqlite3'
    if own_db.exists() and (data / 'db.sqlite3').samefile(own_db):
        sys.exit("Loyihaning asl bazasi bilan ishlatmang: VPS bazasining NUSXASINI oling (docs/runbook.md)")
    password = os.environ.get('HIK_PASS')
    if not password:
        sys.exit("HIK_PASS muhit o'zgaruvchisi o'rnatilmagan (terminal paroli)")

    os.environ['SQLITE_PATH'] = str(data / 'db.sqlite3')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.conf import settings
    settings.MEDIA_ROOT = str(data / 'media')
    from access.hikvision import Client, DeviceError
    from access.models import Device
    from access.sync import eligible_users, sync_device

    from org.models import Branch
    entries = resolve(json.loads(Path(a.config).read_text(encoding='utf-8')))
    devices = []
    for e in entries:
        extra = {}
        if e.get('branch'):      # terminals.json: "branch": "<filial id>" yoki "<tashkilot nomi>/<filial nomi>"
            ref = str(e['branch'])
            if ref.isdigit():
                br = Branch.objects.filter(pk=int(ref)).first()
            else:
                org_name, _, br_name = ref.partition('/')
                br = Branch.objects.filter(organization__name=org_name.strip(), name=(br_name or 'Asosiy').strip()).first()
            if br is None:
                print(f"{e['name']}: filial topilmadi ({ref}) — o'tkazib yuborildi")
                continue
            extra['branch'] = br
        dev, _ = Device.objects.update_or_create(
            name=e['name'], defaults=dict(direction=e['direction'], host=e['host'], username='admin', password=password, is_active=True, **extra))
        if not dev.branch_id:
            print(f"OGOHLANTIRISH: {dev.name} filialga biriktirilmagan — unga HAMMA tashkilotdagi odamlar yuboriladi. "
                  f"terminals.json da \"branch\" ni kiriting.")
        devices.append(dev)

    print(f"Yuboriladigan odamlar (rasm va Face ID bor), jami: {len(eligible_users())}")

    for dev in devices:
        label = f'{dev.name} ({dev.host}, {dev.branch or "filialsiz"})'
        people = eligible_users(dev)              # faqat shu qurilma filialining o'quvchi, ustoz va xodimlari
        wanted = {u.device_id for u in people}
        if a.mode == 'test':
            if dev is not devices[0] or not people:
                continue
            u = people[0]
            print(f'{label}: sinov — {u.get_full_name()} ({u.device_id})', sync_device(dev, only_user_id=u.pk))
        elif a.mode == 'sync':
            print(f'{label}:', sync_device(dev), flush=True)
        elif a.mode == 'prune':
            client = Client(dev)
            try:
                extra = [(no, name) for no, name in client.list_users() if no not in wanted]
            except DeviceError as err:
                print(f'{label}: xato — {err}')
                continue
            print(f'{label}: ortiqcha {len(extra)} ta' + (':' if extra else ''))
            for no, name in extra:
                print(f'    {no}  {name}')
                if a.apply:
                    client.delete_user(no)
            if extra and a.apply:
                print('    -> terminaldan o\'chirildi')
        if a.mode in ('sync', 'prune', 'status') or (a.mode == 'test' and dev is devices[0]):
            try:
                users, faces = Client(dev).user_count()
                print(f'    terminalda: {users} foydalanuvchi, {faces} yuz')
            except DeviceError as err:
                print(f'    sonni olib bo\'lmadi: {err}')
    if a.mode == 'prune' and not a.apply:
        print("\nHech narsa o'chirilmadi. O'chirish uchun: prune --apply")


if __name__ == '__main__':
    main()
