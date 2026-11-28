"""ISUP protokoli bilan ishlaydigan qatlam (backend).

* `HikSdkBackend` — Hikvision ISUP SDK (libHCISUPCMS.so + libHCISUPAlarm.so, Linux x64) ustidan ctypes. SDK repoda yo'q;
  founder uni o'z hisobi bilan yuklab oladi (docs/isup-server.md). Struct'lar SDK bilan keladigan header'lardan (incEn/*.h)
  yoziladi — taxmin qilinmaydi, shuning uchun hozircha faqat tekshiruv va aniq xato xabari (M1 bosqichi).
* `FakeBackend` — xotiradagi soxta terminallar: testlar va SDK'siz mahalliy sinov uchun.

Backend shlyuzni (`handler`) quyidagicha chaqiradi (SDK'da ular register/alarm callback'lari ichida bo'ladi):
    handler.on_register(device_id, info) -> bool     ENUM_DEV_ON: ro'yxatda yo'q device ID — False (rad)
    handler.on_auth(device_id) -> str | None         ENUM_DEV_AUTH: ISUP 5.0 kaliti (None — rad)
    handler.on_online(device_id)                     ENUM_DEV_SESSIONKEY dan keyin: ulanish tayyor
    handler.on_offline(device_id)                    ENUM_DEV_OFF yoki heartbeat to'xtagan
    handler.on_alarm(device_id, data)                EHOME_ISAPI_ALARM / EHOME_ALARM_ACS: JSON yoki XML matn
"""
import json
import logging
import os
from pathlib import Path

from access.hikvision import DeviceError

log = logging.getLogger('isup.backend')


class Backend:
    def start(self, handler):
        raise NotImplementedError

    def stop(self):
        pass

    def passthrough(self, device_id, method, path, body, timeout):
        """ISAPI so'rovi (NET_ECMS_ISAPIPassThrough). Javob matni; terminal ulanmagan bo'lsa DeviceError."""
        raise NotImplementedError


# ---- haqiqiy SDK ---------------------------------------------------------------------------------------------------------

REQUIRED_LIBS = ('libHCISUPCMS.so', 'libHCISUPAlarm.so')


class SdkMissing(RuntimeError):
    pass


class HikSdkBackend(Backend):
    """Portlar (docs/isup-server.md): CMS ro'yxatdan o'tish 7660 (TCP+UDP), alarm 7663/TCP (ISUP 5.0 — MQTT turi, 2),
    rasm serveri (SS) 6011 — faqat kerak bo'lsa. `public_host` — terminal ko'radigan manzil (my.spetion.uz yoki IP)."""

    def __init__(self, sdk_dir, listen_ip='0.0.0.0', public_host='my.spetion.uz', cms_port=7660, alarm_port=7663,
                 keepalive_sec=30, timeout_count=6):
        self.sdk_dir = Path(sdk_dir) if sdk_dir else None
        self.listen_ip, self.public_host = listen_ip, public_host
        self.cms_port, self.alarm_port = cms_port, alarm_port
        self.keepalive_sec, self.timeout_count = keepalive_sec, timeout_count

    def missing_libs(self):
        if not self.sdk_dir or not self.sdk_dir.is_dir():
            return list(REQUIRED_LIBS)
        return [name for name in REQUIRED_LIBS if not (self.sdk_dir / name).exists()]

    def start(self, handler):
        missing = self.missing_libs()
        if missing:
            raise SdkMissing(f"ISUP SDK topilmadi ({self.sdk_dir}): {', '.join(missing)}. "
                             "SDK'ni founder yuklab oladi va /opt/isup-sdk/lib ga qo'yadi (docs/isup-server.md).")
        if os.name != 'posix':
            raise SdkMissing('ISUP SDK faqat Linux x64 da ishlatiladi')
        # M1: ctypes.CDLL(libHCISUPCMS.so, RTLD_GLOBAL) -> NET_ECMS_SetSDKInitCfg (libcrypto/libssl yo'llari) -> NET_ECMS_Init ->
        #     NET_ECMS_StartListen(NET_EHOME_CMS_LISTEN_PARAM{7660, DEVICE_REGISTER_CB}) ; NET_EALARM_Init -> NET_EALARM_StartListen
        #     (7663, AlarmServerType=2). Callback'lar CFUNCTYPE obyektlari sifatida o'chirilmasdan saqlanadi (GC). Callback ichida
        #     faqat navbatga qo'yiladi — HTTP/IO yo'q. Struct'lar SDK header'laridan ko'chiriladi.
        raise NotImplementedError('HikSdkBackend: SDK header\'lari kelgach yoziladi (M1, docs/isup-server.md)')


# ---- soxta terminal (testlar) ---------------------------------------------------------------------------------------------

def _ok():
    return json.dumps({'statusCode': 1, 'statusString': 'OK', 'subStatusCode': 'ok'})


def _err(sub, code=4):
    return json.dumps({'statusCode': code, 'statusString': 'Invalid Operation', 'subStatusCode': sub})


