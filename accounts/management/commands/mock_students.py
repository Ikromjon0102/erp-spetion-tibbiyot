from django.core.management.base import BaseCommand

from academics.models import Group
from accounts.models import Student, User

PREFIX = 'namuna_'  # namunaviy o'quvchilar loginlari shu bilan boshlanadi (keyin osongina o'chiriladi)
BOYS = ['Jasur', 'Sardor', 'Aziz', 'Bekzod', 'Doniyor', 'Otabek', 'Sherzod', 'Anvar', 'Rustam', 'Timur', 'Behruz', 'Ulugbek']
GIRLS = ['Madina', 'Sevara', 'Zilola', 'Malika', 'Nilufar', 'Dildora', 'Gulnora', 'Sabina', 'Shahnoza', 'Kamola', 'Mohira', 'Laylo']
SURNAMES = ['Karimov', 'Aliyev', 'Qodirov', 'Rahimov', 'Tursunov', 'Yusupov', 'Ergashev', 'Nazarov', 'Saidov', 'Abdullayev',
            'Hasanov', 'Ismoilov']


class Command(BaseCommand):
    help = "O'quvchisi yo'q sinflarga namuna (mock) o'quvchilar qo'shadi. --remove bilan ularni o'chiradi."

    def add_arguments(self, parser):
        parser.add_argument('--per-class', type=int, default=10)
        parser.add_argument('--remove', action='store_true', help="Barcha namunaviy o'quvchilarni o'chiradi")

    def handle(self, per_class, remove, **opts):
        if remove:
            n, _ = User.objects.filter(username__startswith=PREFIX).delete()
            self.stdout.write(self.style.SUCCESS(f"Namunaviy yozuvlar o'chirildi ({n} ta obyekt)."))
            return

        for gi, group in enumerate(Group.objects.order_by('name')):
            if group.students.exists():  # haqiqiy o'quvchilari bor sinfga tegmaymiz
                self.stdout.write(f'{group.name}: o\'quvchilar bor, o\'tkazib yuborildi')
                continue
            digits = ''.join(ch for ch in group.name if ch.isdigit()) or str(group.pk)
            for i in range(per_class):
                girl = i % 2 == 1
                first = (GIRLS if girl else BOYS)[(i // 2 + gi) % len(BOYS)]
                last = SURNAMES[(i * 5 + gi * 3) % len(SURNAMES)] + ('a' if girl else '')
                user = User(username=f'{PREFIX}{digits}_{i + 1:02d}', first_name=first, last_name=last,
                            role=User.Role.STUDENT)
                user.set_unusable_password()
                user.save()
                Student.objects.create(user=user, group=group)
            self.stdout.write(self.style.SUCCESS(f"{group.name}: {per_class} ta namunaviy o'quvchi qo'shildi"))
