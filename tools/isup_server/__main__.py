"""ISUP shlyuzini ishga tushirish (systemd: deploy/droplet/isup-gateway.service — M1 da qo'shiladi).

    python -m tools.isup_server --registry /var/www/erp/isup/registry.json            # haqiqiy SDK (M1 dan keyin)
    python -m tools.isup_server --fake --registry registry.json                       # SDK'siz: soxta backend, mahalliy sinov

Muhit o'zgaruvchilari: ISUP_API_TOKEN (ichki API kaliti, Django .env dagi bilan bir xil), ISUP_SDK_DIR (/opt/isup-sdk/lib),
ISUP_DJANGO_URL (http://127.0.0.1:8010), ISUP_DJANGO_HOST (my.spetion.uz), ISUP_FACE_BASE (https://my.spetion.uz/isup-face/),
ISUP_SPOOL (/var/lib/isup-gateway/spool.jsonl), ISUP_PUBLIC_HOST (terminal ko'radigan manzil).
"""
import argparse
import logging
import os
import signal
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.isup_server.backend import FakeBackend, HikSdkBackend  # noqa: E402
from tools.isup_server.events import Forwarder, http_poster  # noqa: E402
from tools.isup_server.faces import FaceStore  # noqa: E402
from tools.isup_server.gateway import Gateway, serve  # noqa: E402
from tools.isup_server.registry import Registry  # noqa: E402


def main(argv=None):
    env = os.environ.get
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--registry', required=True, help="JSON: [{device_id, isup_key, token, name}]")
    ap.add_argument('--fake', action='store_true', help='SDK o\'rniga soxta backend')
    ap.add_argument('--internal-port', type=int, default=7690)
    ap.add_argument('--public-port', type=int, default=7691)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    registry = Registry.from_json(a.registry)
    forwarder = Forwarder(registry, http_poster(env('ISUP_DJANGO_URL', 'http://127.0.0.1:8010'), env('ISUP_DJANGO_HOST', 'my.spetion.uz')),
                          env('ISUP_SPOOL', '/var/lib/isup-gateway/spool.jsonl'))
    backend = FakeBackend() if a.fake else HikSdkBackend(env('ISUP_SDK_DIR', '/opt/isup-sdk/lib'),
                                                         public_host=env('ISUP_PUBLIC_HOST', 'my.spetion.uz'))
    gw = Gateway(backend, registry, forwarder, FaceStore(), env('ISUP_FACE_BASE', 'https://my.spetion.uz/isup-face/'),
                 env('ISUP_API_TOKEN', ''))
    gw.start()
    servers = serve(gw, ('127.0.0.1', a.internal_port), ('127.0.0.1', a.public_port))
    logging.info('ISUP shlyuzi ishlayapti: %s terminal ro\'yxatda', len(registry))

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        while not stop.wait(60):
            gw.tick()
    except KeyboardInterrupt:
        pass
    for s in servers:
        s.shutdown()
    backend.stop()


if __name__ == '__main__':
    main()
