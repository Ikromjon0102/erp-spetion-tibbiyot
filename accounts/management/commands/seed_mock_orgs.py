"""TEST (mock) ma'lumotlar: 4 tashkilotning har birida bittadan farzand o'qiydigan ota-ona, hamma rollar uchun namunaviy hisoblar,
dars jadvali, baho, davomat, to'lov, e'lon, xarajat, oylik va taomnoma. Haqiqiy odamlar ma'lumoti ishlatilmaydi.
FAQAT sinov serveriga (haqiqiy ma'lumot ko'chirilgunicha). Ishlatish:

    python manage.py create_orgs && python manage.py seed_menu     # avval tashkilotlar va menyu
    python manage.py seed_mock_orgs --password demo1234 [--link-exam]

--link-exam: exam platformasidagi shu farzandlarni (ism bo'yicha) ota-ona ilovasiga bog'laydi (EXAM_API_URL/KEY sozlangan bo'lishi kerak).
Qayta ishga tushirsa: "admin" bor bo'lsa ham --force kerak bo'lmaydi, lekin ota-ona allaqachon bor bo'lsa to'xtaydi."""
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.constants import PERIODS
from academics.models import Group, Lesson, Subject, Teaching
from access.models import AccessEvent, Device
from accounts.face_ids import next_teacher_id
from accounts.models import Student, User
from accounts.phone import to_digits
from accounts.student_import import _unique_username
from billing.models import BillingSettings, Payment
from billing.services import billed_months, ensure_charges
from finance.models import Expense, ExpenseCategory, RecurringExpense, SalaryRule
from journal.models import Attendance, Grade, Homework
from notices.models import Announcement
from org.models import Organization
from panel.models import Position, StaffProfile

PARENT_PHONE = '+998 90 218-57-07'

# tashkilot nomi -> (guruh nomi, oylik narx, guruh narxi, asosiy farzand, sinfdoshlar, fanlar, hafta kunlari, dars soatlari)
ORGS = {
    'Tibbiyot maktabi': ('9-Med', 2500000, None, ('Madina', 'Karimova', True),
                         [('Zarina', 'Yusupova'), ('Sardor', 'Nazarov'), ('Laylo', 'Hamidova'), ('Jasur', 'Saidov'), ('Malika', 'Normatova')],
                         ['Biologiya', 'Kimyo', 'Matematika'], [0, 1, 2, 3, 4, 5], [1, 2, 3]),
    'Asosiy maktab': ('7-A', 1500000, None, ('Aziz', 'Karimov', False),
                      [('Timur', 'Rahimov'), ('Sevara', 'Aliyeva'), ('Bobur', 'Ergashev'), ('Dilnoza', 'Tursunova'), ('Anvar', 'Qodirov')],
                      ['Matematika', 'Ona tili', 'Ingliz tili'], [0, 1, 2, 3, 4], [4, 5, 6]),
    "O'quv markaz": ('Ingliz tili A2', 600000, 700000, ('Dilnoza', 'Karimova', True),
                     [('Nigora', 'Mirzayeva'), ('Otabek', 'Sobirov'), ('Kamola', 'Ismoilova'), ('Farhod', 'Abdullayev'), ('Feruza', 'Xolmatova')],
                     ['Ingliz tili', 'Matematika'], [0, 2, 4], [1, 2]),       # haftada 3 kun, 2 soatdan
    "Bog'cha": ('Quyoshcha guruhi', 1200000, None, ('Bobur', 'Karimov', False),
                [('Doniyor', 'Aliyev'), ('Sabina', 'Rahimova'), ('Behruz', 'Tursunov'), ('Munisa', 'Yusupova'), ('Nodira', 'Nazarova')],
                ['Savod', 'Hisob', 'Rasm chizish'], [0, 1, 2, 3, 4], [1, 2, 3]),
}
# ism, familiya, telefon, fan(lar), qaysi tashkilotlarda
TEACHERS = [
    ('Sanjar', 'Yoqubov', '+998 90 200-00-01', ['Matematika'], ['Tibbiyot maktabi', 'Asosiy maktab']),
    ('Mohira', 'Hasanova', '+998 90 200-00-02', ['Biologiya', 'Kimyo'], ['Tibbiyot maktabi']),
    ('Nilufar', 'Karimova', '+998 90 200-00-03', ['Ingliz tili', 'Ona tili'], ['Asosiy maktab', "O'quv markaz"]),
    ('Dilfuza', 'Ochilova', '+998 90 200-00-04', ['Savod', 'Hisob', 'Rasm chizish', 'Matematika'], ["Bog'cha", "O'quv markaz"]),
]
# lavozim, ism, familiya, telefon, qaysi tashkilotlar (None = hammasi)
STAFF = [
    ('Maktab egasi', 'Bahodir', 'Raximov', '+998 90 111-00-01', None),
    ('Direktor', 'Dilshod', 'Normatov', '+998 90 111-00-02', ['Asosiy maktab']),
    ('Hisobchi', 'Barno', 'Ahmedova', '+998 90 111-00-03', None),
    ('Reception', 'Sevinch', 'Normurodova', '+998 90 111-00-04', ["O'quv markaz"]),
    ('Zavxoz', 'Anvar', 'Xudoyberdiyev', '+998 90 111-00-05', ['Asosiy maktab', "Bog'cha"]),
    ("Zam (o'quv ishlari)", 'Gulnora', 'Abdurahmonova', '+998 90 111-00-06', ['Tibbiyot maktabi']),
]
HOMEWORK = ["Darslikdagi 12-mavzuni o'qing va savollarga yozma javob bering.", "5 ta misol yeching.", "Mavzu bo'yicha qisqa referat (1 bet).", "Lug'at so'zlarini yodlang."]


