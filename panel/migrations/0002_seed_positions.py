from django.db import migrations

from panel.perms import PRESETS


def seed(apps, schema_editor):
    Position = apps.get_model('panel', 'Position')
    for order, (name, is_owner, perms) in enumerate(PRESETS, 1):
        Position.objects.get_or_create(name=name, defaults={'is_owner': is_owner, 'default_perms': list(perms), 'order': order})


class Migration(migrations.Migration):
    dependencies = [('panel', '0001_initial')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
