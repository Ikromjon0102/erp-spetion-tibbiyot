"""Taqdimot (demo) uchun to'liq TO'QIMA ma'lumotlar: sinflar, ustozlar, dars jadvali, o'quvchilar, ota-onalar, davomat, baholar,
vazifalar, to'lovlar, e'lonlar va kirish-chiqish hodisalari. Haqiqiy odamlar ma'lumoti ishlatilmaydi.

    python manage.py seed_showcase --password "<parol>"      # bo'sh bazaga bir marta
    python manage.py seed_showcase --refresh                  # har kuni: bugungi kelish-ketish va davomatni yangilaydi

Panelda hamma narsa ko'rinadi (bu ma'lumotlar `is_demo` emas, sinov hisobidan farqli)."""
import random
from datetime import date, datetime, time, timedelta

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
from billing.models import BillingSettings, Discount, Payment, StudentDiscount
from billing.services import billed_months, ensure_charges
from journal.models import Attendance, Grade, Homework
from notices.models import Announcement, AnnouncementRead
from panel.models import Position, StaffProfile

BOYS = ['Aziz', 'Jasur', 'Sardor', 'Bobur', 'Timur', 'Doniyor', 'Anvar', 'Sherzod', 'Javohir', 'Otabek', 'Behruz', 'Akmal', 'Farhod', 'Humoyun']
GIRLS = ['Madina', 'Zilola', 'Malika', 'Sevara', 'Dilnoza', 'Laylo', 'Zarina', 'Nigora', 'Shahnoza', 'Kamola', 'Munisa', 'Feruza', 'Nodira', 'Sabina']
SURNAMES = ['Karimov', 'Rahimov', 'Tursunov', 'Aliyev', 'Qodirov', 'Yusupov', 'Ergashev', 'Saidov', 'Nazarov', 'Ismoilov', 'Abdullayev',
            'Hamidov', 'Mirzayev', 'Normatov', 'Sobirov', 'Xolmatov']
FATHERS = ['Bahodir', 'Rustam', 'Alisher', 'Komil', 'Ravshan', 'Sanjar', 'Jamshid', 'Dilshod']
MOTHERS = ['Gulbahor', 'Dilfuza', 'Nargiza', 'Mohira', 'Shirin', 'Barno', 'Odina', 'Zebo']
# (fan, ustoz familiyasi, ismi, ayol?)
TEACHERS = [('Ona tili', 'Abdurahmonova', 'Gulnora', True), ('Matematika', 'Yoqubov', 'Sanjar', False), ('Biologiya', 'Hasanova', 'Mohira', True),
            ('Kimyo', 'Rasulov', 'Ilhom', False), ('Fizika', 'Tojiyev', 'Baxtiyor', False), ('Ingliz tili', 'Karimova', 'Nilufar', True),
            ('Tarix', 'Ochilov', 'Shuhrat', False), ('Informatika', 'Mamatov', 'Eldor', False), ('Anatomiya', 'Salimova', 'Dildora', True),
            ('Jismoniy tarbiya', 'Ibragimov', 'Rustam', False)]
STAFF = [('Direktor', 'Raximov', 'Dilshod'), ('Reception', 'Normurodova', 'Sevinch'), ('Hisobchi', 'Ahmedova', 'Barno'),
         ("Zam (o'quv ishlari)", 'Xudoyberdiyev', 'Anvar')]
HOMEWORK = ["Darslikdagi 12-mavzuni o'qing va savollarga yozma javob bering.", "5 ta misol yeching va daftarga ko'chiring.",
            "Mavzu bo'yicha qisqa referat (1 bet) tayyorlang.", "Lug'at so'zlarini yodlang."]
GRADES = [5, 5, 5, 4, 4, 4, 3, 3, 2]


