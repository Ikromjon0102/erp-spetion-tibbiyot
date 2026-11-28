from django.core.management.base import BaseCommand, CommandError

from academics.school_schedule_import import CLASS_MAP, import_schedule, read_schedule
from org.models import Branch


class Command(BaseCommand):
    help = ("Maktab dars jadvalini (ruscha «Расписание Классов» varag'i) filialga yuklaydi. "
            "--pay-sheet: sinf rahbarlari («Кл. руководитель» darslari uchun). --dry-run: faqat tekshiradi.")

    def add_arguments(self, parser):
        parser.add_argument('--branch', type=int, required=True)
        parser.add_argument('--file', required=True)
        parser.add_argument('--pay-sheet', help="O'quvchilar to'lov jadvali (.xlsx) — sinf rahbarlari shundan")
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, branch, file, pay_sheet, dry_run, **opts):
        branch = Branch.objects.filter(pk=branch).select_related('organization').first()
        if branch is None:
            raise CommandError('Filial topilmadi')
        heads = {}
        if pay_sheet:
            from accounts.pay_sheet_import import read_pay_sheets
            heads = {name: d['teacher'] for name, d in read_pay_sheets(pay_sheet).items()}
        rows = read_schedule(file)
        try:
            r = import_schedule(rows, branch, class_teachers=heads, dry_run=dry_run)
        except ValueError as e:
            raise CommandError(str(e))
        out = self.stdout.write
        out(f'Filial: {branch.organization.name} · {branch.name}{" (dry-run)" if dry_run else ""}')
        out(self.style.SUCCESS(f"Darslar: {r['lessons']}, sinflar: {len(r['groups'])}, fanlar: {len(r['subjects'])}; "
                               f"eski darslar nofaol qilindi: {r['deactivated']}"))
        out('Sinflar: ' + ', '.join(f'{k} -> {CLASS_MAP.get(k, "?")}' for k in sorted(CLASS_MAP)))
        out('Fanlar: ' + ', '.join(sorted(r['subjects'])))
        if r['unknown_class']:
            out(self.style.ERROR('Tizimda yo\'q sinflar: ' + ', '.join(sorted(r['unknown_class']))))
        out('Ustozlar:')
        for x in sorted(r['teachers']):
            out(f'  {x}')
        if r['no_teacher']:
            out(self.style.WARNING('Ustozi topilmadi (dars ustozsiz yoziladi):'))
            for k, n in sorted(r['no_teacher'].items()):
                out(f'  {k}: {n} dars')
