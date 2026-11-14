from django.db import migrations

ALL = ['parents.view', 'parents.add', 'parents.change', 'schedule.view', 'schedule.change', 'devices.view', 'devices.manage']
ADD = {
    'Maktab egasi': ALL,
    'Direktor': ALL,
    "Zam (o'quv ishlari)": ['schedule.view', 'schedule.change', 'parents.view'],
    'Reception': ['parents.view', 'parents.add', 'parents.change', 'schedule.view'],
    'Zavxoz': ['schedule.view', 'devices.view'],
}


def add_perms(apps, schema_editor):
    Position = apps.get_model('panel', 'Position')
    for pos in Position.objects.all():
        perms = list(pos.default_perms)
        perms += [p for p in ADD.get(pos.name, []) if p not in perms]
        pos.default_perms = perms
        pos.save(update_fields=['default_perms'])


class Migration(migrations.Migration):
    dependencies = [('panel', '0004_teachers_permissions')]
    operations = [migrations.RunPython(add_perms, migrations.RunPython.noop)]
