from django.db import migrations

EXP = ['expenses.view', 'expenses.add', 'expenses.change', 'expenses.manage', 'payroll.view', 'payroll.manage']
ADD = {
    'Maktab egasi': EXP + ['org.settings'],
    'Direktor': ['org.settings'],       # filial admini o'z tashkilotining nomi va rangini o'zgartira oladi
    'Hisobchi': EXP,                    # xarajat va oyliklar faqat hisobchi va founder; boshqalarga founder alohida beradi
}


def add_perms(apps, schema_editor):
    Position = apps.get_model('panel', 'Position')
    for pos in Position.objects.all():
        perms = list(pos.default_perms)
        perms += [p for p in ADD.get(pos.name, []) if p not in perms]
        pos.default_perms = perms
        pos.save(update_fields=['default_perms'])


class Migration(migrations.Migration):
    dependencies = [('panel', '0005_schedule_parents_devices_permissions')]
    operations = [migrations.RunPython(add_perms, migrations.RunPython.noop)]