class FakeTerminal:
    """Hikvision yuz terminalining ISAPI qismi (foydalanuvchi, yuz, son, qidiruv) — xotirada.
    `fetch(url) -> bytes | None` — terminal faceURL'dan rasmni yuklab olishi."""

    def __init__(self, device_id, isup_key, users=None, fetch=None, model='DS-K1T341CM'):
        self.device_id, self.isup_key, self.fetch, self.model = device_id, isup_key, fetch, model
        self.users = dict(users or {})          # employeeNo -> ism (eduschool yozganlari ham shu yerda)
        self.faces = {}                         # employeeNo -> jpeg
        self.requests = []

    def handle(self, method, path, body):
        self.requests.append((method, path))
        data = json.loads(body) if body else {}
        route = path.split('?', 1)[0]
        if (method, route) == ('GET', '/ISAPI/System/deviceInfo'):
            return f'<DeviceInfo><model>{self.model}</model><deviceID>{self.device_id}</deviceID></DeviceInfo>'
        if (method, route) == ('POST', '/ISAPI/AccessControl/UserInfo/Record'):
            u = data['UserInfo']
            if u['employeeNo'] in self.users:
                return _err('employeeNoAlreadyExist', 6)
            self.users[u['employeeNo']] = u['name']
            return _ok()
        if (method, route) == ('PUT', '/ISAPI/AccessControl/UserInfo/Modify'):
            u = data['UserInfo']
            if u['employeeNo'] not in self.users:
                return _err('employeeNoNotExist', 6)
            self.users[u['employeeNo']] = u['name']
            return _ok()
        if (method, route) == ('PUT', '/ISAPI/AccessControl/UserInfo/Delete'):
            for x in data['UserInfoDelCond']['EmployeeNoList']:
                self.users.pop(x['employeeNo'], None)
                self.faces.pop(x['employeeNo'], None)
            return _ok()
        if (method, route) == ('GET', '/ISAPI/AccessControl/UserInfo/Count'):
            return json.dumps({'UserInfoCount': {'userNumber': len(self.users), 'bindFaceUserNumber': len(self.faces)}})
        if (method, route) == ('POST', '/ISAPI/AccessControl/UserInfo/Search'):
            cond = data['UserInfoSearchCond']
            rows = sorted(self.users.items())
            pos, n = cond['searchResultPosition'], cond['maxResults']
            chunk = rows[pos:pos + n]
            return json.dumps({'UserInfoSearch': {
                'responseStatusStrg': 'MORE' if pos + n < len(rows) else 'OK', 'numOfMatches': len(chunk),
                'UserInfo': [{'employeeNo': no, 'name': name} for no, name in chunk]}})
        if (method, route) == ('PUT', '/ISAPI/Intelligent/FDLib/FDSearch/Delete'):
            for x in data.get('FPID', []):
                self.faces.pop(x['value'], None)
            return _ok()
        if (method, route) == ('POST', '/ISAPI/Intelligent/FDLib/FaceDataRecord'):
            if data.get('FPID') not in self.users:
                return _err('employeeNoNotExist', 6)
            jpeg = self.fetch(data.get('faceURL', '')) if self.fetch else None
            if not jpeg:
                return _err('downloadFaceFail', 6)
            self.faces[data['FPID']] = jpeg
            return _ok()
        return _err('notSupport')


class FakeBackend(Backend):
    def __init__(self):
        self.handler = None
        self.terminals = {}        # ulangan: device_id -> FakeTerminal

    def start(self, handler):
        self.handler = handler

    def connect(self, terminal):
        """Terminal ro'yxatdan o'tadi: device ID tekshiruvi, keyin kalit. Muvaffaqiyatli bo'lsa True."""
        if not self.handler.on_register(terminal.device_id, {'model': terminal.model}):
            return False
        key = self.handler.on_auth(terminal.device_id)
        if key is None or key != terminal.isup_key:
            log.warning('ISUP kaliti mos emas: %s', terminal.device_id)
            return False
        self.terminals[terminal.device_id] = terminal
        self.handler.on_online(terminal.device_id)
        return True

    def disconnect(self, device_id):
        if self.terminals.pop(device_id, None) is not None:
            self.handler.on_offline(device_id)

    def scan(self, device_id, employee_no, when, name=''):
        """Terminal yuzni tanidi -> ISUP alarm (HTTP listening bilan bir xil JSON)."""
        payload = {'ipAddress': '', 'dateTime': when, 'eventType': 'AccessControllerEvent',
                   'AccessControllerEvent': {'employeeNoString': employee_no, 'name': name, 'majorEventType': 5,
                                             'subEventType': 75}}
        return self.handler.on_alarm(device_id, json.dumps(payload).encode())

    def passthrough(self, device_id, method, path, body, timeout):
        t = self.terminals.get(device_id)
        if t is None:
            raise DeviceError(f"Qurilmaga ulanib bo'lmadi: {device_id} ISUP orqali ulanmagan")
        return t.handle(method, path, body)
