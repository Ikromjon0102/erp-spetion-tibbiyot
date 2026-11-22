"""YUK SINOVI uchun katta hajmli TEST ma'lumot (~4000 o'quvchi, ota-onalar, ustozlar, xodimlar, to'lov, xarajat). FAQAT sinov bazasida!

    SQLITE_PATH=scale.sqlite3 python manage.py migrate
    SQLITE_PATH=scale.sqlite3 python manage.py create_orgs
    SQLITE_PATH=scale.sqlite3 python manage.py seed_scale [--students 4000]

Hamma narsa bulk_create bilan (parol hash'i bitta, shuning uchun tez). Maqsad — ro'yxatlar va hisobotlar tezligini o'lchash."""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.models import Group
from accounts.models import Student, User
from billing.models import BillingSettings, Discount, Payment, StudentDiscount
from billing.services import ensure_charges
from finance.models import Expense, ExpenseCategory
from org.models import Branch, Organization

FIRST = ['Ali', 'Vali', 'Aziz', 'Bobur', 'Sardor', 'Jasur', 'Timur', 'Otabek', 'Anvar', 'Farhod', 'Madina', 'Zarina', 'Laylo', 'Malika',
         'Sevara', 'Dilnoza', 'Nigora', 'Kamola', 'Feruza', 'Munisa', 'Nodira', 'Sabina', 'Dilfuza', 'Mohira']
LAST = ['Karimov', 'Aliyev', 'Rahimov', 'Nazarov', 'Yusupov', 'Saidov', 'Hamidov', 'Normatov', 'Ergashev', 'Tursunov', 'Qodirov',
        'Sobirov', 'Ismoilov', 'Abdullayev', 'Xolmatov', 'Mirzayev', 'Ochilov', 'Hasanov', 'Yoqubov', 'Ahmedov']

# tashkilot -> (o'quvchi ulushi, oylik narx, [filial nomlari], guruhlar soni filialga)
PLAN = {
    'Tibbiyot maktabi': (0.11, 2_500_000, ['Asosiy'], 22),
    'Asosiy maktab': (0.12, 1_500_000, ['Asosiy'], 24),
    "O'quv markaz": (0.74, 600_000, ['Filial 1', 'Filial 2', 'Filial 3', 'Filial 4', 'Filial 5'], 28),
    "Bog'cha": (0.03, 1_200_000, ['Asosiy'], 4),
}


