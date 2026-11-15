from django.core.management.base import BaseCommand
from django.db.models import Q

from accounts.face_ids import _used, next_student_id, next_teacher_id
from accounts.models import Student, User


class Command(BaseCommand):
    help = ("Face ID si yo'q o'quvchilarga (9001 dan) va ustozlarga (7001 dan) avtomatik raqam beradi. "
            "Mavjud ID lar o'zgarmaydi. Avval --dry-run bilan ko'ring.")

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="Faqat nima bo'lishini ko'rsatadi, saqlamaydi")

    def handle(self, dry_run, **opts):
        taken = _used()
        students = (Student.objects.filter(Q(access_id__isnull=True) | Q(access_id=''), user__is_demo=False).select_related('user', 'group')
                    .order_by('group__name', 'user__last_name', 'user__first_name'))
        n_students = 0
        for st in students:
            fid = next_student_id(taken)
            taken.add(fid)
            n_students += 1
            self.stdout.write(f'  {fid}  {st.user.get_full_name()} ({st.group or "—"})')
            if not dry_run:
                st.access_id = fid
                st.save(update_fields=['access_id'])
        teachers = User.objects.filter(Q(access_id__isnull=True) | Q(access_id=''), role=User.Role.TEACHER, is_demo=False).order_by('last_name', 'first_name')
        n_teachers = 0
        for u in teachers:
            fid = next_teacher_id(taken)
            taken.add(fid)
            n_teachers += 1
            self.stdout.write(f'  {fid}  {u.get_full_name()} (ustoz)')
            if not dry_run:
                u.access_id = fid
                u.save(update_fields=['access_id'])
        self.stdout.write(self.style.SUCCESS(
            f"{'Beriladi (sinov, saqlanmadi)' if dry_run else 'Berildi'}: {n_students} ta o'quvchi, {n_teachers} ta ustoz."))
