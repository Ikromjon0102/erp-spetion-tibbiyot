"""Spetion agent — oyna va tray (soat yonidagi ikonka). Yadro: core.py.

Birinchi ishga tushganda o'zini %LOCALAPPDATA%\\SpetionAgent ga ko'chiradi va Windows bilan birga ishga tushadigan qiladi
(HKCU\\...\\Run). Ikkinchi nusxa ochilsa — mavjud oynani ko'rsatadi va yopiladi.
"""
import logging
import os
import platform
import queue
import shutil
import socket
import subprocess
import sys
import threading
import tkinter as tk
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import messagebox, ttk

if sys.stdout is None:                     # oynali exe da konsol yo'q: print() yiqitmasin
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.spetion_agent import core  # noqa: E402
from tools.spetion_agent.core import APP_DIR, VERSION, Config, DeviceError, ServerError, Worker  # noqa: E402

TITLE = 'Spetion agent'
INSTANCE_PORT = 47615
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
log = logging.getLogger('spetion_agent')
lines = deque(maxlen=300)
emitted = [0]


class UiLog(logging.Handler):
    def emit(self, record):
        lines.append(self.format(record))
        emitted[0] += 1


def setup_logging():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%d.%m %H:%M:%S')
    fh = RotatingFileHandler(APP_DIR / 'agent.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    fh.setFormatter(fmt)
    ui = UiLog()
    ui.setFormatter(logging.Formatter('%(asctime)s  %(message)s', '%H:%M'))
    log.addHandler(fh)
    log.addHandler(ui)
    log.setLevel(logging.INFO)


def resource(name):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent.parent))
    return base / name


# ---- o'rnatish va bitta nusxa ------------------------------------------------------------------------------------------------

def installed_exe():
    return APP_DIR / 'SpetionAgent.exe'


def set_autostart(exe):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, 'SpetionAgent', 0, winreg.REG_SZ, f'"{exe}" --tray')


def remove_autostart():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, 'SpetionAgent')
    except OSError:
        pass


def install_if_needed():
    """exe yuklab olingan joydan ishga tushirilgan bo'lsa — doimiy joyga ko'chiradi va o'shani ishga tushiradi. True — davom etmaslik."""
    if not getattr(sys, 'frozen', False):
        return False
    me, target = Path(sys.executable).resolve(), installed_exe()
    if target.exists() and me == target.resolve():
        set_autostart(target)
        for leftover in (target.with_suffix('.old'), target.with_suffix('.new')):
            try:
                leftover.unlink()
            except OSError:
                pass
        return False
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if notify_running():                   # eski nusxa ishlab turibdi: to'xtatib, keyin almashtiramiz
        notify_running('quit')
        import time
        time.sleep(2)
    shutil.copy2(me, target)
    set_autostart(target)
    subprocess.Popen([str(target)], close_fds=True)
    return True


def notify_running(cmd='show'):
    try:
        with socket.create_connection(('127.0.0.1', INSTANCE_PORT), timeout=1) as s:
            s.sendall(cmd.encode())
        return True
    except OSError:
        return False


def listen_instance(q):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(('127.0.0.1', INSTANCE_PORT))
    except OSError:
        return None
    srv.listen(2)

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
                with conn:
                    q.put(conn.recv(16).decode(errors='ignore') or 'show')
            except OSError:
                return
    threading.Thread(target=loop, daemon=True).start()
    return srv


# ---- oyna -------------------------------------------------------------------------------------------------------------------