class Command(BaseCommand):
    help = "Yuk sinovi uchun ~4000 o'quvchilik TEST ma'lumot yaratadi"

    def add_arguments(self, p):
        p.add_argument('--students', type=int, default=4000)

    @transaction.atomic
    def handle(self, *args, **o):
        if User.objects.filter(username__startswith='sc_').exists():
            raise CommandError("Allaqachon yaratilgan (sc_ foydalanuvchilar bor).")
        rng = random.Random(7)
        total = o['students']
        pw = make_password('demo1234')
        today = timezone.localdate()
        month = today.replace(day=1)
        n_user = 0

        def mk_user(role, first, last, phone='', **kw):
            nonlocal n_user
            n_user += 1
            from accounts.phone import to_digits
            return User(username=f'sc_{role[:1]}{n_user}', password=pw, role=role, first_name=first, last_name=last, phone=phone,
                        phone_digits=to_digits(phone) if phone else '', **kw)

        orgs = {org.name: org for org in Organization.objects.all()}
        if not orgs:
            raise CommandError("Avval: python manage.py create_orgs")
        grp_by_branch, students_plan = {}, []
        for name, (share, price, branch_names, per_branch) in PLAN.items():
            org = orgs[name]
            cfg = BillingSettings.get(org)
            cfg.monthly_price, cfg.billing_start = price, today.replace(month=9, day=1) if today.month >= 9 else today.replace(year=today.year - 1, month=9, day=1)
            cfg.save()
            for bn in branch_names:
                br, _ = Branch.objects.get_or_create(organization=org, name=bn)
                groups = Group.objects.bulk_create([Group(name=f'{org.short_name[:6]}-{br.pk}-{i + 1}', branch=br) for i in range(per_branch)])
                grp_by_branch[br.pk] = (br, groups)
                students_plan += [(br, groups)] * round(total * share / len(branch_names))
        self.stdout.write(f"Guruhlar: {sum(len(g) for _, g in grp_by_branch.values())}, o'quvchilar rejasi: {len(students_plan)}")

        # --- o'quvchilar va ota-onalar
        stu_users = [mk_user('student', rng.choice(FIRST), rng.choice(LAST)) for _ in students_plan]
        User.objects.bulk_create(stu_users, batch_size=500)
        stu_users = list(User.objects.filter(username__startswith='sc_s').order_by('pk'))
        students = [Student(user=u, branch=br, group=rng.choice(groups)) for u, (br, groups) in zip(stu_users, students_plan)]
        Student.objects.bulk_create(students, batch_size=500)
        students = list(Student.objects.filter(user__username__startswith='sc_s').order_by('pk'))

        n_par = int(len(students) * 0.8)
        parents = [mk_user('parent', rng.choice(FIRST), rng.choice(LAST), phone=f'+998 9{rng.randint(0, 9)} {rng.randint(100, 999)}-{rng.randint(10, 99)}-{rng.randint(10, 99)}')
                   for _ in range(n_par)]
        for i, p in enumerate(parents):          # telefon takrorlanmasin
            p.phone = f'+998 9{i % 10} {100 + i // 10 % 900}-{10 + i // 9000 % 90}-{10 + i % 90}'
            p.phone_digits = ''.join(ch for ch in p.phone if ch.isdigit())
            p.username = p.phone_digits
        User.objects.bulk_create(parents, batch_size=500)
        parents = list(User.objects.filter(role='parent', username__regex=r'^\d+$').order_by('pk'))
        through = Student.parents.through
        links = [through(student_id=s.pk, user_id=parents[i % len(parents)].pk) for i, s in enumerate(students[:int(len(students) * 0.92)])]
        through.objects.bulk_create(links, batch_size=1000, ignore_conflicts=True)

        # --- chegirmalar: ~8% — 10%, ~5% — 25%, ~3% — grant
        discs = {}
        for org in orgs.values():
            for nm, pct in (('10%', 10), ('25%', 25), ('Grant', 100)):
                discs[(org.pk, nm)], _ = Discount.objects.get_or_create(organization=org, name=nm, defaults={'percent': pct})
        sd = []
        for s in students:
            r = rng.random()
            nm = '10%' if r < .08 else '25%' if .08 <= r < .13 else 'Grant' if .13 <= r < .16 else None
            if nm:
                sd.append(StudentDiscount(student=s, discount=discs[(s.branch.organization_id, nm)]))
        StudentDiscount.objects.bulk_create(sd, batch_size=1000)

        # --- hisoblar va to'lovlar
        ensure_charges([s.pk for s in students], today)
        pays = []
        from billing.models import Charge
        for ch in Charge.objects.filter(cancelled=False, amount__gt=0).iterator(chunk_size=5000):
            r = rng.random()
            if r < .68:
                amount = ch.amount
            elif r < .78:
                amount = ch.amount // 2
            else:
                continue
            when = min(ch.month + timedelta(days=rng.randint(2, 20)), today)
            pays.append(Payment(student_id=ch.student_id, amount=amount, paid_on=when, receipt_no=f'SC{len(pays):07d}'))
        Payment.objects.bulk_create(pays, batch_size=2000)

        # --- ustozlar va xodimlar
        teachers = [mk_user('teacher', rng.choice(FIRST), rng.choice(LAST), phone=f'+998 91 {200 + i // 90}-{10 + i % 90}-{10 + i % 70}') for i in range(220)]
        for i, t in enumerate(teachers):
            t.username = t.phone_digits
        User.objects.bulk_create(teachers, batch_size=300)
        teachers = list(User.objects.filter(role='teacher', username__regex=r'^\d+$', phone__startswith='+998 91').order_by('pk'))
        tb = User.branches.through
        brs = [b for b, _ in grp_by_branch.values()]
        tb.objects.bulk_create([tb(user_id=t.pk, branch_id=brs[i % len(brs)].pk) for i, t in enumerate(teachers)], ignore_conflicts=True)

        # --- xarajatlar: oyiga har filialga bir nechta
        cats = {c.name: c for c in ExpenseCategory.objects.all()} or {'Ijara': ExpenseCategory.objects.create(name='Ijara')}
        cat_list = list(cats.values())
        exps = []
        for back in range(4):
            d = (month - timedelta(days=30 * back)).replace(day=5)
            for b in brs:
                for c in cat_list[:6]:
                    exps.append(Expense(branch=b, category=c, date=d, amount=rng.randint(3, 30) * 100_000, payee='sinov'))
        Expense.objects.bulk_create(exps, batch_size=1000)
        self.stdout.write(self.style.SUCCESS(
            f"Tayyor: {len(students)} o'quvchi, {len(parents)} ota-ona, {len(teachers)} ustoz, {Charge.objects.count()} hisob, {len(pays)} to'lov, {len(exps)} xarajat"))
