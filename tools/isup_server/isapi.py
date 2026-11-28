"""ISAPI-over-ISUP: terminalga LAN'dagi bilan bir xil ISAPI so'rovlari, lekin ISUP ulanishi orqali (NET_ECMS_ISAPIPassThrough).

`PassthroughClient` access.hikvision.Client bilan bir xil usullarga ega (upsert_user, set_face, delete_user, user_count,
list_users, info), shuning uchun access/sync.py dagi sync mantiqi o'zgarmasdan ishlaydi — faqat mijoz tanlanadi.

Farq: yuz rasmi multipart bilan emas, `faceURL` bilan yuboriladi (terminal rasmni o'zi yuklab oladi, faces.py).
"""
import base64
import json
import unicodedata
import urllib.error
import urllib.request

from access.hikvision import DeviceError

ALLOWED_METHODS = ('GET', 'PUT', 'POST', 'DELETE')
TIMEOUT = 10
FACE_TIMEOUT = 25        # terminal rasmni yuklab olib, yuzni tahlil qilguncha


def check_request(method, path):
    """Faqat ISAPI yo'llari va oddiy metodlar (shlyuz ixtiyoriy narsani terminalga uzatmaydi)."""
    if method not in ALLOWED_METHODS:
        raise DeviceError(f"Metod ruxsat etilmagan: {method}")
    if not path.startswith('/ISAPI/') or any(c in path for c in ' \r\n\t'):
        raise DeviceError(f"Yo'l ruxsat etilmagan: {path[:80]}")


def _parse(text, what):
    """ISAPI javobi (JSON yoki XML ResponseStatus). Xato bo'lsa DeviceError."""
    text = (text or '').strip()
    if not text:
        return None
    if text.startswith('{'):
        try:
            body = json.loads(text)
        except ValueError:
            raise DeviceError(f'{what}: javob o\'qilmadi')
        if isinstance(body, dict) and body.get('statusCode') not in (None, 1):
            raise DeviceError(f"{what}: {body.get('subStatusCode') or body.get('statusString') or text[:200]}")
        return body
    if '<statusCode>' in text and '<statusCode>1</statusCode>' not in text:
        raise DeviceError(f'{what}: {text[:200]}')
    return text


class PassthroughClient:
    """`call(device_id, method, path, body, timeout) -> javob matni`; terminal ulanmagan bo'lsa DeviceError
    («Qurilmaga ulanib bo'lmadi ...» — sync shu terminalni to'xtatadi, boshqalarini davom ettiradi).
    `stage(jpeg) -> (url, done)` — rasmni vaqtincha manzilga qo'yish (shlyuz ichida FaceStore)."""

    def __init__(self, call, device_id, stage=None):
        self.call, self.device_id, self.stage = call, device_id, stage

    def _req(self, method, path, body=None, what='ISAPI', timeout=TIMEOUT):
        check_request(method, path)
        text = self.call(self.device_id, method, path, None if body is None else json.dumps(body, ensure_ascii=False), timeout)
        return _parse(text, what)

    def info(self):
        return self.call(self.device_id, 'GET', '/ISAPI/System/deviceInfo', None, TIMEOUT)

    def upsert_user(self, employee_no, name):
        body = {'UserInfo': {'employeeNo': employee_no, 'name': name[:32], 'userType': 'normal',
                             'Valid': {'enable': True, 'beginTime': '2020-01-01T00:00:00', 'endTime': '2037-12-31T23:59:59'},
                             'doorRight': '1', 'RightPlan': [{'doorNo': 1, 'planTemplateNo': '1'}]}}
        try:
            self._req('POST', '/ISAPI/AccessControl/UserInfo/Record?format=json', body, "Foydalanuvchini yozish")
        except DeviceError as e:
            if 'AlreadyExist' not in str(e) and 'alreadyExist' not in str(e):
                raise
            self._req('PUT', '/ISAPI/AccessControl/UserInfo/Modify?format=json', body, "Foydalanuvchini yozish")

    def set_face_url(self, employee_no, url):
        try:       # eski rasm bo'lsa o'chiriladi (yo'q bo'lsa xato — e'tibor berilmaydi)
            self._req('PUT', '/ISAPI/Intelligent/FDLib/FDSearch/Delete?format=json&FDID=1&faceLibType=blackFD',
                      {'FPID': [{'value': employee_no}]}, "Eski rasmni o'chirish")
        except DeviceError as e:
            if 'ulanib bo' in str(e):
                raise
        self._req('POST', '/ISAPI/Intelligent/FDLib/FaceDataRecord?format=json',
                  {'faceLibType': 'blackFD', 'FDID': '1', 'FPID': employee_no, 'faceURL': url},
                  'Yuz rasmini yozish', timeout=FACE_TIMEOUT)

    def set_face(self, employee_no, jpeg):
        if self.stage is None:
            raise DeviceError("Rasm manzili sozlanmagan (FaceStore yo'q)")
        url, done = self.stage(jpeg)
        try:
            self.set_face_url(employee_no, url)
        finally:
            done()

    def user_count(self):
        info = (self._req('GET', '/ISAPI/AccessControl/UserInfo/Count?format=json', what='Foydalanuvchilar sonini olish')
                or {}).get('UserInfoCount') or {}
        return info.get('userNumber', 0), info.get('bindFaceUserNumber', 0)

    def list_users(self):
        out, pos = [], 0
        while True:
            body = {'UserInfoSearchCond': {'searchID': '1', 'searchResultPosition': pos, 'maxResults': 30}}
            data = (self._req('POST', '/ISAPI/AccessControl/UserInfo/Search?format=json', body,
                              "Foydalanuvchilar ro'yxatini olish") or {}).get('UserInfoSearch') or {}
            rows = data.get('UserInfo') or []
            out += [(str(x.get('employeeNo', '')), x.get('name', '')) for x in rows]
            if data.get('responseStatusStrg') != 'MORE' or not rows:
                return out
            pos += len(rows)

    def delete_user(self, employee_no):
        self._req('PUT', '/ISAPI/AccessControl/UserInfo/Delete?format=json',
                  {'UserInfoDelCond': {'EmployeeNoList': [{'employeeNo': employee_no}]}}, "Foydalanuvchini o'chirish")

    def search_events(self, start, end, position=0, max_results=30):
        """Terminal jurnalidagi skanlar (internet uzilganda yo'qolganlarni tiklash uchun). start/end — ISO matn."""
        body = {'AcsEventCond': {'searchID': '1', 'searchResultPosition': position, 'maxResults': max_results,
                                 'major': 5, 'minor': 75, 'startTime': start, 'endTime': end}}
        return (self._req('POST', '/ISAPI/AccessControl/AcsEvent?format=json', body, 'Jurnal') or {}).get('AcsEvent') or {}


