from django.db import migrations

# Lavozim namunalariga qo'shiladigan yangi ruxsatlar (mavjud sozlamalar o'chirilmaydi, faqat to'ldiriladi)
ADD = {
    'Maktab egasi': ['payments.view', 'payments.accept', 'payments.discounts', 'payments.settings', 'payments.reports', 'payments.void'],
    'Direktor': ['payments.view', 'payments.accept', 'payments.discounts', 'payments.settings', 'payments.reports', 'payments.void'],
    'Reception': ['payments.view', 'payments.accept'],
    'Hisobchi': ['payments.view', 'payments.reports'],
}


def migrate_perms(apps, schema_editor):
    """'sensitive.payments' -> 'payments.view'. Lavozim namunalariga yangi to'lov ruxsatlari qo'shiladi."""
    Position, Staff = apps.get_model('panel', 'Position'), apps.get_model('panel', 'StaffProfile')
    for pos in Position.objects.all():
        perms = ['payments.view' if p == 'sensitive.payments' else p for p in pos.default_perms]
        perms += [p for p in ADD.get(pos.name, []) if p not in perms]
        pos.default_perms = list(dict.fromkeys(perms))
        pos.save(update_fields=['default_perms'])
    for st in Staff.objects.select_related('position'):
        perms = ['payments.view' if p == 'sensitive.payments' else p for p in st.perms]
        st.perms = list(dict.fromkeys(perms))
        st.save(update_fields=['perms'])


class Migration(migrations.Migration):
    dependencies = [('panel', '0002_seed_positions')]
    operations = [migrations.RunPython(migrate_perms, migrations.RunPython.noop)]
