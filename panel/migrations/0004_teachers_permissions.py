from django.db import migrations

ADD = {
    'Maktab egasi': ['teachers.view', 'teachers.add', 'teachers.change'],
    'Direktor': ['teachers.view', 'teachers.add', 'teachers.change'],
    "Zam (o'quv ishlari)": ['teachers.view', 'teachers.change'],
    'Reception': ['teachers.view'],
}


def add_perms(apps, schema_editor):
    """Lavozim namunalariga ustozlar ruxsatlari qo'shiladi (xodimlarning shaxsiy ruxsatlari o'zgarmaydi)."""
    Position = apps.get_model('panel', 'Position')
    for pos in Position.objects.all():
        perms = list(pos.default_perms)
        perms += [p for p in ADD.get(pos.name, []) if p not in perms]
        pos.default_perms = perms
        pos.save(update_fields=['default_perms'])


class Migration(migrations.Migration):
    dependencies = [('panel', '0003_payments_permissions')]
    operations = [migrations.RunPython(add_perms, migrations.RunPython.noop)]
