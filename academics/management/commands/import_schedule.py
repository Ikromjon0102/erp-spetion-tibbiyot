import csv

from django.core.management.base import BaseCommand, CommandError

from academics.schedule_import import import_workbook


class Command(BaseCommand):
    help = "Dars jadvali Excel faylini yuklaydi (qayta ishga tushirsa jadval yangilanadi, davomat tarixi saqlanadi)."

    def add_arguments(self, parser):
        parser.add_argument('path', help="Excel fayl, masalan: 'Dars_Jadvali(Noyabr).xlsx'")
        parser.add_argument('--credentials', default='teachers_credentials.csv',
                            help="Yangi ustozlarning login/parollari yoziladigan fayl")

    def handle(self, path, credentials, **opts):
        try:
            r = import_workbook(path)
        except (OSError, ValueError) as e:
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS(
            f"Jadvalda {r['lessons_total']} ta dars: {r['created']} yangi, {r['updated']} o'zgargan, "
            f"{r['deactivated']} ta eski dars yashirildi."))
        for w in r['warnings']:
            self.stdout.write(self.style.WARNING(w))
        if r['credentials']:
            with open(credentials, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                w.writerow(['Ustoz', 'Login', 'Parol'])
                w.writerows(r['credentials'])
            self.stdout.write(self.style.SUCCESS(
                f"{len(r['credentials'])} ta yangi ustoz yaratildi: {', '.join(r['teachers_new'])}\n"
                f"Login va parollar: {credentials} (ustozlarga tarqatib bo'lgach, faylni o'chiring)"))
