"""Hamma narsani sinab ko'rish uchun bitta hisob: ham ustoz, ham ota-ona, davomat va baho istalgan vaqtda.

Sinov ma'lumotlari alohida "Sinov-sinf" va "Sinov-sinf B" da: haqiqiy sinflar, o'quvchilar va e'lonlarga tegmaydi va
ular ko'rinmaydi. Hisobning 4 ta farzandi bor: ikkitasi A sinfda, ikkitasi B sinfda (turli sinflardagi farzandlar holati).
`--remove` hammasini o'chiradi."""
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from academics.models import Group, Lesson, Subject, Teaching
from accounts.models import Student, User
from accounts.passwords import new_temp_password
from access.models import AccessEvent, Device
from journal.models import Attendance, Grade, Homework
from billing.services import add_test_payment
from notices.models import Announcement

USERNAME = 'sinov'
PHONE = '+998 90 000-00-01'
SUBJECTS = ('Sinov fani', "Sinov (kun bo'yi)")
# (guruh, o'quvchi login prefiksi, [(familiya, ism, face ID)])
CLASSES = [
    ('Sinov-sinf', 'sinov_o', [
        ('Sinovov', 'Aziz', 'S9001'), ('Sinovova', 'Madina', 'S9002'), ('Testov', 'Jasur', 'S9003'), ('Testova', 'Zilola', 'S9004'),
        ('Namunov', 'Sardor', 'S9005'), ('Namunova', 'Malika', 'S9006'), ('Tekshirov', 'Doniyor', 'S9007'), ('Tekshirova', 'Sevara', 'S9008')]),
    ('Sinov-sinf B', 'sinov_b', [
        ('Sinovov', 'Bobur', 'S9101'), ('Sinovova', 'Zarina', 'S9102'), ('Testov', 'Anvar', 'S9103'),
        ('Testova', 'Dilnoza', 'S9104'), ('Namunov', 'Timur', 'S9105'), ('Namunova', 'Laylo', 'S9106')]),
]
CHILDREN_PER_CLASS = 2
GROUP_NAMES = [c[0] for c in CLASSES]
KID_PREFIXES = [c[1] for c in CLASSES]


