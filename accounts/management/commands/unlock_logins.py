from django.core.cache import cache
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Xato urinishlar tufayli bloklangan barcha loginlarni ochadi."

    def handle(self, *args, **opts):
        cache.clear()
        self.stdout.write(self.style.SUCCESS("Barcha bloklar olib tashlandi."))
