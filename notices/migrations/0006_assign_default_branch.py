from django.db import migrations


def assign(apps, schema_editor):
    Branch = apps.get_model('org', 'Branch')
    Announcement = apps.get_model('notices', 'Announcement')
    branch = Branch.objects.order_by('pk').first()
    if not branch:
        return
    for a in Announcement.objects.filter(branch__isnull=True).select_related('group'):
        a.branch_id = a.group.branch_id if a.group_id and a.group.branch_id else branch.pk
        a.save(update_fields=['branch'])


class Migration(migrations.Migration):
    dependencies = [('notices', '0005_announcement_branch'), ('academics', '0004_assign_default_branch'),
                    ('org', '0002_default_org')]
    operations = [migrations.RunPython(assign, migrations.RunPython.noop)]
