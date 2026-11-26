from django.db import migrations

PERM = 'students.move'


def grant(apps, schema_editor):
    """«Guruhdan-guruhga o'tkazish» — faqat «Filial rahbari» lavozimiga va shu lavozimdagi xodimlarga (2026-11-26)."""
    Position = apps.get_model('panel', 'Position')
    StaffProfile = apps.get_model('panel', 'StaffProfile')
    for pos in Position.objects.filter(name='Filial rahbari'):
        if PERM not in pos.default_perms:
            pos.default_perms = list(pos.default_perms) + [PERM]
            pos.save(update_fields=['default_perms'])
        for sp in StaffProfile.objects.filter(position=pos):
            if PERM not in sp.perms:
                sp.perms = list(sp.perms) + [PERM]
                sp.save(update_fields=['perms'])


def revoke(apps, schema_editor):
    for model in ('Position', 'StaffProfile'):
        field = 'default_perms' if model == 'Position' else 'perms'
        for obj in apps.get_model('panel', model).objects.all():
            vals = getattr(obj, field)
            if PERM in vals:
                setattr(obj, field, [v for v in vals if v != PERM])
                obj.save(update_fields=[field])


class Migration(migrations.Migration):
    dependencies = [('panel', '0008_branch_head_position')]
    operations = [migrations.RunPython(grant, revoke)]
