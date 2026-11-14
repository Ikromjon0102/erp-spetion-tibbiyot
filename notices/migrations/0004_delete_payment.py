from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('notices', '0003_copy_payments_to_billing')]
    operations = [migrations.DeleteModel(name='Payment')]
