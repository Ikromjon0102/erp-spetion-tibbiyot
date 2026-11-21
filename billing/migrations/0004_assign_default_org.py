from django.db import migrations


def assign(apps, schema_editor):
    Organization = apps.get_model('org', 'Organization')
    BillingSettings = apps.get_model('billing', 'BillingSettings')
    Discount = apps.get_model('billing', 'Discount')
    org = Organization.objects.order_by('pk').first()
    if not org:
        return
    BillingSettings.objects.filter(organization__isnull=True).update(organization=org)
    Discount.objects.filter(organization__isnull=True).update(organization=org)


class Migration(migrations.Migration):
    dependencies = [('billing', '0003_billingsettings_organization_discount_organization_and_more'), ('org', '0002_default_org')]
    operations = [migrations.RunPython(assign, migrations.RunPython.noop)]
