from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.school_import import import_staff, import_student_file, read_staff_docx, read_student_sheets


class Command(BaseCommand):
    help = "Maktab ro'yxatlarini yuklaydi: o'quvchilar (.xls/.xlsx) va xodimlar (.docx). --dry-run bilan faqat sanaydi."

    def add_arguments(self, parser):
        parser.add_argument('--students', help="O'quvchilar fayli (.xls/.xlsx)")
        parser.add_argument('--staff', help='Xodimlar fayli (.docx)')
        parser.add_argument('--dry-run', action='store_true', help="Hech narsa yozmaydi, faqat nimalar yuklanishini ko'rsatadi")

    def handle(self, students, staff, dry_run, **opts):
        if not students and not staff:
            raise CommandError('--students yoki --staff bering')
        try:
            if dry_run:
                if students:
                    for g, rows in read_student_sheets(students).items():
                        self.stdout.write(f"{g}: {len(rows)} ta o'quvchi, telefonsiz: {sum(1 for r in rows if not r[2])}")
                if staff:
                    self.stdout.write(f'Xodimlar: {len(read_staff_docx(staff))} ta')
                return
            with transaction.atomic():
                if staff:
                    r = import_staff(read_staff_docx(staff))
                    self.stdout.write(self.style.SUCCESS(
                        f"Xodimlar: ustoz {r['teachers']}, panel xodimi {r['panel']}, boshqa {r['other']}, oldindan bor {r['existing']}"))
                    for x in r['bad_phone']:
                        self.stdout.write(self.style.WARNING(f"Telefon noto'g'ri: {x}"))
                if students:
                    for r in import_student_file(students):
                        self.stdout.write(self.style.SUCCESS(
                            f"{r['group']}: yangi {r['created']}, oldindan {r['existing']}; "
                            f"ota-ona yangi {r['parents_new']}, bog'langan {r['parents_linked']}"))
                        for n in r['no_phone']:
                            self.stdout.write(self.style.WARNING(f"Telefon yo'q: {n}"))
                        for n in r['bad_phone']:
                            self.stdout.write(self.style.WARNING(f"Telefon noto'g'ri: {n}"))
        except (OSError, ValueError) as e:
            raise CommandError(str(e))
