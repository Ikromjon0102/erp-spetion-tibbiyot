"""SpetionAgent.exe yig'ish (Windows'da):  python tools/spetion_agent/build.py

Kerak: pip install -r tools/spetion_agent/requirements.txt
Natija: dist/agent/SpetionAgent.exe va SpetionAgent.json (versiya + sha256). Serverga: bash deploy/droplet/push_agent.sh <ip>
Versiya: core.py dagi VERSION (har yangi tarqatishda oshiring — agentlar o'zini shu bo'yicha yangilaydi).
"""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from tools.spetion_agent.core import VERSION  # noqa: E402

OUT = ROOT / 'dist' / 'agent'


def main():
    work = ROOT / 'build' / 'agent'
    shutil.rmtree(work, ignore_errors=True)
    sep = ';' if sys.platform == 'win32' else ':'
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
           '--name', 'SpetionAgent', '--icon', str(ROOT / 'static/brand/favicon.ico'),
           '--add-data', f"{ROOT / 'static/brand/favicon.ico'}{sep}static/brand",
           '--add-data', f"{ROOT / 'static/brand/logo/spetion-belgi-rangli.png'}{sep}static/brand/logo",
           '--paths', str(ROOT), '--hidden-import', 'pystray._win32',
           '--exclude-module', 'django', '--exclude-module', 'numpy',
           '--distpath', str(OUT), '--workpath', str(work), '--specpath', str(work),
           str(ROOT / 'tools/spetion_agent/app.py')]
    subprocess.run(cmd, check=True)
    exe = OUT / 'SpetionAgent.exe'
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    (OUT / 'SpetionAgent.json').write_text(json.dumps({'version': VERSION, 'sha256': digest}), encoding='utf-8')
    print(f'\nTayyor: {exe} ({exe.stat().st_size // 1024} KB), v{VERSION}, sha256 {digest[:16]}…')


if __name__ == '__main__':
    main()
