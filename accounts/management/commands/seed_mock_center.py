"""TEST (mock): o'quv markazga qo'shimcha filiallar va «Markaz direktori». Filial bo'yicha ko'rinishni sinash uchun.
`seed_mock_orgs` dan keyin, FAQAT sinov serverida. Qayta ishga tushirish xavfsiz (bor narsani qayta yaratmaydi).

    python manage.py seed_mock_center [--password demo1234]

Yaratiladi: «Filial 2 (Chilonzor)» va «Filial 3 (Yunusobod)» — har birida 2 guruh, 6 tadan o'quvchi (hisob va to'lovlar bilan),
bitta ustoz, dars jadvali, kirish/chiqish terminali, shu oy xarajatlari; «Markaz direktori» (+998 90 111-00-07) — markazning hamma filiali.
"""
import random
from datetime import time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.models import Group, Lesson, Subject, Teaching
from access.models import Device
from accounts.models import Student, User
from accounts.phone import to_digits
from billing.models import Payment
from billing.services import ensure_charges
from finance.models import Expense, ExpenseCategory
from org.models import Branch, Organization
from panel.models import Position, StaffProfile

CENTER = "O'quv markaz"
BRANCHES = {
    'Filial 2 (Chilonzor)': {
        'teacher': ('Jamshid', 'Tursunov', '+998 90 200-00-05', 'Matematika'),
        'groups': [('Matematika 7-sinf', 600000, [0, 2, 4], (14, 0), (16, 0)), ('IELTS 6.0', 900000, [1, 3, 5], (10, 0), (12, 0))],
        'students': ['Akmal Rasulov', 'Bekzod Ismoilov', 'Charos Hakimova', 'Diyora Salimova', 'Elyor Murodov', 'Feruza Qosimova',
                     'Gulnoza Aliyeva', 'Hasan Yoqubov', 'Iroda Karimova', 'Jahongir Nurmatov', 'Kamron Sodiqov', 'Lola Fayzullayeva'],
    },
    'Filial 3 (Yunusobod)': {
        'teacher': ('Malika', 'Rahimova', '+998 90 200-00-06', 'Ingliz tili'),
        'groups': [('Ingliz tili B1', 700000, [0, 2, 4], (8, 0), (10, 0)), ('Kids English', 500000, [1, 3], (15, 0), (16, 30))],
        'students': ['Madina Toshpulatova', 'Nodir Ergashev', 'Ozoda Rustamova', 'Parviz Hamroyev', 'Rayhona Usmonova', 'Sardor Mahmudov',
                     'Tohir Abdullayev', 'Umida Saidova', 'Vohid Rashidov', 'Xurshida Jo\'rayeva', 'Yulduz Mirzayeva', 'Ziyoda Komilova'],
    },
}
DIRECTOR = ('Markaz direktori', 'Rustam', 'Qodirov', '+998 90 111-00-07')


class Command(BaseCommand):
    help = "Sinov: o'quv markazga 2 ta qo'shimcha filial va markaz direktori"

    def add_arguments(self, parser):
        parser.add_argument('--password', default='demo1234')

    @transaction.atomic
    def handle(self, password, **opts):
        org = Organization.objects.filter(name=CENTER).first()
        if org is None:
            raise CommandError("Avval create_orgs va seed_mock_orgs")
        rng = random.Random(11)
        today = timezone.localdate()
        cat = {c.name: c for c in ExpenseCategory.objects.all()}
        cats = [cat.get(n) for n in ('Ijara', 'Kommunal', 'Xo\'jalik', 'Boshqa') if cat.get(n)] or [ExpenseCategory.objects.create(name='Boshqa')]

        def user(role, first, last, phone='', username=None):
            username = username or to_digits(phone)
            u, created = User.objects.get_or_create(username=username, defaults={'first_name': first, 'last_name': last, 'role': role, 'phone': phone})
            if created:
                u.set_password(password)
                u.save()
            return u

        made = []
        for bname, spec in BRANCHES.items():
            br, created = Branch.objects.get_or_create(organization=org, name=bname)
            if not created:
                continue
            made.append(bname)
            f, l, phone, subj_name = spec['teacher']
            t = user('teacher', f, l, phone)
            t.branches.set([br])
            subj, _ = Subject.objects.get_or_create(name=subj_name)
            students = []
            for gi, (gname, price, days, (h1, m1), (h2, m2)) in enumerate(spec['groups']):
                g = Group.objects.create(name=gname, branch=br, monthly_price=price)
                te = Teaching.objects.create(teacher=t, subject=subj, group=g)
                for d in days:
                    Lesson.objects.create(teaching=te, weekday=d, period=gi + 1, start=time(h1, m1), end=time(h2, m2), room=str(10 + gi))
                for full in spec['students'][gi * 6:(gi + 1) * 6]:
                    first, last = full.split(' ', 1)
                    su = user('student', first, last, username=f'mc-{to_digits(phone)}-{len(students)}')
                    students.append(Student.objects.create(user=su, group=g, branch=br))
            ensure_charges([s.pk for s in students], today)
            for s in students:                       # to'lovlar: ko'pchiligi to'lagan, ba'zilari qisman, ba'zilari qarzdor
                for ch in s.charges.filter(cancelled=False, amount__gt=0):
                    r = rng.random()
                    if r < .7 or (r < .85 and ch.month < today.replace(day=1)):
                        amount = ch.amount if r < .7 else ch.amount // 2
                        Payment.objects.create(student=s, amount=amount, paid_on=min(ch.month + timedelta(days=rng.randint(2, 12)), today),
                                               method=rng.choice(['cash', 'card']))
            for direction, label in (('in', 'Kirish'), ('out', 'Chiqish')):
                Device.objects.create(name=f'{bname}: {label}', direction=direction, branch=br, last_seen=timezone.now())
            for c in cats[:3]:
                Expense.objects.create(branch=br, category=c, date=today.replace(day=min(today.day, 3)), amount=rng.randint(8, 40) * 100000,
                                       payee='sinov xarajat')

        pos_name, f, l, phone = DIRECTOR
        base = Position.objects.filter(name='Direktor').first()
        pos, _ = Position.objects.get_or_create(name=pos_name, defaults={'default_perms': list(base.default_perms) if base else []})
        u = user('staff', f, l, phone)
        StaffProfile.objects.get_or_create(user=u, defaults={'position': pos, 'perms': list(pos.default_perms)})
        u.branches.set(list(Branch.objects.filter(organization=org, is_active=True)))
        self.stdout.write(self.style.SUCCESS(
            f"Yangi filiallar: {', '.join(made) or 'yo`q (oldin yaratilgan)'}. Markaz direktori: {phone} / {password} — "
            f"{Branch.objects.filter(organization=org).count()} ta filial"))
