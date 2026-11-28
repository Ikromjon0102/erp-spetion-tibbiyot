"""ISUP 5.0 shlyuzi (prototip): Hikvision terminallari maktab tarmog'idan serverga o'zi ulanadi, server ularni masofadan boshqaradi.

To'liq reja va qarorlar: docs/isup-server.md. Bu paket Django'ga bog'liq emas (faqat stdlib + access.hikvision.DeviceError) va
alohida systemd xizmati sifatida ishlaydi. Hikvision ISUP SDK (libHCISUPCMS.so va b.) repoda YO'Q: uni founder o'z hisobi bilan
yuklab oladi va serverga qo'yadi; SDK bo'lmasa ham FakeBackend bilan testlar va mahalliy sinov ishlaydi.

  registry.py  device ID -> ISUP kaliti va paneldagi qurilma tokeni
  events.py    terminal hodisasini (JSON/XML) mavjud /api/access/hikvision/<token>/ formatiga keltirish, yuborish, navbat
  isapi.py     ISAPI-over-ISUP mijozi (access.hikvision.Client bilan bir xil usullar), to'qnashuv hisobi
  faces.py     yuz rasmini terminal yuklab olishi uchun qisqa muddatli bir martalik manzil
  backend.py   SDK interfeysi: FakeBackend (testlar), HikSdkBackend (SDK kelgach yoziladi)
  gateway.py   hammasini bog'laydi + ichki HTTP API (127.0.0.1) va rasm berish
"""