class Command(BaseCommand):
    help = "Taqdimot uchun to'qima ma'lumotlar yaratadi (--password) yoki bugungi kunni yangilaydi (--refresh)."

    def add_arguments(self, parser):
        parser.add_argument('--password', help="Hamma demo hisoblar uchun bitta parol")
        parser.add_argument('--refresh', action='store_true', help="Faqat bugungi kelish-ketish, davomat va qurilma signalini yangilaydi")
        parser.add_argument('--per-class', type=int, default=10)
        parser.add_argument('--force', action='store_true', help="Bazada o'quvchilar bo'lsa ham davom etadi")

    def handle(self, password, refresh, per_class, force, **opts):
        self.rng = random.Random(2026)
        if refresh:
            self.refresh_today()
            return self.stdout.write(self.style.SUCCESS('Bugungi ma\'lumotlar yangilandi.'))
        if not password:
            raise CommandError('--password kerak')
        if Student.objects.exists() and not force:
            raise CommandError("Bazada o'quvchilar bor. Faqat bo'sh bazaga yoki --force bilan.")
        with transaction.atomic():
            self.build(password, per_class)
        self.refresh_today()

    # ---------------------------------------------------------------- yaratish
    def mkuser(self, password, role, first, last, phone='', username=None, **kw):
        digits = to_digits(phone)
        u = User(username=username or digits or f'{last}-{first}'.lower(), first_name=first, last_name=last, role=role, phone=phone, **kw)
        if password:
            u.set_password(password)
        else:
            u.set_unusable_password()
        u.save()
        return u

    def build(self, password, per_class):
        rng = self.rng
        today = timezone.localdate()
        creds = []

        admin = User.objects.filter(username='admin').first()
        if not admin:
            admin = User.objects.create_superuser('admin', password=password, first_name='Tizim', last_name='Administratori')
        creds.append(('Texnik administrator', 'admin', '/admin/ va /panel/'))

        staff = {}
        for i, (pos, last, first) in enumerate(STAFF, 1):
            phone = f'+998 90 100-00-0{i}'
            u = self.mkuser(password, 'staff', first, last, phone)
            p = Position.objects.get(name=pos)
            StaffProfile.objects.create(user=u, position=p, perms=list(p.default_perms))
            staff[pos] = u
            creds.append((pos, phone, '/panel/'))

        subjects, teachers = [], []
        for i, (subj, last, first, female) in enumerate(TEACHERS, 1):
            phone = f'+998 90 200-00-{i:02d}'
            t = self.mkuser(password, 'teacher', first, last, phone)
            t.access_id = next_teacher_id()
            t.save(update_fields=['access_id'])
            subjects.append(Subject.objects.get_or_create(name=subj)[0])
            teachers.append(t)
            if i <= 3:
                creds.append((f'Ustoz ({subj})', phone, '/ustoz/'))

        groups = [Group.objects.create(name=f'{n}-Sinf', year=2026) for n in range(5, 11)]
        teachings = {}
        for gi, g in enumerate(groups):
            for si, s in enumerate(subjects):
                teachings[(gi, si)] = Teaching.objects.create(teacher=teachers[si], subject=s, group=g)
            # bir ustozning bir vaqtda ikki sinfda bo'lishi mumkin emas: (soat + kun + sinf) % 10 sinflar uchun har xil
            for day in range(6):
                for period, start, end in PERIODS[:6]:
                    si = (period + day + gi) % len(subjects)
                    Lesson.objects.create(teaching=teachings[(gi, si)], weekday=day, period=period, room=str(200 + gi * 10 + period),
                                          start=time.fromisoformat(start), end=time.fromisoformat(end))

        students, phone_n = [], 100
        for gi, g in enumerate(groups):
            for _ in range(per_class):
                girl = rng.random() < 0.5
                first = rng.choice(GIRLS if girl else BOYS)
                base = rng.choice(SURNAMES)
                last = base + ('a' if girl else '')
                su = self.mkuser(None, 'student', first, last, username=_unique_username(f'{last}-{first}'))
                st = Student.objects.create(user=su, group=g, birth_date=date(2015 - gi, rng.randint(1, 12), rng.randint(1, 28)))
                phone_n += 1
                father = rng.random() < 0.5
                pu = self.mkuser(password, 'parent', rng.choice(FATHERS if father else MOTHERS), base + ('' if father else 'a'),
                                 f'+998 91 {phone_n // 100 + 300}-{phone_n % 100:02d}-{rng.randint(10, 99)}')
                st.parents.add(pu)
                students.append(st)
        # aka-uka/opa-singil: ba'zi ota-onalarning ikki farzandi bor
        for st in rng.sample(students[len(students) // 2:], 6):
            donor = rng.choice(students[:len(students) // 2])
            old = list(st.parents.all())
            st.parents.set(donor.parents.all())
            User.objects.filter(pk__in=[o.pk for o in old]).delete()
        # bitta ustoz ham ota-ona (ikki rejim namunasi)
        students[3].parents.add(teachers[1])
        creds.append(('Ota-ona', students[0].parents.first().phone, "/ (farzandlar sahifasi)"))
        creds.append(('Ustoz va ota-ona (ikki rejim)', teachers[1].phone, '/ustoz/ <-> farzandlarim'))

        self.history(students, teachings, teachers, groups, today)
        self.finance(students, staff['Reception'], today)
        self.notices(students, admin, teachers, groups, today)

        for name, direction in (('Kirish-1', 'in'), ('Kirish-2', 'in'), ('Chiqish-1', 'out'), ('Chiqish-2', 'out')):
            Device.objects.create(name=name, direction=direction)

        self.stdout.write(self.style.SUCCESS(f"Tayyor: {len(groups)} sinf, {len(students)} o'quvchi, {len(teachers)} ustoz."))
        self.stdout.write(f"Hamma hisoblar paroli: {password}")
        for role, login, where in creds:
            self.stdout.write(f"  {role:34} login: {login:18} {where}")

    def history(self, students, teachings, teachers, groups, today):
        rng = self.rng
        gi_of = {g.pk: i for i, g in enumerate(groups)}
        grades, atts = [], []
        days = [today - timedelta(days=n) for n in range(1, 21) if (today - timedelta(days=n)).weekday() != 6]
        for st in students:
            gi = gi_of[st.group_id]
            my = [t for (g, _), t in teachings.items() if g == gi]
            for _ in range(rng.randint(7, 11)):
                t = rng.choice(my)
                grades.append(Grade(student=st, teaching=t, date=rng.choice(days), score=rng.choice(GRADES),
                                    kind=rng.choice(['current', 'current', 'current', 'test', 'exam']), created_by=t.teacher))
            for d in days[:12]:
                for lesson in Lesson.objects.filter(teaching__group_id=st.group_id, weekday=d.weekday(), active=True):
                    status = rng.choices(['present', 'late', 'excused', 'absent'], [90, 4, 3, 3])[0]
                    atts.append(Attendance(student=st, lesson=lesson, date=d, status=status, marked_by=lesson.teaching.teacher))
        Grade.objects.bulk_create(grades)
        Attendance.objects.bulk_create(atts, ignore_conflicts=True)

        hw = []
        for (gi, si), t in teachings.items():
            if si in (0, 1, 2, 5) and gi in (0, 1, 2, 3):
                hw.append(Homework(teaching=t, text=rng.choice(HOMEWORK), due_date=today + timedelta(days=rng.randint(1, 4)),
                                   assigned_on=today - timedelta(days=rng.randint(0, 2)), created_by=t.teacher))
        Homework.objects.bulk_create(hw)

    def finance(self, students, cashier, today):
        rng = self.rng
        cfg = BillingSettings.get()
        cfg.monthly_price, cfg.due_day = 1500000, 10
        cfg.billing_start = date(today.year if today.month >= 9 else today.year - 1, 9, 1)
        cfg.save()
        staff_kid = Discount.objects.create(name='Xodim farzandi', percent=50)
        siblings = Discount.objects.create(name='2+ farzand', percent=10)
        for st in rng.sample(students, 3):
            StudentDiscount.objects.create(student=st, discount=staff_kid, note='Xodim farzandi', assigned_by=cashier)
        for st in students:
            if st.parents.first().children.count() > 1:
                StudentDiscount.objects.create(student=st, discount=siblings, note='Oilada 2 va undan ko\'p farzand', assigned_by=cashier)
        ensure_charges([s.pk for s in students], today)
        months = billed_months(today, cfg)
        methods = [m for m, _ in Payment.Method.choices]
        for st in students:
            kind = rng.choices(['full', 'partial', 'none'], [62, 23, 15])[0]
            for i, m in enumerate(months):
                charge = st.charges.filter(month=m).first()
                if not charge:
                    continue
                last = i == len(months) - 1
                if kind == 'none' and i > 0:
                    continue
                if kind == 'partial' and last:
                    amount = int(charge.amount) // 2
                else:
                    amount = int(charge.amount)
                paid_on = min(date(m.year, m.month, rng.randint(2, 9)), today)
                Payment.objects.create(student=st, amount=amount, method=rng.choice(methods), paid_on=paid_on, received_by=cashier)

    def notices(self, students, author, teachers, groups, today):
        rng = self.rng
        items = [("Ota-onalar yig'ilishi", "Juma kuni soat 15:00 da maktab zalida umumiy ota-onalar yig'ilishi bo'lib o'tadi. Ishtirok etishingizni so'raymiz.", 'parents', None),
                 ("Yangi dars jadvali", "Noyabr oyi uchun dars jadvali yangilandi. Iltimos, farzandingizning jadvalini tekshirib chiqing.", 'all', None),
                 ("Ustozlar kengashi", "Ertaga soat 14:30 da ustozlar kengashi. Kun tartibi: choraklik baholash.", 'teachers', None),
                 ("Tibbiyot fanlari olimpiadasi", "Yakshanba kuni 9-10-sinflar o'rtasida Biologiya va Anatomiya olimpiadasi o'tkaziladi.", 'all', groups[-1]),
                 ("To'lov muddati eslatmasi", "Oylik to'lov muddati — har oyning 10-sanasigacha. Qarzdorlikni to'lashni unutmang.", 'parents', None)]
        parents = list({p for st in students for p in st.parents.all()})
        for n, (title, body, aud, grp) in enumerate(items):
            a = Announcement.objects.create(title=title, body=body, audience=aud, group=grp, author=author)
            Announcement.objects.filter(pk=a.pk).update(created_at=timezone.now() - timedelta(days=len(items) - n, hours=rng.randint(0, 5)))
            readers = parents if aud == 'parents' else teachers if aud == 'teachers' else parents + teachers
            for u in rng.sample(readers, int(len(readers) * rng.choice([0.4, 0.6, 0.85]))):
                r = AnnouncementRead.objects.create(announcement=a, user=u)
                AnnouncementRead.objects.filter(pk=r.pk).update(read_at=a.created_at + timedelta(hours=rng.randint(1, 40)))

    # ---------------------------------------------------------------- har kuni
    def refresh_today(self):
        """Bugungi kelish-ketish va davomatni qayta yaratadi, o'tgan kunlar uchun kelish-ketishni to'ldiradi, qurilmalarni 'tirik' qiladi."""
        now = timezone.localtime()
        today = now.date()
        students = list(Student.objects.select_related('user', 'group').filter(user__is_demo=False))
        devices = {d: list(Device.objects.filter(direction=d)) for d in ('in', 'out')}
        if not students or not devices['in'] or not devices['out']:
            raise CommandError("Avval seed_showcase --password bilan ma'lumot yarating.")

        def at(day, h, m):
            return timezone.make_aware(datetime.combine(day, time(h, m)))

        start = today - timedelta(days=10)
        AccessEvent.objects.filter(occurred_at__gte=at(start, 0, 0)).delete()
        events = []
        for back in range(10, -1, -1):
            day = today - timedelta(days=back)
            if day.weekday() == 6:
                continue
            for st in students:
                # har bir (kun, o'quvchi) uchun qiymatlar avval belgilanadi: yangilash qayta-qayta ishlaganda natija barqaror qoladi
                r = random.Random(f'{day}:{st.pk}')
                comes, m_in, m_out, leaves, d_in, d_out = r.random(), r.randint(0, 38), r.randint(0, 110), r.random(), r.random(), r.random()
                if comes > (0.88 if back else 0.85):
                    continue
                arrive, leave = at(day, 7, 50) + timedelta(minutes=m_in), at(day, 14, 0) + timedelta(minutes=m_out)
                if arrive > now:
                    continue
                events.append(AccessEvent(device=devices['in'][int(d_in * len(devices['in']))], employee_no=st.access_id, student=st,
                                          direction='in', occurred_at=arrive))
                if (back or leaves < 0.35) and leave <= now:
                    events.append(AccessEvent(device=devices['out'][int(d_out * len(devices['out']))], employee_no=st.access_id,
                                              student=st, direction='out', occurred_at=leave))
        AccessEvent.objects.bulk_create(events, ignore_conflicts=True)

        # bugungi davomat: boshlangan darslar, eng oxirgisi "olinmagan" qoladi (bosh sahifada ko'rinadi)
        Attendance.objects.filter(date=today).delete()
        started = list(Lesson.objects.filter(weekday=today.weekday(), active=True, start__lte=now.time()).select_related('teaching'))
        last_start = max((l.start for l in started), default=None)
        arrived = {e.student_id for e in events if e.direction == 'in' and e.occurred_at.date() == today}
        rows = []
        for lesson in started:
            if lesson.start == last_start:
                continue
            for st in students:
                if st.group_id == lesson.teaching.group_id:
                    rows.append(Attendance(student=st, lesson=lesson, date=today, marked_by=lesson.teaching.teacher,
                                           status='present' if st.pk in arrived else 'absent'))
        Attendance.objects.bulk_create(rows, ignore_conflicts=True)
        Device.objects.update(last_seen=timezone.now())
