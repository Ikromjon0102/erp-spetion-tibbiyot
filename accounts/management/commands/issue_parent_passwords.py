import csv

from django.core.management.base import BaseCommand

from accounts.models import User
from accounts.passwords import issue_temp_password


class Command(BaseCommand):
    help = ("Ota-onalarga bir martalik parol beradi va login/parollarni CSV ga yozadi. Ota-ona telefon raqami bilan kiradi "
            "va birinchi kirishda yangi parol qo'yadi. Odatda faqat paroli hali berilmaganlar uchun ishlaydi.")

    def add_arguments(self, parser):
        parser.add_argument('--phone', help="Faqat shu telefon raqamli ota-ona uchun (parolni qayta berish)")
        parser.add_argument('--all', action='store_true', help="Paroli bor ota-onalarga ham qayta bir martalik parol beradi")
        parser.add_argument('--output', default='parents_credentials.csv')

    def handle(self, phone, all, output, **opts):
        parents = User.objects.filter(role=User.Role.PARENT, is_active=True).prefetch_related('children__user')
        if phone:
            digits = ''.join(ch for ch in phone if ch.isdigit())
            parents = parents.filter(username=digits[-12:] if len(digits) >= 12 else '998' + digits)
        elif not all:
            parents = [p for p in parents if not p.has_usable_password()]

        rows = []
        for p in parents:
            kids = ', '.join(f'{c.user.last_name} {c.user.first_name} ({c.group.name if c.group else "—"})'
                             for c in p.children.all())
            rows.append((p.get_full_name(), kids, p.phone or p.username, issue_temp_password(p)))

        if not rows:
            self.stdout.write('Parol beriladigan ota-ona topilmadi.')
            return
        with open(output, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['Ota-ona', 'Farzand(lar)', 'Login (telefon)', 'Bir martalik parol'])
            w.writerows(rows)
        self.stdout.write(self.style.SUCCESS(
            f"{len(rows)} ta ota-onaga bir martalik parol berildi -> {output}\n"
            f"Faylni ota-onalarga yetkazib bo'lgach o'chiring. Birinchi kirishda ular yangi parol qo'yadi."))
