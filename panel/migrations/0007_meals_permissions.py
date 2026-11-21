from django.db import migrations

MEALS = ['meals.view', 'meals.manage']
ADD = {'Maktab egasi': MEALS, 'Direktor': MEALS, 'Zavxoz': MEALS}


def add_perms(apps, schema_editor):
    Position = apps.get_model('panel', 'Position')
    for pos in Position.objects.all():
        perms = list(pos.default_perms)
        perms += [p for p in ADD.get(pos.name, []) if p not in perms]
        pos.default_perms = perms
        pos.save(update_fields=['default_perms'])


class Migration(migrations.Migration):
    dependencies = [('panel', '0006_expenses_payroll_org_permissions')]
    operations = [migrations.RunPython(add_perms, migrations.RunPython.noop)]
