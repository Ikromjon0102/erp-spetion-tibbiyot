"""Founder bergan 14 kunlik maktab menyusini tashkilotga yuklaydi (taom nomlari; rasmlarni keyin panelda bir marta yuklaysiz).

Ishlatish:
    python manage.py seed_menu                       # taomnoma yoqilgan hamma maktab tashkilotlariga
    python manage.py seed_menu --org "Tibbiyot maktabi" [--force]

Menyusi allaqachon bor tashkilotga tegmaydi (--force bilan ustiga yozadi). Sikl hisobi bugundan 1-kun deb boshlanadi:
kerak bo'lsa panelda «Bugun sikldagi nechanchi kun» ni o'zgartiring.
"""
from django.core.management.base import BaseCommand, CommandError

from meals import seed
from meals.models import MealType, MenuEntry
from meals.services import get_plan, set_entry, split_dishes
from org.models import Organization


class Command(BaseCommand):
    help = "14 kunlik maktab menyusini yuklaydi"

    def add_arguments(self, parser):
        parser.add_argument('--org', help='Tashkilot nomi (bo\'sh bo\'lsa taomnoma yoqilgan hamma maktablar)')
        parser.add_argument('--force', action='store_true', help="Mavjud menyu ustiga yozadi")

    def handle(self, *args, **options):
        qs = Organization.objects.filter(name=options['org']) if options['org'] else Organization.objects.filter(kind='school', meals_enabled=True)
        orgs = list(qs)
        if not orgs:
            raise CommandError('Mos tashkilot topilmadi')
        for org in orgs:
            say = (lambda m: self.stdout.write(m)) if options['verbosity'] > 0 else (lambda m: None)
            if not org.meals_enabled:
                org.meals_enabled = True
                org.save(update_fields=['meals_enabled'])
            get_plan(org)
            if MenuEntry.objects.filter(organization=org).exists() and not options['force']:
                say(f'{org.name}: menyu bor, o\'tkazib yuborildi (--force bilan ustiga yoziladi)')
                continue
            types = list(MealType.objects.filter(organization=org).order_by('order'))
            lunch, snack = types[0], types[1] if len(types) > 1 else None
            for day in range(1, 15):
                set_entry(org, day, lunch, split_dishes(seed.LUNCH[day]))
                if snack is not None:
                    text = seed.SNACK[day]
                    set_entry(org, day, snack, split_dishes(text or ''), not_served=text is None)
            say(f'{org.name}: 14 kunlik menyu yuklandi')
