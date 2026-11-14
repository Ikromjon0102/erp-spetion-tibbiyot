from django.core.management.base import BaseCommand, CommandError

from accounts.student_import import group_name_from_filename, import_students


class Command(BaseCommand):
    help = "Sinf o'quvchilari ro'yxatini Excel'dan yuklaydi (qayta ishga tushirsa takrorlanmaydi)."

    def add_arguments(self, parser):
        parser.add_argument('path', help="Excel fayl, masalan: \"10-sinf o'quvchilari ro'yxati.xlsx\"")
        parser.add_argument('--group', help="Guruh nomi (berilmasa fayl nomidan olinadi: '10-sinf' -> '10-Sinf')")

    def handle(self, path, group, **opts):
        group = group or group_name_from_filename(path)
        if not group:
            raise CommandError("Guruh nomini fayl nomidan aniqlab bo'lmadi, --group bilan bering")
        try:
            r = import_students(path, group)
        except (OSError, ValueError) as e:
            raise CommandError(str(e))
        self.stdout.write(self.style.SUCCESS(
            f"{r['group']}: {r['created']} ta yangi o'quvchi, {r['existing']} tasi oldindan bor edi. "
            f"Ota-onalar: {r['parents_new']} ta yangi hisob, {r['parents_linked']} ta bog'lanish."))
        for name in r['no_phone']:
            self.stdout.write(self.style.WARNING(f"Telefon yo'q (ota-ona yaratilmadi): {name}"))
        for item in r['bad_phone']:
            self.stdout.write(self.style.WARNING(f"Telefon noto'g'ri: {item}"))
