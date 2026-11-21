from django.db import migrations


def create_default(apps, schema_editor):
    Organization = apps.get_model('org', 'Organization')
    Branch = apps.get_model('org', 'Branch')
    org, _ = Organization.objects.get_or_create(
        name='Tibbiyot maktabi',
        defaults={'short_name': 'Med maktab', 'kind': 'school', 'brand_color': '#166534', 'meals_enabled': True})
    Branch.objects.get_or_create(organization=org, name='Asosiy')


class Migration(migrations.Migration):
    dependencies = [('org', '0001_initial')]
    operations = [migrations.RunPython(create_default, migrations.RunPython.noop)]