class Command(BaseCommand):
    help = "Sinov serveri uchun to'qima ma'lumotlar (4 tashkilot, hamma rollar, 4 farzandli ota-ona)"

    def add_arguments(self, parser):
        parser.add_argument('--password', default='demo1234', help="Hamma sinov hisoblar paroli")
        parser.add_argument('--link-exam', action='store_true', help="Exam platformasidagi shu o'quvchilarni bog'lash")

    def handle(self, password, link_exam, **opts):
        if User.objects.filter(phone_digits=to_digits(PARENT_PHONE)).exists():
            raise CommandError("Sinov ota-onasi allaqachon bor (bu buyruq bir marta ishlaydi).")
        missing = [n for n in ORGS if not Organization.objects.filter(name=n).exists()]
        if missing:
            raise CommandError(f"Avval `create_orgs` ishlating; topilmadi: {', '.join(missing)}")
        self.rng = random.Random(7)
        self.password = password
        self.creds = []
        with transaction.atomic():
            self.build()
        if link_exam:
            self.link_exam()
        self.report()

    # ------------------------------------------------------------------ yaratish
    def user(self, role, first, last, phone='', username=None, password=True, **kw):
        digits = to_digits(phone)
        u = User(username=username or digits, first_name=first, last_name=last, role=role, phone=phone, **kw)
        u.set_password(self.password) if password else u.set_unusable_password()
        u.save()
        return u

    def build(self):
        today = timezone.localdate()
        orgs = {n: Organization.objects.get(name=n) for n in ORGS}
        branch = {n: o.branches.first() for n, o in orgs.items()}
        cat = {c.name: c for c in ExpenseCategory.objects.all()}
        subjects = {}

        # --- narx (tashkilot bo'yicha), birinchi oy
        start = date(2026, 9, 1)
        for name, (_g, price, _gp, *_rest) in ORGS.items():
            cfg = BillingSettings.get(orgs[name])
            cfg.monthly_price, cfg.due_day, cfg.billing_start = price, 10, start
            cfg.save()

        # --- xodimlar
        staff = {}
        for pos, first, last, phone, where in STAFF:
            u = self.user('staff', first, last, phone)
            p = Position.objects.get(name=pos)
            StaffProfile.objects.create(user=u, position=p, perms=list(p.default_perms))
            if where is not None:
                u.branches.set([branch[n] for n in where])
            else:
                u.branches.set(list(branch.values()))
            staff[pos] = u
            self.creds.append((f'Xodim: {pos}', to_digits(phone), 'panel'))

        # --- ustozlar
        teachers = {}
        for first, last, phone, subs, where in TEACHERS:
            t = self.user('teacher', first, last, phone)
            t.access_id = next_teacher_id()
            t.save(update_fields=['access_id'])
            t.branches.set([branch[n] for n in where])
            for s in subs:
                subjects.setdefault(s, Subject.objects.get_or_create(name=s)[0])
            teachers[last] = (t, subs)
            self.creds.append((f"Ustoz ({', '.join(subs)})", to_digits(phone), 'ustoz'))

        # --- tashkilotlar: guruh, jadval, o'quvchilar, tarix
        parent = self.user('parent', 'Gulnora', 'Karimova', PARENT_PHONE)
        self.creds.insert(0, ('Ota-ona (4 farzand)', to_digits(PARENT_PHONE), 'ilova'))
        kids = {}
        for name, (gname, _price, gprice, kid, mates, subs, days, periods) in ORGS.items():
            for s in subs:
                subjects.setdefault(s, Subject.objects.get_or_create(name=s)[0])
            grp = Group.objects.create(name=gname, year=2026, branch=branch[name], monthly_price=gprice)
            tch = {}
            for s in subs:      # fan -> shu tashkilotda dars beradigan ustoz
                owner = next((t for t, ts in teachers.values() if s in ts and name in self._where(t)), None)
                tch[s] = Teaching.objects.create(teacher=owner or next(iter(teachers.values()))[0], subject=subjects[s], group=grp)
            for di, day in enumerate(days):
                for pi, period in enumerate(periods):
                    s = subs[(di + pi) % len(subs)]
                    p = PERIODS[period - 1]
                    Lesson.objects.create(teaching=tch[s], weekday=day, period=period, room=str(100 + period),
                                          start=time.fromisoformat(p[1]), end=time.fromisoformat(p[2]))
            students = []
            for i, (first, last, *_g) in enumerate([kid] + [(m[0], m[1]) for m in mates]):
                su = self.user('student', first, last, username=_unique_username(f'{last}-{first}'))
                st = Student.objects.create(user=su, group=grp, birth_date=date(2012 + (name == "Bog'cha") * 6 + (name == 'Asosiy maktab') * 2, 3 + i, 10 + i))
                if i == 0:
                    st.parents.add(parent)
                    kids[name] = st
                    self.creds.append((f"Farzand: {first} {last} ({name})", su.username, 'o\'quvchi'))
                students.append(st)
            self.devices(name, branch[name], students, today)
            self.history(students, list(tch.values()), today)
            ensure_charges([s.pk for s in students], today)
            self.pay(name, students, staff['Hisobchi'], today)
            Announcement.objects.create(title=f"{orgs[name].label}: ota-onalar yig'ilishi", body="Juma kuni soat 15:00 da yig'ilish bo'lib o'tadi.",
                                        audience='parents', branch=branch[name], author=staff['Maktab egasi'])
            Announcement.objects.create(title="To'lov muddati", body="Oylik to'lov — har oyning 10-sanasigacha.", audience='all',
                                        branch=branch[name], author=staff['Maktab egasi'])
            self.finance(name, branch[name], cat, staff['Hisobchi'], teachers, today)
        self.photos()

    def _where(self, teacher):
        return [b.organization.name for b in teacher.branches.all()]

    def devices(self, name, br, students, today):
        din = Device.objects.create(name=f'{name}: Kirish', direction='in', branch=br, last_seen=timezone.now())
        dout = Device.objects.create(name=f'{name}: Chiqish', direction='out', branch=br, last_seen=timezone.now())
        now = timezone.localtime()
        for back in range(6, -1, -1):
            day = today - timedelta(days=back)
            if day.weekday() == 6:
                continue
            for st in students:
                r = random.Random(f'{day}:{st.pk}')
                if r.random() > 0.9:
                    continue
                arr = timezone.make_aware(datetime.combine(day, time(8, 0))) + timedelta(minutes=r.randint(0, 25))
                if arr > now:
                    continue
                AccessEvent.objects.create(device=din, employee_no=st.access_id, student=st, direction='in', occurred_at=arr)
                lv = timezone.make_aware(datetime.combine(day, time(14, 30))) + timedelta(minutes=r.randint(0, 60))
                if back and lv <= now:
                    AccessEvent.objects.create(device=dout, employee_no=st.access_id, student=st, direction='out', occurred_at=lv)

    def history(self, students, teachings, today):
        rng = self.rng
        days = [today - timedelta(days=n) for n in range(1, 25) if (today - timedelta(days=n)).weekday() != 6]
        for st in students:
            main = st.pk == students[0].pk
            for _ in range(rng.randint(9, 13)):
                t = rng.choice(teachings)
                score = rng.choice([5, 5, 4, 4, 4, 3] if main else [5, 4, 4, 3, 3, 2])
                Grade.objects.create(student=st, teaching=t, date=rng.choice(days), score=score,
                                     kind=rng.choice(['current', 'current', 'test', 'exam']), created_by=t.teacher)
            for d in days[:14]:
                for lesson in Lesson.objects.filter(teaching__group_id=st.group_id, weekday=d.weekday(), active=True):
                    status = rng.choices(['present', 'late', 'excused', 'absent'], [90, 4, 3, 3])[0]
                    Attendance.objects.get_or_create(student=st, lesson=lesson, date=d,
                                                     defaults={'status': status, 'marked_by': lesson.teaching.teacher})
        for t in teachings[:2]:
            Homework.objects.create(teaching=t, text=rng.choice(HOMEWORK), due_date=today + timedelta(days=rng.randint(1, 3)),
                                    assigned_on=today - timedelta(days=1), created_by=t.teacher)

    def pay(self, name, students, cashier, today):
        months = billed_months(today, BillingSettings.get(Organization.objects.get(name=name)))
        # asosiy farzandning holati tashkilotga qarab har xil: to'liq, qarz, qisman, oldindan
        scenario = {'Tibbiyot maktabi': 'full', 'Asosiy maktab': 'debt', "O'quv markaz": 'partial', "Bog'cha": 'full'}[name]
        for idx, st in enumerate(students):
            kind = scenario if idx == 0 else self.rng.choice(['full', 'full', 'partial', 'none'])
            for i, m in enumerate(months):
                charge = st.charges.filter(month=m).first()
                if not charge or (kind == 'none' and i > 0):
                    continue
                last = i == len(months) - 1
                if kind == 'debt' and last:
                    continue
                amount = int(charge.amount) // 2 if kind == 'partial' and last else int(charge.amount)
                Payment.objects.create(student=st, amount=amount, method=self.rng.choice(['cash', 'card', 'transfer']),
                                       paid_on=min(date(m.year, m.month, self.rng.randint(2, 9)), today), received_by=cashier)

    def finance(self, name, br, cat, cashier, teachers, today):
        first = date(today.year, today.month, 1)
        for back, (c, amt, payee) in enumerate([('Kommunal', 1800000, 'Elektr va gaz'), ('Xo\'jalik', 650000, 'Tozalash vositalari'), ('Ijara', 4000000, 'Bino egasi')]):
            category = cat.get(c) or next(iter(cat.values()))
            Expense.objects.create(branch=br, category=category, date=first - timedelta(days=back * 9 + 2), amount=amt, payee=payee, created_by=cashier)
        RecurringExpense.objects.create(branch=br, category=cat.get('Ijara') or next(iter(cat.values())), amount=4000000, payee='Bino ijarasi', day=5,
                                        start_month=first.replace(month=9))
        for last, (t, _s) in teachers.items():
            if name in self._where(t):
                center = name == "O'quv markaz"
                SalaryRule.objects.create(employee=t, branch=br, effective_from=date(2026, 9, 1), kind='percent' if center else 'fixed',
                                          amount=0 if center else 3500000, percent=Decimal('40'), created_by=cashier)

    def photos(self):
        """Taomlar uchun oddiy rangli namunaviy rasmlar (haqiqiy rasm panelda bir marta yuklanadi)."""
        from PIL import Image, ImageDraw
        from meals.models import Dish
        from meals.services import save_dish_photo
        palette = [(214, 137, 16), (192, 57, 43), (39, 174, 96), (41, 128, 185), (142, 68, 173), (127, 140, 141)]
        for i, dish in enumerate(Dish.objects.filter(photo='')[:60]):
            img = Image.new('RGB', (640, 420), palette[i % len(palette)])
            ImageDraw.Draw(img).text((24, 190), dish.name, fill=(255, 255, 255))
            buf = BytesIO()
            img.save(buf, 'JPEG')
            buf.seek(0)
            save_dish_photo(dish, buf)

    # ------------------------------------------------------------------ exam
    def link_exam(self):
        from examlink import client, matching
        from examlink.models import ExamLink
        if not client.enabled():
            raise CommandError('EXAM_API_URL / EXAM_API_KEY sozlanmagan')
        exam = client.fetch_students()
        made = 0
        for st in Student.objects.filter(parents__phone_digits=to_digits(PARENT_PHONE)):
            name = st.user.get_full_name()
            best = max(exam, key=lambda x: matching.similarity(name, x['full_name']), default=None)
            if best and matching.similarity(name, best['full_name']) >= 0.99 and not ExamLink.objects.filter(exam_student_id=best['id']).exists():
                ExamLink.objects.create(student=st, exam_student_id=best['id'], exam_name=best['full_name'], exam_class=best['class_name'])
                made += 1
        self.stdout.write(f'Exam bilan bog\'landi: {made} ta farzand')

    def report(self):
        self.stdout.write(self.style.SUCCESS(f'Tayyor. Hamma sinov hisoblar paroli: {self.password}'))
        for role, login, where in self.creds:
            self.stdout.write(f'  {role:44} login: {login:24} ({where})')
