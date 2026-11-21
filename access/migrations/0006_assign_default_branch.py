from django.db import migrations


def assign(apps, schema_editor):
    Branch = apps.get_model('org', 'Branch')
    Model = apps.get_model('access', 'Device')
    branch = Branch.objects.order_by('pk').first()
    if branch:
        Model.objects.filter(branch__isnull=True).update(branch=branch)


class Migration(migrations.Migration):
    dependencies = [('access', '0005_device_branch'), ('org', '0002_default_org')]
    operations = [migrations.RunPython(assign, migrations.RunPython.noop)]
