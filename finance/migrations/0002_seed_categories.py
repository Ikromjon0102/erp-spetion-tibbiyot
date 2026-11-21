from django.db import migrations

CATEGORIES = [
    ('Ijara', 1, False), ('Kommunal (svet, gaz, suv)', 2, False), ("Oziq-ovqat (taomnoma uchun)", 3, False),
    ("Jihoz va ta'mirlash", 4, False), ('Reklama', 5, False), ('Soliq va to\'lovlar', 6, False), ('Transport', 7, False),
    ('Maosh', 8, True), ('Boshqa', 99, False),
]


def seed(apps, schema_editor):
    ExpenseCategory = apps.get_model('finance', 'ExpenseCategory')
    for name, order, system in CATEGORIES:
        ExpenseCategory.objects.get_or_create(name=name, defaults={'order': order, 'is_system': system})


class Migration(migrations.Migration):
    dependencies = [('finance', '0001_initial')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
