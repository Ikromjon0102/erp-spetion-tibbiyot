"""Hikvision yuz tanish terminali bilan ISAPI orqali ishlash (foydalanuvchi va yuz rasmini yuborish).

Eslatma: ISAPI yo'llari qurilma modeliga va dasturiy ta'minot versiyasiga qarab biroz farq qilishi mumkin;
ulanishni "Qurilmalar" sahifasidagi "Tekshirish" tugmasi bilan sinab ko'ring."""
import json

import requests
from requests.auth import HTTPDigestAuth

TIMEOUT = 12


class DeviceError(Exception):
    pass


def _check(resp, what):
    """ISAPI javobini tekshiradi; xato bo'lsa DeviceError ko'taradi."""
    if resp.status_code in (401, 403):
        raise DeviceError("Login yoki parol noto'g'ri")
    text = resp.text[:300]
    try:
        body = resp.json()
    except ValueError:
        body = None
    if resp.status_code >= 400:
        code = (body or {}).get('subStatusCode') or (body or {}).get('statusString') or text
        raise DeviceError(f'{what}: {code} (HTTP {resp.status_code})')
    if isinstance(body, dict) and body.get('statusCode') not in (None, 1):
        raise DeviceError(f"{what}: {body.get('subStatusCode') or body.get('statusString') or text}")
    return body


class Client:
    def __init__(self, device):
        scheme = 'https' if device.use_https else 'http'
        self.base = f'{scheme}://{device.host}:{device.port}'
        self.s = requests.Session()
        self.s.auth = HTTPDigestAuth(device.username, device.password)
        self.s.verify = False   # qurilmalarda odatda o'z-o'zidan imzolangan sertifikat

    def _fresh_session(self):
        s = requests.Session()
        s.auth = HTTPDigestAuth(self.s.auth.username, self.s.auth.password)
        s.verify = False
        self.s = s

    def _req(self, method, path, **kw):
        # Digest nonce bir necha so'rovdan keyin eskirib 401 berishi mumkin: yangi sessiya bilan qayta uriniladi
        for attempt in range(3):
            try:
                r = self.s.request(method, self.base + path, timeout=TIMEOUT, **kw)
            except requests.exceptions.RequestException as e:
                raise DeviceError(f"Qurilmaga ulanib bo'lmadi: {e.__class__.__name__}")
            if r.status_code != 401 or attempt == 2:
                return r
            self._fresh_session()
        return r

    def info(self):
        r = self._req('GET', '/ISAPI/System/deviceInfo')
        if r.status_code in (401, 403):
            raise DeviceError("Login yoki parol noto'g'ri")
        if r.status_code >= 400:
            raise DeviceError(f'HTTP {r.status_code}')
        return r.text

    def upsert_user(self, employee_no, name):
        body = {'UserInfo': {'employeeNo': employee_no, 'name': name[:32], 'userType': 'normal',
                             'Valid': {'enable': True, 'beginTime': '2020-01-01T00:00:00', 'endTime': '2037-12-31T23:59:59'},
                             'doorRight': '1', 'RightPlan': [{'doorNo': 1, 'planTemplateNo': '1'}]}}
        r = self._req('POST', '/ISAPI/AccessControl/UserInfo/Record?format=json', data=json.dumps(body),
                      headers={'Content-Type': 'application/json'})
        if r.status_code >= 400 and 'AlreadyExist' in r.text:
            r = self._req('PUT', '/ISAPI/AccessControl/UserInfo/Modify?format=json', data=json.dumps(body),
                          headers={'Content-Type': 'application/json'})
        _check(r, "Foydalanuvchini yozish")

    def set_face(self, employee_no, jpeg):
        # eski rasm bo'lsa o'chiriladi (xato bo'lsa e'tibor berilmaydi), keyin yangisi yoziladi
        self._req('PUT', '/ISAPI/Intelligent/FDLib/FDSearch/Delete?format=json&FDID=1&faceLibType=blackFD',
                  data=json.dumps({'FPID': [{'value': employee_no}]}), headers={'Content-Type': 'application/json'})
        meta = json.dumps({'faceLibType': 'blackFD', 'FDID': '1', 'FPID': employee_no})
        r = self._req('POST', '/ISAPI/Intelligent/FDLib/FaceDataRecord?format=json',
                      files={'FaceDataRecord': (None, meta, 'application/json'), 'FaceImage': ('face.jpg', jpeg, 'image/jpeg')})
        _check(r, 'Yuz rasmini yozish')

    def user_count(self):
        """(foydalanuvchilar soni, yuzi bog'langanlar soni)."""
        r = self._req('GET', '/ISAPI/AccessControl/UserInfo/Count?format=json')
        info = (_check(r, 'Foydalanuvchilar sonini olish') or {}).get('UserInfoCount') or {}
        return info.get('userNumber', 0), info.get('bindFaceUserNumber', 0)

    def list_users(self):
        """Qurilmadagi barcha foydalanuvchilar: [(employeeNo, ism), ...]."""
        out, pos = [], 0
        while True:
            body = {'UserInfoSearchCond': {'searchID': '1', 'searchResultPosition': pos, 'maxResults': 30}}
            r = self._req('POST', '/ISAPI/AccessControl/UserInfo/Search?format=json', data=json.dumps(body),
                          headers={'Content-Type': 'application/json'})
            data = (_check(r, "Foydalanuvchilar ro'yxatini olish") or {}).get('UserInfoSearch') or {}
            rows = data.get('UserInfo') or []
            out += [(str(x.get('employeeNo', '')), x.get('name', '')) for x in rows]
            if data.get('responseStatusStrg') != 'MORE' or not rows:
                return out
            pos += len(rows)

    def delete_user(self, employee_no):
        body = {'UserInfoDelCond': {'EmployeeNoList': [{'employeeNo': employee_no}]}}
        r = self._req('PUT', '/ISAPI/AccessControl/UserInfo/Delete?format=json', data=json.dumps(body),
                      headers={'Content-Type': 'application/json'})
        _check(r, "Foydalanuvchini o'chirish")