# ---- Django tomonidan foydalanish: shlyuzning ichki API'si orqali -------------------------------------------------------

class RemoteClient(PassthroughClient):
    """Django (access/sync.py) uchun: so'rovlar 127.0.0.1 dagi shlyuzga boradi. Rasm /face ga yuboriladi —
    shlyuz uni vaqtincha manzilga qo'yadi va terminalga faceURL beradi."""

    def __init__(self, base_url, api_token, device_id, urlopen=urllib.request.urlopen):
        self.base, self.api_token, self.urlopen = base_url.rstrip('/'), api_token, urlopen
        super().__init__(self._call, device_id)

    def _post(self, path, payload, timeout):
        req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(), method='POST',
                                     headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {self.api_token}'})
        try:
            with self.urlopen(req, timeout=timeout + 5) as resp:
                data = json.loads(resp.read() or b'{}')
        except urllib.error.HTTPError as e:
            try:
                data = json.loads(e.read() or b'{}')
            except ValueError:
                data = {}
            raise DeviceError(data.get('error') or f'Shlyuz: HTTP {e.code}')
        except (OSError, ValueError) as e:
            raise DeviceError(f"Qurilmaga ulanib bo'lmadi: ISUP shlyuzi javob bermadi ({e.__class__.__name__})")
        if not data.get('ok'):
            raise DeviceError(data.get('error') or 'Shlyuz xatosi')
        return data

    def _call(self, device_id, method, path, body, timeout):
        return self._post('/isapi', {'device_id': device_id, 'method': method, 'path': path, 'body': body,
                                     'timeout': timeout}, timeout).get('text', '')

    def set_face(self, employee_no, jpeg):
        self._post('/face', {'device_id': self.device_id, 'employee_no': employee_no,
                             'jpeg': base64.b64encode(jpeg).decode()}, FACE_TIMEOUT)


# ---- eduschool ma'lumotlarini himoya qilish -----------------------------------------------------------------------------

def _norm(name):
    s = unicodedata.normalize('NFKC', name or '').casefold()
    return ' '.join(s.replace("'", '').replace('`', '').replace('‘', '').replace('’', '').split())


def collision_report(terminal_users, wanted):
    """terminal_users: [(employeeNo, ism)] (terminalda bor); wanted: {employeeNo: ism} (biz yozmoqchi bo'lganlar).
    -> {'conflicts': [(no, terminaldagi ism, bizdagi ism)], 'foreign': [(no, ism)], 'same': [no]}

    conflicts — shu raqam terminalda BOSHQA odamda (eduschool raqamlashi bizniki bilan to'qnashgan): avtomatik
    yozilmaydi (aks holda begona odamning yozuvi va yuzi ustidan yoziladi), qo'lda hal qilinadi.
    foreign — terminalda bor, bizda yo'q: ISUP sync ularni HECH QACHON o'chirmaydi (faqat o'zimiz yozganlarni)."""
    on_terminal = {str(no): name for no, name in terminal_users}
    conflicts, same = [], []
    for no, ours in wanted.items():
        theirs = on_terminal.get(str(no))
        if theirs is None:
            continue
        if _norm(theirs) == _norm(ours[:32]):     # terminal ismni 32 belgigacha saqlaydi; ismsiz yozuv ham to'qnashuv
            same.append(str(no))
        else:
            conflicts.append((str(no), theirs, ours))
    foreign = [(no, name) for no, name in on_terminal.items() if no not in {str(k) for k in wanted}]
    return {'conflicts': sorted(conflicts), 'foreign': sorted(foreign), 'same': sorted(same)}
