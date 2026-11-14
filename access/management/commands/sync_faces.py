from django.core.management.base import BaseCommand

from access.sync import sync_all


class Command(BaseCommand):
    help = "Yuz rasmlarini Hikvision qurilmalarga yuboradi (faqat o'zgarganlarini). Cron/Task Scheduler bilan davriy ishga tushirish mumkin."

    def handle(self, *args, **opts):
        results = sync_all()
        if not results:
            self.stdout.write("Manzili kiritilgan faol qurilma yo'q")
        for pk, r in results.items():
            self.stdout.write(f"Qurilma #{pk}: yuborildi {r['sent']}, o'zgarmagan {r['skipped']}, o'chirildi {r['removed']}, xato {r['failed']}"
                              + (f" — {r['error']}" if r['error'] else ''))
