from django.core.management.base import BaseCommand, CommandError

from accounts.pay_sheet_import import import_pay_sheets, import_staff_sheet, read_pay_sheets, read_staff_sheet
from org.models import Branch


class Command(BaseCommand):
    help = ("Maktabning to'lov jadvali (sinf varaqlari) va xodimlar Excel'ini filialga yuklaydi. "
            "Avval xodimlar (ustoz ham ota-ona bo'lsa bitta hisob bo'lishi uchun). --dry-run: faqat sanaydi.")

    def add_arguments(self, parser):
        parser.add_argument('--branch', type=int, required=True, help='Filial id')
        parser.add_argument('--students', help="O'quvchilar to'lov jadvali (.xlsx)")
        parser.add_argument('--staff', help='Xodimlar raqamlari (.xlsx)')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, branch, students, staff, dry_run, **opts):
        branch = Branch.objects.filter(pk=branch).select_related('organization').first()
        if branch is None:
            raise CommandError('Filial topilmadi')
        self.stdout.write(f'Filial: {branch.organization.name} · {branch.name}')
        staff_rows = read_staff_sheet(staff) if staff else []
        sheets = read_pay_sheets(students) if students else {}
        if dry_run:
            for name, d in sheets.items():
                self.stdout.write(f"  {name}: {len(d['students'])} o'quvchi, rahbar: {d['teacher'] or '-'}")
            self.stdout.write(f"Jami: {len(sheets)} sinf, {sum(len(d['students']) for d in sheets.values())} o'quvchi, "
                              f"{len(staff_rows)} xodim")
            return
        if staff_rows:
            r = import_staff_sheet(staff_rows, branch)
            self.stdout.write(self.style.SUCCESS(f"Xodimlar: ustoz {r['teachers']}, boshqa xodim {r['staff']}, oldindan bor {r['existing']}"))
            for x in r['skipped']:
                self.stdout.write(self.style.WARNING(f'  o\'tkazib yuborildi: {x}'))
            for x in r['no_phone']:
                self.stdout.write(self.style.WARNING(f'  telefonsiz: {x}'))
        if sheets:
            r = import_pay_sheets(sheets, branch)
            self.stdout.write(self.style.SUCCESS(
                f"Sinflar: {r['groups']} yangi; o'quvchi {r['created']} yangi, {r['existing']} oldindan bor; "
                f"ota-ona {r['parents_new']} yangi hisob, {r['parents_linked']} bog'lanish"))
            for x in r['no_phone']:
                self.stdout.write(self.style.WARNING(f'  telefonsiz: {x}'))
            for x in r['bad_phone']:
                self.stdout.write(self.style.WARNING(f"  telefon noto'g'ri: {x}"))
