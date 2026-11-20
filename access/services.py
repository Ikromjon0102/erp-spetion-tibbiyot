from datetime import timedelta

from django.utils import timezone

from .models import Device


def day_summaries(student, days=14):
    """So'nggi `days` kun uchun: maktabga kelgan (birinchi kirish) va ketgan (oxirgi chiqish) vaqt."""
    since = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    result = {}
    for e in student.access_events.filter(occurred_at__gte=since).order_by('occurred_at'):
        local = timezone.localtime(e.occurred_at)
        row = result.setdefault(local.date(), {'date': local.date(), 'arrived': None, 'left': None})
        if e.direction == Device.Direction.IN:
            row['arrived'] = row['arrived'] or local
            row['left'] = None      # chiqqandan keyin yana kirish skani — o'quvchi maktabda (oxirgi skan hal qiladi)
        else:
            row['left'] = local
    return [result[d] for d in sorted(result, reverse=True)]


def today_summary(student):
    today = timezone.localdate()
    return next((r for r in day_summaries(student, days=1) if r['date'] == today), None)
