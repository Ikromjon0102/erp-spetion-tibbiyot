from datetime import date

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


# Namuna matn: haqiqiy rekvizitlar panel -> To'lovlar -> Sozlamalar'da kiritiladi. Raqamlar ataylab nol — bu hisobga pul o'tmaydi.
PAY_INFO_SAMPLE = """NAMUNA — haqiqiy rekvizitlar bilan almashtiring
Qabul qiluvchi: «Spetion» xususiy maktabi MChJ
Hisob raqam: 0000 0000 0000 0000 0000
Bank: «Namuna bank» ATB, MFO 00000
STIR (INN): 000 000 000
To'lov maqsadi: o'quvchining familiyasi, ismi va sinfi
Naqd to'lov: maktab kassasi, Du–Sha 9:00–17:00"""


class BillingSettings(models.Model):
    """Yagona (bitta) sozlama yozuvi: oylik narx, to'lov muddati va hisob boshlanadigan oy."""
    monthly_price = models.DecimalField('Oylik narx (so\'m)', max_digits=12, decimal_places=0, default=0)
    due_day = models.PositiveSmallIntegerField("To'lov muddati (oyning nechanchi kunigacha)", default=10,
                                               validators=[MinValueValidator(1), MaxValueValidator(28)])
    billing_start = models.DateField("Hisob boshlanadigan oy", null=True, blank=True,
                                     help_text="Shu oydan boshlab o'quvchilarga hisob yoziladi (oyning 1-sanasi)")
    pay_info = models.TextField("To'lov yo'riqnomasi (rekvizitlar)", blank=True, default=PAY_INFO_SAMPLE,
                                help_text="Ota-ona ilovasida «To'lov» bo'limida ko'rsatiladi. Bo'sh qoldirilsa ko'rinmaydi")

    @property
    def pay_info_is_sample(self):
        return self.pay_info.strip() == PAY_INFO_SAMPLE.strip()

    class Meta:
        verbose_name = 'Moliya sozlamalari'
        verbose_name_plural = 'Moliya sozlamalari'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'billing_start': timezone.localdate().replace(day=1)})
        return obj

    def __str__(self):
        return f'Oylik narx: {self.monthly_price}'


class Discount(models.Model):
    """Chegirma turi (katalog): nomi va foizi. Standart holatda hech kimda chegirma yo'q — kerakli o'quvchiga biriktiriladi."""
    name = models.CharField('Nomi', max_length=100, unique=True)
    percent = models.DecimalField('Foiz (%)', max_digits=5, decimal_places=2,
                                  validators=[MinValueValidator(0), MaxValueValidator(100)])
    description = models.CharField('Izoh', max_length=200, blank=True,
                                   help_text="Masalan: oilada 2 va undan ko'p farzand o'qisa")
    is_active = models.BooleanField('Faol', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-percent', 'name']
        verbose_name = 'Chegirma'
        verbose_name_plural = 'Chegirmalar'

    def __str__(self):
        return f'{self.name} (−{self.percent:g}%)'


class StudentDiscount(models.Model):
    """O'quvchiga biriktirilgan chegirma. Bir necha chegirma bo'lsa, eng kattasi qo'llanadi."""
    student = models.ForeignKey('accounts.Student', on_delete=models.CASCADE, related_name='discounts')
    discount = models.ForeignKey(Discount, on_delete=models.PROTECT, related_name='assignments')
    valid_from = models.DateField('Qaysi oydan', null=True, blank=True)
    valid_to = models.DateField('Qaysi oygacha (shu oy ham)', null=True, blank=True)
    note = models.CharField('Sabab / izoh', max_length=200, blank=True)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "O'quvchi chegirmasi"
        verbose_name_plural = "O'quvchi chegirmalari"

    def covers(self, month):
        return (self.valid_from is None or self.valid_from <= month) and (self.valid_to is None or month <= self.valid_to)

    def __str__(self):
        return f'{self.student} — {self.discount}'


class Charge(models.Model):
    """Bir oy uchun hisoblangan summa. Hisoblangan paytdagi narx va chegirma saqlanadi (keyin narx o'zgarsa, eski oy o'zgarmaydi)."""
    student = models.ForeignKey('accounts.Student', on_delete=models.CASCADE, related_name='charges')
    month = models.DateField('Oy (1-sana)')
    base_price = models.DecimalField('Asosiy narx', max_digits=12, decimal_places=0)
    discount_percent = models.DecimalField('Chegirma (%)', max_digits=5, decimal_places=2, default=0)
    discount_label = models.CharField('Chegirma izohi', max_length=200, blank=True)
    amount = models.DecimalField("To'lanadigan summa", max_digits=12, decimal_places=0)
    cancelled = models.BooleanField('Bekor qilingan', default=False)
    cancel_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['month']
        unique_together = ('student', 'month')
        verbose_name = 'Oylik hisob'
        verbose_name_plural = 'Oylik hisoblar'

    def __str__(self):
        return f'{self.student} {self.month:%Y-%m}: {self.amount}'


class Payment(models.Model):
    """Qabul qilingan to'lov. Qisman to'lov mumkin; ortiqcha summa keyingi oylar hisobiga o'tadi."""
    class Method(models.TextChoices):
        CASH = 'cash', 'Naqd'
        TERMINAL = 'terminal', "To'lov tizimi (Payme, Click...)"
        CARD = 'card', 'Plastik karta'
        TRANSFER = 'transfer', "Pul o'tkazmasi (bank)"

    student = models.ForeignKey('accounts.Student', on_delete=models.CASCADE, related_name='fee_payments')
    amount = models.DecimalField('Summa', max_digits=12, decimal_places=0, validators=[MinValueValidator(1)])
    method = models.CharField('Usul', max_length=10, choices=Method.choices, default=Method.CASH)
    paid_on = models.DateField('To\'lov sanasi', default=timezone.localdate)
    receipt_no = models.CharField('Chek raqami', max_length=20, blank=True, db_index=True)
    note = models.CharField('Izoh', max_length=200, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    voided = models.BooleanField('Bekor qilingan', default=False)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-paid_on', '-id']
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.receipt_no:   # chek raqami: yil-oy va tartib raqami, masalan CH2611-00042
            self.receipt_no = f'CH{self.paid_on:%y%m}-{self.pk:05d}'
            super().save(update_fields=['receipt_no'])

    def __str__(self):
        return f'{self.receipt_no} {self.student} {self.amount}'