class App:
    def __init__(self, start_hidden=False):
        self.cfg = Config()
        self.worker = Worker(self.cfg)
        self.q = queue.Queue()
        self.root = tk.Tk()
        self.root.title(TITLE)
        self.root.geometry('860x560')
        self.root.minsize(720, 460)
        try:
            self.root.iconbitmap(str(resource('static/brand/favicon.ico')))
        except tk.TclError:
            pass
        self.root.protocol('WM_DELETE_WINDOW', self.hide)
        style = ttk.Style()
        style.configure('Big.TLabel', font=('Segoe UI', 13, 'bold'))
        style.configure('Code.TEntry', font=('Consolas', 18))
        self.body = ttk.Frame(self.root, padding=14)
        self.body.pack(fill='both', expand=True)
        self.render()
        if start_hidden and self.cfg.paired:
            self.root.withdraw()
        self.tray = None
        self.start_tray()
        threading.Thread(target=self.worker.run, daemon=True).start()
        self.root.after(1000, self.tick)

    # -- umumiy --
    def clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def render(self):
        self.clear()
        (self.main_view if self.cfg.paired else self.pair_view)()

    def hide(self):
        self.root.withdraw()

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit(self):
        self.worker.stop_event.set()
        self.worker.wake()
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    def start_tray(self):
        try:
            import pystray
            from PIL import Image
        except ImportError:
            return
        img = Image.open(resource('static/brand/logo/spetion-belgi-rangli.png')).resize((64, 64))
        menu = pystray.Menu(pystray.MenuItem('Ochish', lambda: self.q.put('show'), default=True),
                            pystray.MenuItem('Hozir yuborish', lambda: self.q.put('sync')),
                            pystray.MenuItem('Chiqish', lambda: self.q.put('quit')))
        self.tray = pystray.Icon('SpetionAgent', img, TITLE, menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def tick(self):
        while not self.q.empty():
            cmd = self.q.get()
            if cmd == 'show':
                self.show()
            elif cmd == 'sync':
                self.worker.wake(force_sync=True)
            elif cmd == 'quit':
                return self.quit()
        if self.worker.restart_requested:            # yangi versiya o'rnatildi: yangisi port bo'shashini kutib ishga tushadi
            subprocess.Popen([sys.executable, '--tray', '--after-update'], close_fds=True)
            return self.quit()
        if self.cfg.paired and hasattr(self, 'tree'):
            self.refresh_main()
        self.root.after(1500, self.tick)

    # -- ulash --
    def pair_view(self):
        f = self.body
        ttk.Label(f, text='Spetion agentini ulash', style='Big.TLabel').pack(anchor='w')
        ttk.Label(f, wraplength=760, justify='left', text=(
            "Bu dastur shu binodagi yuz tanish terminallariga o'quvchi va xodimlar rasmini avtomatik yuboradi.\n"
            "my.spetion.uz → Qurilmalar → «Ulash kodi olish» tugmasini bosing va chiqqan 8 raqamli kodni shu yerga kiriting.")
        ).pack(anchor='w', pady=(6, 14))
        code = tk.StringVar()
        e = ttk.Entry(f, textvariable=code, width=14, font=('Consolas', 20), justify='center')
        e.pack(anchor='w')
        e.focus_set()
        msg = ttk.Label(f, foreground='#b91c1c')
        url = tk.StringVar(value=self.cfg.get('server_url'))
        adv = ttk.Frame(f)
        ttk.Label(adv, text='Server:').pack(side='left')
        ttk.Entry(adv, textvariable=url, width=36).pack(side='left', padx=6)

        def go(*_):
            msg.config(text='Ulanmoqda…', foreground='#555')
            self.root.update_idletasks()
            try:
                data = core.AgentServer(url.get().strip() or core.DEFAULT_URL).pair(code.get(), platform.node())
            except ServerError as ex:
                msg.config(text=str(ex), foreground='#b91c1c')
                return
            self.cfg.set(server_url=url.get().strip() or core.DEFAULT_URL)
            self.cfg.set_key(data['key'], {'id': data['branch_id'], 'name': data['branch'], 'org': data['org']})
            self.worker.reset_server()
            self.worker.devices = []
            log.info('Ulandi: %s · %s', data['org'], data['branch'])
            self.render()
            self.worker.wake()
            self.map_dialog()
        e.bind('<Return>', go)
        ttk.Button(f, text='Ulash', command=go).pack(anchor='w', pady=10)
        msg.pack(anchor='w')
        ttk.Label(f, text=f'v{VERSION}', foreground='#888').pack(side='bottom', anchor='e')
        adv.pack(side='bottom', anchor='w')

    # -- asosiy --
    def main_view(self):
        f = self.body
        br = self.cfg.get('branch') or {}
        top = ttk.Frame(f)
        top.pack(fill='x')
        ttk.Label(top, text=f"{br.get('org', '')} · {br.get('name', '')}", style='Big.TLabel').pack(side='left')
        self.server_lbl = ttk.Label(top, text='')
        self.server_lbl.pack(side='right')

        pw = ttk.Frame(f)
        pw.pack(fill='x', pady=(10, 6))
        ttk.Label(pw, text='Terminal paroli (admin):').pack(side='left')
        self.pw_var = tk.StringVar()
        ttk.Entry(pw, textvariable=self.pw_var, show='•', width=22).pack(side='left', padx=6)
        ttk.Button(pw, text='Saqlash', command=self.save_password).pack(side='left')
        self.pw_lbl = ttk.Label(pw, text='saqlangan' if self.cfg.password else 'kiritilmagan', foreground='#555')
        self.pw_lbl.pack(side='left', padx=8)

        cols = ('dir', 'ip', 'state', 'count', 'note')
        self.tree = ttk.Treeview(f, columns=cols, height=7)
        for c, title, w in (('#0', 'Terminal (panel)', 150), ('dir', "Yo'nalish", 70), ('ip', 'IP', 110), ('state', 'Holat', 150),
                            ('count', 'Terminalda', 110), ('note', 'Oxirgi natija', 260)):
            self.tree.heading(c, text=title, anchor='w')
            self.tree.column(c, width=w, anchor='w', stretch=c == 'note')
        self.tree.pack(fill='x', pady=6)

        btns = ttk.Frame(f)
        btns.pack(fill='x')
        ttk.Button(btns, text='Terminallarni qidirish va biriktirish', command=self.map_dialog).pack(side='left')
        ttk.Button(btns, text='Hozir yuborish', command=lambda: self.worker.wake(force_sync=True)).pack(side='left', padx=6)
        self.sync_lbl = ttk.Label(btns, text='', foreground='#555')
        self.sync_lbl.pack(side='left', padx=8)
        ttk.Button(btns, text='Uzish', command=self.unpair).pack(side='right')

        ttk.Label(f, text='Jurnal', foreground='#555').pack(anchor='w', pady=(10, 0))
        self.logbox = tk.Text(f, height=10, font=('Consolas', 9), state='disabled', relief='flat', background='#f6f6f6')
        self.logbox.pack(fill='both', expand=True)
        ttk.Label(f, text=f'v{VERSION} · jurnal fayli: {APP_DIR / "agent.log"}', foreground='#888').pack(anchor='e')
        self._log_len = -1
        self.refresh_main()

    def refresh_main(self):
        st = self.worker.state
        ok = st['server_ok']
        self.server_lbl.config(text='● Serverga ulangan' if ok else f"● {st['server'] or 'Ulanmoqda…'}",
                               foreground='#15803d' if ok else '#b91c1c')
        self.sync_lbl.config(text='Yuborilmoqda…' if st['syncing'] else (f"Oxirgi tekshiruv: {st['last_sync']}" if st['last_sync'] else ''))
        mapped = self.cfg.get('terminals')
        self.tree.delete(*self.tree.get_children())
        for d in self.worker.devices:
            t = mapped.get(d['token'])
            s = st['terminals'].get(d['token'], {})
            if not t:
                state, ip = 'biriktirilmagan', '—'
            else:
                ip = t.get('ip') or '?'
                state = 'onlayn' if s.get('online') else (s.get('error') or 'tekshirilmoqda…')
            count = f"{s['users']} kishi / {s['faces']} yuz" if s.get('users') is not None else ''
            self.tree.insert('', 'end', text=d['name'], values=('Kirish' if d['direction'] == 'in' else 'Chiqish', ip, state, count,
                                                                  s.get('note', '')))
        if emitted[0] != self._log_len:
            self._log_len = emitted[0]
            self.logbox.config(state='normal')
            self.logbox.delete('1.0', 'end')
            self.logbox.insert('end', '\n'.join(lines))
            self.logbox.see('end')
            self.logbox.config(state='disabled')

    def save_password(self):
        pw = self.pw_var.get()
        if not pw:
            return
        ip = next((t['ip'] for t in self.cfg.get('terminals').values() if t.get('ip')), None)
        if ip:
            try:
                core.Client(core.Terminal(ip, pw)).user_count()
            except DeviceError as e:
                if not messagebox.askyesno(TITLE, f'{ip} terminali bu parolni qabul qilmadi:\n{e}\n\nBaribir saqlansinmi?'):
                    return
        self.cfg.set_password(pw)
        self.pw_var.set('')
        self.pw_lbl.config(text='saqlangan')
        self.worker._status_at.clear()
        self.worker.wake(force_sync=True)
        log.info('Terminal paroli saqlandi')

    def unpair(self):
        if messagebox.askyesno(TITLE, "Agent filialdan uzilsinmi? Qayta ulash uchun paneldan yangi kod kerak bo'ladi."):
            self.cfg.unpair()
            self.worker.reset_server()
            self.worker.devices = []
            log.info('Agent uzildi')
            self.render()

    # -- terminallarni biriktirish --
    def map_dialog(self):
        if not self.worker.devices:
            try:
                info = self.worker.server.devices()
                self.worker.devices = info['devices']
            except ServerError as e:
                messagebox.showerror(TITLE, str(e))
                return
        if not self.worker.devices:
            messagebox.showinfo(TITLE, "Panelda bu filial uchun terminal qo'shilmagan.\nAvval my.spetion.uz → Qurilmalar → «Qurilma qo'shish».")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title('Terminallarni biriktirish')
        dlg.geometry('720x420')
        dlg.transient(self.root)
        fr = ttk.Frame(dlg, padding=12)
        fr.pack(fill='both', expand=True)
        info = ttk.Label(fr, text='Tarmoqdagi terminallar qidirilmoqda…', wraplength=680, justify='left')
        info.pack(anchor='w')
        grid = ttk.Frame(fr)
        grid.pack(fill='x', pady=10)
        found = {}
        mapped = self.cfg.get('terminals')
        choices = {}

        def label(d):
            return f"{d['ip']}  ·  {d['mac']}  ·  {d.get('model') or 'Hikvision'}"

        def build():
            for w in grid.winfo_children():
                w.destroy()
            ordered = sorted(found.values(), key=lambda d: tuple(int(x) for x in d['ip'].split('.') if x.isdigit()))
            opts = ['(biriktirilmagan)'] + [label(d) for d in ordered]
            for i, dev in enumerate(self.worker.devices):
                ttk.Label(grid, text=f"{dev['name']} ({'kirish' if dev['direction'] == 'in' else 'chiqish'})").grid(row=i, column=0, sticky='w', pady=3)
                cur = mapped.get(dev['token'])
                var = choices.get(dev['token']) or tk.StringVar()
                if not var.get():
                    match = found.get(cur.get('mac')) if cur else None
                    var.set(label(match) if match else (f"{cur['ip']}  ·  {cur.get('mac') or '?'}  ·  (oldingi)" if cur else opts[0]))
                choices[dev['token']] = var
                cb = ttk.Combobox(grid, textvariable=var, values=opts, width=60, state='readonly')
                cb.grid(row=i, column=1, padx=8, pady=3)
            grid.columnconfigure(1, weight=1)

        def scan():
            def work():
                try:
                    res = core.sadp_probe()
                except OSError as e:
                    res, err = [], str(e)
                else:
                    err = ''
                self.root.after(0, lambda: done(res, err))
            threading.Thread(target=work, daemon=True).start()

        def done(res, err):
            if not dlg.winfo_exists():
                return
            terminals = [d for d in res if d.get('terminal')]
            hidden = len(res) - len(terminals) if terminals else 0     # kamera/registratorlar ro'yxatni to'ldirmasin
            for d in (terminals or res):
                found[d['mac']] = d
            info.config(text=(f"Topildi: {len(found)} ta terminal" + (f" ({hidden} ta kamera/registrator ko'rsatilmadi)" if hidden else '')
                              + ". Har bir panel terminaliga mos qurilmani tanlang "
                              "(qaysi biri qaysi ekanini IP yoki terminal ekranidagi manzil bo'yicha aniqlang)."
                              if found else "Terminal topilmadi. Windows «tarmoqqa ruxsat» so'ragan bo'lsa — ruxsat bering va qayta qidiring. "
                              "Yoki IP manzilini qo'lda qo'shing.") + (f'\n{err}' if err else ''))
            build()

        manual = ttk.Frame(fr)
        manual.pack(fill='x')
        ip_var = tk.StringVar()
        ttk.Label(manual, text="IP bo'yicha qo'shish:").pack(side='left')
        ttk.Entry(manual, textvariable=ip_var, width=18).pack(side='left', padx=6)

        def add_ip():
            ip = ip_var.get().strip()
            try:
                mac = core.mac_for_ip(ip, self.cfg.password)
            except DeviceError as e:
                messagebox.showerror(TITLE, str(e), parent=dlg)
                return
            found[mac or ip] = {'ip': ip, 'mac': mac, 'model': "qo'lda"}
            build()
        ttk.Button(manual, text="Qo'shish", command=add_ip).pack(side='left')
        ttk.Button(manual, text='Qayta qidirish', command=scan).pack(side='left', padx=6)

        def save():
            by_label = {label(d): d for d in found.values()}
            new = {}
            for token, var in choices.items():
                d = by_label.get(var.get())
                if d:
                    new[token] = {'ip': d['ip'], 'mac': d['mac'], 'label': next(x['name'] for x in self.worker.devices if x['token'] == token)}
                elif var.get().endswith('(oldingi)') and token in mapped:
                    new[token] = mapped[token]
            used = [t['mac'] or t['ip'] for t in new.values()]
            if len(used) != len(set(used)):
                messagebox.showerror(TITLE, 'Bitta qurilma ikki terminalga tanlangan.', parent=dlg)
                return
            self.cfg.set(terminals=new, last_stamp='')
            self.worker._status_at.clear()
            log.info('Terminallar biriktirildi: %s', ', '.join(f"{t['label']}={t['ip']}" for t in new.values()) or "yo'q")
            dlg.destroy()
            self.worker.wake(force_sync=True)
        bar = ttk.Frame(fr)
        bar.pack(fill='x', side='bottom')
        ttk.Button(bar, text='Saqlash', command=save).pack(side='right')
        ttk.Button(bar, text='Bekor qilish', command=dlg.destroy).pack(side='right', padx=6)
        build()
        scan()


def main():
    setup_logging()
    if '--uninstall' in sys.argv:
        notify_running('quit')
        remove_autostart()
        return
    if '--portable' not in sys.argv and install_if_needed():      # --portable: o'rnatmasdan (sinov uchun)
        return
    q = queue.Queue()
    srv = listen_instance(q)
    if srv is None and '--after-update' in sys.argv:      # eski nusxa yopilishini kutamiz
        import time
        for _ in range(20):
            time.sleep(0.5)
            srv = listen_instance(q)
            if srv:
                break
    if srv is None:                         # boshqa nusxa ishlab turibdi
        notify_running('show')
        return
    log.info('Agent ishga tushdi (v%s)', VERSION)
    app = App(start_hidden='--tray' in sys.argv)

    def relay():
        while not q.empty():
            app.q.put(q.get())
        try:
            app.root.after(500, relay)
        except tk.TclError:
            pass
    relay()
    app.root.mainloop()


if __name__ == '__main__':
    main()
