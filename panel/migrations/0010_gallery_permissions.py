from django.db import migrations

GALLERY = ['gallery.view', 'gallery.manage']
POSITIONS = ('Maktab egasi', 'Direktor', 'Filial rahbari')


def add_perms(apps, schema_editor):
    """Galereya ruxsatlari: lavozim namunalariga va shu lavozimdagi mavjud xodimlarga (yangi modul — ular uchun bu kundalik ish)."""
    Position = apps.get_model('panel', 'Position')
    StaffProfile = apps.get_model('panel', 'StaffProfile')
    for pos in Position.objects.filter(name__in=POSITIONS):
        pos.default_perms = list(pos.default_perms) + [p for p in GALLERY if p not in pos.default_perms]
        pos.save(update_fields=['default_perms'])
        for sp in StaffProfile.objects.filter(position=pos):
            sp.perms = list(sp.perms) + [p for p in GALLERY if p not in sp.perms]
            sp.save(update_fields=['perms'])


class Migration(migrations.Migration):
    dependencies = [('panel', '0009_students_move_perm')]
    operations = [migrations.RunPython(add_perms, migrations.RunPython.noop)]
