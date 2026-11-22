"""Founderning tashkilotlarini yaratadi (mavjud bo'lsa tegmaydi): asosiy maktab, bog'cha, o'quv markaz.

Ranglar boshlang'ich: keyin Panel → Sozlamalar → Tashkilot va brend sahifasida o'zgartiriladi.
Ishlatish: python manage.py create_orgs
"""
from django.core.management.base import BaseCommand

from org.models import Branch, Organization

ORGS = [
    # nomi, qisqa nomi, turi, rang, taomnoma, filiallar
    ('Asosiy maktab', 'Asosiy maktab', 'school', '#1E3A8A', True, ['Asosiy']),
    ("Bog'cha", "Bog'cha", 'kindergarten', '#F97316', True, ['Asosiy']),
    ("O'quv markaz", 'Markaz', 'center', '#E53935', False, ['Filial 1']),
]


class Command(BaseCommand):
    help = "Asosiy maktab, bog'cha va o'quv markaz tashkilotlarini (agar yo'q bo'lsa) yaratadi"

    def handle(self, *args, **options):
        for name, short, kind, color, meals, branches in ORGS:
            org, created = Organization.objects.get_or_create(
                name=name, defaults={'short_name': short, 'kind': kind, 'brand_color': color, 'meals_enabled': meals})
            for b in branches:
                Branch.objects.get_or_create(organization=org, name=b)
            if options['verbosity'] > 0:
                self.stdout.write(f"{'yaratildi' if created else 'bor'}: {name} ({org.brand_color})")
