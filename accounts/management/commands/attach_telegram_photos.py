from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from accounts.models import Student
from accounts.photos import PhotoError, save_photo
from accounts.telegram_photos import match, read_export
from org.models import Branch


class Command(BaseCommand):
    help = ("Telegram guruh eksportidagi (result.json + photos/) o'quvchi rasmlarini filial o'quvchilariga biriktiradi. "
            "Rasmi bor o'quvchiga tegmaydi (--replace bo'lmasa). Oxirida sinflar bo'yicha rasmsizlar ro'yxati.")

    def add_arguments(self, parser):
        parser.add_argument('--branch', type=int, required=True)
        parser.add_argument('--export', required=True, help='ChatExport papkasi')
        parser.add_argument('--replace', action='store_true', help='Bor rasmni ham almashtiradi')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, branch, export, replace, dry_run, **opts):
        branch = Branch.objects.filter(pk=branch).select_related('organization').first()
        if branch is None:
            raise CommandError('Filial topilmadi')
        students = list(Student.objects.filter(branch=branch, group__isnull=False).select_related('user', 'group'))
        by_id = {s.pk: s for s in students}
        entries = read_export(export)
        r = match(entries, [(s.pk, s.user.last_name, s.user.first_name, s.group.name) for s in students])
        out = self.stdout.write
        out(f'Filial: {branch.organization.name} · {branch.name}; eksportda {len(entries)} rasm, '
            f"mos keldi {len(r['matched'])} o'quvchi, mos kelmadi {len(r['unmatched'])}, ikkilangan {len(r['ambiguous'])}")

        saved, kept, bad = 0, 0, []
        for sid, ((path, caption, label, _id, _d), who, score) in sorted(r['matched'].items(), key=lambda x: by_id[x[0]].group.name):
            st = by_id[sid]
            if st.user.photo and not replace:
                kept += 1
                continue
            if dry_run:
                saved += 1
                continue
            try:
                with open(path, 'rb') as f:
                    save_photo(st.user, f)
                if not st.access_id:
                    st.save()                                     # Face ID (9001+) avtomatik beriladi
                saved += 1
            except (OSError, PhotoError) as e:
                bad.append(f'{caption} ({path.name}): {e}')
        out(self.style.SUCCESS(f"Rasm biriktirildi: {saved}{' (dry-run)' if dry_run else ''}; oldindan rasmi bor: {kept}"))
        for x in bad:
            out(self.style.WARNING(f'  xato: {x}'))

        out(self.style.WARNING(f"\nMos kelmagan rasmlar ({len(r['unmatched'])}) — panelda o'quvchi kartasidan qo'lda yuklang:"))
        for (path, caption, label, _id, _d), near, score in r['unmatched']:
            out(f"  {caption} [{label or '-'}] — {path.name}; eng yaqini: {near}")
        for (path, caption, label, _id, _d), cands in r['ambiguous']:
            out(f"  {caption} [{label or '-'}] — {path.name}; ikkilangan: {' / '.join(cands)}")

        will_have = set(r['matched']) if dry_run else set()      # save_photo shu obyektlarning o'zini yangilaydi
        missing, total = defaultdict(list), defaultdict(int)
        for s in students:
            total[s.group.name] += 1
            if not s.user.photo and s.pk not in will_have:
                missing[s.group.name].append(f'{s.user.last_name} {s.user.first_name}')
        out(self.style.WARNING(f"\nRasmi yo'q o'quvchilar: {sum(len(v) for v in missing.values())} / {len(students)}"))
        for g in sorted(total, key=_class_key):
            names = sorted(missing.get(g, []))
            out(f'{g}: {len(names)} / {total[g]} rasmsiz' + (':' if names else ''))
            for n in names:
                out(f'  - {n}')


def _class_key(name):
    import re
    m = re.match(r'(\d+)', name)
    return (int(m.group(1)) if m else 99, name)
