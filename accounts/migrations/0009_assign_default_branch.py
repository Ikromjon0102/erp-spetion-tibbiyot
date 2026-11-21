from django.db import migrations


def assign(apps, schema_editor):
    Branch = apps.get_model('org', 'Branch')
    Student = apps.get_model('accounts', 'Student')
    User = apps.get_model('accounts', 'User')
    branch = Branch.objects.order_by('pk').first()
    if not branch:
        return
    for s in Student.objects.filter(branch__isnull=True).select_related('group'):
        s.branch_id = (s.group.branch_id if s.group_id and s.group.branch_id else branch.pk)
        s.save(update_fields=['branch'])
    # ustoz, ma'muriyat va xodimlar hozircha bitta (mavjud) filialda ishlaydi
    for u in User.objects.filter(role__in=['teacher', 'admin', 'staff']):
        u.branches.add(branch)


class Migration(migrations.Migration):
    dependencies = [('accounts', '0008_student_branch_user_branches'), ('academics', '0004_assign_default_branch'),
                    ('org', '0002_default_org')]
    operations = [migrations.RunPython(assign, migrations.RunPython.noop)]
