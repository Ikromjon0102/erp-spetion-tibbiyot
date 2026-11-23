from django.core.management.base import BaseCommand
from django.utils import timezone

from access.models import AccessEvent, PresenceNotice, earliest_leave_from, leave_from, org_of_student
from tgbot.signals import notify_presence


class Command(BaseCommand):
    help = ("Chiqish xabari vaqti kelgach, oxirgi skani «chiqish» bo'lgan (qaytmagan) o'quvchilarning ota-onasiga "
            "«maktabdan chiqdi» xabarini yuboradi. Har 5 daqiqada cron bilan ishga tushiriladi.")

    def handle(self, *args, **opts):
        now = timezone.localtime()
        if now.time() < earliest_leave_from():      # hech bir tashkilotda hali vaqt kelmagan
            return
        today = now.date()
        last = {}
        for e in (AccessEvent.objects.filter(occurred_at__date=today, student__isnull=False, student__user__is_active=True)
                  .select_related('student__user', 'student__branch__organization').order_by('occurred_at')):
            last[e.student_id] = e
        done = set(PresenceNotice.objects.filter(date=today, kind='left').values_list('student_id', flat=True))
        sent = 0
        for sid, e in last.items():
            if e.direction == 'out' and sid not in done and now.time() >= leave_from(org_of_student(e.student)):
                sent += notify_presence(e.student, 'left', e.occurred_at, today)
        if sent:
            self.stdout.write(f'Chiqish xabari: {sent} ta')
