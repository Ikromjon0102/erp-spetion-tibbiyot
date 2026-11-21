"""Takroriy xarajatlarni (ijara, kommunal...) oy uchun yozadi. Qayta ishga tushirish xavfsiz: oyda bir marta.

Cron namunasi (har oyning 1-kuni): 0 6 1 * *  python manage.py generate_recurring_expenses
"""
from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone

from finance.models import RecurringExpense


class Command(BaseCommand):
    help = "Takroriy xarajatlarni berilgan (yoki joriy) oy uchun yozadi"

    def add_arguments(self, parser):
        parser.add_argument('--month', help='YYYY-MM (bo\'sh bo\'lsa joriy oy)')

    def handle(self, *args, **options):
        if options['month']:
            y, m = (int(x) for x in options['month'].split('-'))
            month = date(y, m, 1)
        else:
            month = timezone.localdate().replace(day=1)
        made = sum(bool(r.create_for(month)) for r in RecurringExpense.objects.select_related('branch', 'category'))
        self.stdout.write(f'{month:%Y-%m}: {made} ta xarajat yozildi')