class Command(BaseCommand):
    help = "Sinov hisobi (ustoz + ota-ona, vaqt cheklovisiz) va unga sinov ma'lumotlarini yaratadi."

    def add_arguments(self, parser):
        parser.add_argument('--password', help="Parol (berilmasa tasodifiy yaratiladi)")
        parser.add_argument('--remove', action='store_true', help="Sinov hisobi va barcha sinov ma'lumotlarini o'chiradi")

    def handle(self, password, remove, **opts):
        if remove:
            return self.remove()

        subjects = [Subject.objects.get_or_create(name=n)[0] for n in SUBJECTS]
        user = User.objects.filter(username=USERNAME).first()
        created = user is None
        if created:
            user = User(username=USERNAME, first_name='Sinov', last_name='Ustoz')
        user.role, user.phone, user.is_demo, user.is_active = User.Role.TEACHER, PHONE, True, True
        user.must_change_password = False
        if created or password:
            password = password or new_temp_password()
            user.set_password(password)
        else:
            password = None
        user.save()

        # birinchi versiyada yaratilgan, sinf nomisiz e'lonlar (yangi nomlilari bilan takrorlanmasin)
        Announcement.objects.filter(title__in=["[Sinov] Hamma uchun e'lon", "[Sinov] Ustozlarga e'lon",
                                               "[Sinov] Ota-onalarga e'lon"]).delete()
        children, summary = [], []
        for gname, prefix, kids in CLASSES:
            group, _ = Group.objects.get_or_create(name=gname)
            teachings = [Teaching.objects.get_or_create(teacher=user, subject=s, group=group)[0] for s in subjects]
            self.make_lessons(teachings)
            students = self.make_students(group, prefix, kids)
            mine = students[:CHILDREN_PER_CLASS]
            for kid in mine:
                kid.parents.add(user)
            self.seed_history(user, mine, teachings, group)
            self.seed_homework(user, teachings)
            children += mine
            summary.append(f"{gname} ({len(students)} ta o'quvchi)")

        self.stdout.write(self.style.SUCCESS(
            f"Sinov hisobi tayyor.\n  Login: {PHONE}  (yoki: {USERNAME})\n  Parol: {password or '(o`zgarmadi, oldingi parol)'}"))
        self.stdout.write("  Sinflar: " + ', '.join(summary))
        self.stdout.write("  Farzandlar: " + ', '.join(f'{s.user.first_name} ({s.group.name})' for s in children))
        self.stdout.write("  Hammasini o'chirish: python manage.py create_test_account --remove")

    # ------------------------------------------------------------------ yordamchilar
    def make_lessons(self, teachings):
        """Har kuni 1-2-soat + kun bo'yi davom etadigan dars (har qanday vaqtda "HOZIR" bo'lsin)."""
        plan = [(teachings[0], 1, time(8, 30), time(9, 15)), (teachings[0], 2, time(9, 20), time(10, 5)),
                (teachings[1], 9, time(0, 0), time(23, 59))]
        for weekday in range(6):
            for teaching, period, start, end in plan:
                Lesson.objects.update_or_create(teaching=teaching, weekday=weekday, period=period,
                                                defaults={'start': start, 'end': end, 'active': True})

    def make_students(self, group, prefix, kids):
        students = []
        for i, (last, first, face) in enumerate(kids, 1):
            u, made = User.objects.get_or_create(username=f'{prefix}{i}', defaults={
                'first_name': first, 'last_name': last, 'role': User.Role.STUDENT})
            if made:
                u.set_unusable_password()
                u.save()
            st, _ = Student.objects.get_or_create(user=u, defaults={'group': group, 'access_id': face})
            students.append(st)
        return students

    def seed_homework(self, user, teachings):
        """Namunaviy vazifalar (faqat bir marta): ota-ona jadvalda fan ustiga bosib ko'radi, ustoz tahrirlab ko'radi."""
        if Homework.objects.filter(teaching__in=teachings).exists():
            return
        today = timezone.localdate()
        samples = [(teachings[0], "1-mashqni bajaring va 2-betdagi savollarga yozma javob bering.", 1, 0),
                   (teachings[0], "She'rni yoddan o'qishga tayyorlaning.", 3, 1),
                   (teachings[1], "Mavzuni takrorlang va 5 ta misol yeching.", 2, 0)]
        for teaching, text, due_in, assigned_back in samples:
            Homework.objects.create(teaching=teaching, text=text, due_date=today + timedelta(days=due_in),
                                    assigned_on=today - timedelta(days=assigned_back), created_by=user)

    def seed_history(self, user, kids, teachings, group):
        """Farzandlar sahifalarida ko'rinadigan baho, davomat, kirish-chiqish, to'lov va e'lonlar (faqat bir marta)."""
        today = timezone.localdate()
        regular = Lesson.objects.filter(teaching=teachings[0], active=True)
        for n, kid in enumerate(kids):
            if not kid.grades.exists():
                for back, score in enumerate([5, 4, 5, 3, 4, 5, 2, 4]):
                    Grade.objects.create(student=kid, teaching=teachings[back % 2], score=score - (n and back % 3 == 0),
                                         date=today - timedelta(days=back * 2), kind=('test', 'current')[back % 2],
                                         created_by=user)
            if not kid.attendance.exists():
                for back in range(1, 15):
                    d = today - timedelta(days=back)
                    for lesson in regular.filter(weekday=d.weekday()):
                        status = 'absent' if (back + n) % 7 == 0 else 'late' if (back + n) % 5 == 0 else 'present'
                        Attendance.objects.get_or_create(student=kid, lesson=lesson, date=d, defaults={'status': status})
            for month_back, paid in ((2, 1500000), (1, 1500000), (0, 500000 if n == 0 else 1500000)):
                m = (today.replace(day=1) - timedelta(days=30 * month_back)).replace(day=1)
                add_test_payment(kid, m, 1500000, paid)

        # kirish-chiqish: sinfdagi birinchi farzand bugun maktabda, ikkinchisi hali kelmagan
        din, dout = (Device.objects.filter(direction=d).first() or Device.objects.create(name=f'Sinov-{d}', direction=d)
                     for d in ('in', 'out'))
        for n, kid in enumerate(kids):
            for back in range(0 if n == 0 else 1, 7):
                d = today - timedelta(days=back)
                if d.weekday() == 6:
                    continue
                arrive = timezone.make_aware(datetime.combine(d, time(8, 10 + back)))
                AccessEvent.objects.get_or_create(device=din, employee_no=kid.access_id, occurred_at=arrive,
                                                  defaults={'student': kid, 'direction': 'in'})
                if back:
                    leave = timezone.make_aware(datetime.combine(d, time(15, 40 + back)))
                    AccessEvent.objects.get_or_create(device=dout, employee_no=kid.access_id, occurred_at=leave,
                                                      defaults={'student': kid, 'direction': 'out'})

        # e'lonlar faqat sinov sinflariga bog'langan: boshqa foydalanuvchilar ularni ko'rmaydi
        notices = [(f"[Sinov] Hamma uchun e'lon ({group.name})", 'all'), (f"[Sinov] Ustozlarga e'lon ({group.name})", 'teachers'),
                   (f"[Sinov] Ota-onalarga e'lon ({group.name})", 'parents')]
        for title, audience in notices:
            Announcement.objects.get_or_create(title=title, group=group, defaults={
                'body': "Bu sinov e'loni. Ko'rinish va qo'ng'iroqdagi qizil nuqtani tekshirish uchun.\nIkkinchi qator.",
                'audience': audience, 'author': user})

    def remove(self):
        kid_users = User.objects.filter(Q(*[Q(username__startswith=p) for p in KID_PREFIXES], _connector=Q.OR))
        face_ids = list(Student.objects.filter(user__in=kid_users).values_list('access_id', flat=True))
        AccessEvent.objects.filter(employee_no__in=face_ids).delete()
        Announcement.objects.filter(title__startswith='[Sinov]').delete()
        kid_users.delete()                                    # o'quvchilar, baho, davomat, to'lov bilan birga
        Group.objects.filter(name__in=GROUP_NAMES).delete()   # darslar va biriktirishlar bilan birga
        Subject.objects.filter(name__in=SUBJECTS).delete()
        User.objects.filter(username=USERNAME).delete()
        self.stdout.write(self.style.SUCCESS("Sinov hisobi va sinov ma'lumotlari o'chirildi."))
