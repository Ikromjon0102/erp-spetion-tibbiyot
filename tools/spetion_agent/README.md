# Spetion agent (Windows)

Har binodagi kompyuterga o'rnatiladigan kichik dastur. U o'sha binodagi Hikvision yuz terminallariga
o'quvchi va xodimlar rasmini **avtomatik** yuboradi. Server maktab tarmog'iga kira olmaydi, shuning uchun bu ishni agent qiladi.

- `core.py` — oynasiz qism: sozlama, maxfiy qiymatlarni shifrlash (Windows DPAPI), server API, terminallarni topish (SADP/ARP), ish tsikli.
- `app.py` — oyna (tkinter) va soat yonidagi ikonka (pystray). O'zini o'rnatadi, Windows bilan birga ishga tushadi, faqat bitta nusxa ishlaydi.
- `build.py` — `SpetionAgent.exe` ni yig'adi (PyInstaller). `deploy/droplet/push_agent.sh` — serverga joylaydi.
- Testlar: `access/test_agent_app.py` (yadro test serveri va soxta terminallar bilan), `access/test_agent_branch.py` (server API).

## O'rnatish (binoda, 5 daqiqa)
1. Panel → **Qurilmalar**: bino terminallari qo'shilgan bo'lsin (nomi, kirish/chiqish, filial).
2. Shu sahifada **«Ulash kodi olish»** (filialni tanlang) — 8 raqamli kod chiqadi (24 soat, bir marta).
3. Binodagi kompyuterda **«Agentni yuklab olish»** → `SpetionAgent.exe` ni ishga tushiring.
   Imzosiz dastur: Windows «noma'lum dastur» desa — **Batafsil → Baribir ishga tushirish**. Tarmoqqa ruxsat so'rasa — **Ruxsat berish**.
4. Kodni kiriting → **Ulash**. Agent tarmoqdagi terminallarni o'zi topadi: har bir panel terminaliga mos qurilmani tanlang → **Saqlash**.
5. **Terminal paroli** (admin) ni yozing → **Saqlash**. Rasmlar darhol yuborila boshlaydi, natija oynada va panelda ko'rinadi.

Shundan keyin hech narsa qilish shart emas: kompyuter yoqilganda agent o'zi ishga tushadi (soat yonidagi ikonka).
Oynani yopish dasturni to'xtatmaydi — ikonka orqali qayta ochiladi.

## Qanday ishlaydi
- Har daqiqa serverga «tirikman» + terminallar holati (IP, onlayn, terminaldagi odam/yuz soni). Panelda «onlayn» va terminal holati ko'rinadi.
- Server javobidagi filial izi o'zgarsa (yangi rasm, Face ID, chiqib ketgan o'quvchi) — barcha terminallarga sync. O'zgarmagan odam qayta yuborilmaydi.
- Xato qolsa 30 daqiqadan keyin qayta urinadi; har 6 soatda baribir to'liq tekshiradi.
- Terminal IP si o'zgarsa (DHCP) — MAC bo'yicha qayta topadi.
- Har 6 soatda yangi versiyani tekshiradi: sha256 mos kelsa o'zini almashtiradi va qayta ishga tushadi.
- Kalit va terminal paroli `%LOCALAPPDATA%\SpetionAgent\config.json` da DPAPI bilan shifrlangan (boshqa kompyuter yoki foydalanuvchi ocholmaydi).
  Jurnal: `%LOCALAPPDATA%\SpetionAgent\agent.log`.

## Yangi versiya chiqarish
1. `core.py` da `VERSION` ni oshiring.
2. `pip install -r tools/spetion_agent/requirements.txt` (bir marta), `python tools/spetion_agent/build.py`
3. `bash deploy/droplet/push_agent.sh 46.101.207.23` — agentlar 6 soat ichida yangilanadi.

Sinov uchun o'rnatmasdan: `SpetionAgent.exe --portable` (`SPETION_AGENT_DIR` bilan boshqa papka). O'chirish: `SpetionAgent.exe --uninstall`
(avto-ishga tushish olib tashlanadi), keyin `%LOCALAPPDATA%\SpetionAgent` papkasini o'chiring va panelda agentni «Uzish».
