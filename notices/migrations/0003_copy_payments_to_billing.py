from collections import Counter

from django.db import migrations


def copy_payments(apps, schema_editor):
    """Eski "oyiga bitta yozuv" to'lovlarini yangi tizimga o'tkazadi: oylik hisob + (to'langan bo'lsa) alohida to'lov."""
    Old = apps.get_model('notices', 'Payment')
    Charge, NewPayment = apps.get_model('billing', 'Charge'), apps.get_model('billing', 'Payment')
    Settings = apps.get_model('billing', 'BillingSettings')
    rows = list(Old.objects.all())
    for p in rows:
        month = p.month.replace(day=1)
        Charge.objects.get_or_create(student_id=p.student_id, month=month, defaults={'base_price': p.amount, 'amount': p.amount})
        if p.paid and p.paid > 0:
            paid_on = p.paid_at or month
            pay = NewPayment.objects.create(student_id=p.student_id, amount=p.paid, method='cash', paid_on=paid_on,
                                            note="Eski yozuvdan ko'chirilgan")
            pay.receipt_no = f'CH{paid_on:%y%m}-{pay.pk:05d}'
            pay.save(update_fields=['receipt_no'])
    if rows and not Settings.objects.exists():
        price = Counter(p.amount for p in rows).most_common(1)[0][0]
        Settings.objects.create(pk=1, monthly_price=price, billing_start=min(p.month.replace(day=1) for p in rows))


class Migration(migrations.Migration):
    dependencies = [
        ('notices', '0002_announcement_reads'),
        ('billing', '0001_initial'),
    ]
    operations = [migrations.RunPython(copy_payments, migrations.RunPython.noop)]
