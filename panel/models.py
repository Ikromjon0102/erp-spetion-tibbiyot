from django.conf import settings
from django.db import models


class Position(models.Model):
    """Lavozim (direktor, zam, reception...). Faqat yorliq va boshlang'ich ruxsatlar namunasi; haqiqiy ruxsatlar
    har bir xodimda alohida (StaffProfile.perms)."""
    name = models.CharField('Lavozim', max_length=60, unique=True)
    is_owner = models.BooleanField("To'liq ruxsat (maktab egasi)", default=False,
                                   help_text="Bunday lavozimdagi xodimning ruxsatlarini cheklab bo'lmaydi")
    default_perms = models.JSONField('Boshlang\'ich ruxsatlar', default=list, blank=True)
    order = models.PositiveSmallIntegerField('Tartib', default=0)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Lavozim'
        verbose_name_plural = 'Lavozimlar'

    def __str__(self):
        return self.name


class StaffProfile(models.Model):
    """Boshqaruv paniliga kirish huquqi: lavozim + shu xodimga tanlangan ruxsatlar."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='staff_profile')
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name='staff', verbose_name='Lavozim')
    perms = models.JSONField('Ruxsatlar', default=list, blank=True)
    is_active = models.BooleanField('Panelga kirishi mumkin', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Xodim (panel)'
        verbose_name_plural = 'Xodimlar (panel)'

    @property
    def is_owner(self):
        return self.position.is_owner

    def __str__(self):
        return f'{self.user} — {self.position}'


class AuditLog(models.Model):
    """Faoliyat jurnali: kim, nimani, qachon o'zgartirgan."""
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='+', verbose_name='Kim')
    actor_name = models.CharField(max_length=150, blank=True)   # foydalanuvchi o'chirilsa ham nomi qoladi
    verb = models.CharField('Amal', max_length=60)
    target_type = models.CharField('Obyekt turi', max_length=40, blank=True)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    target_label = models.CharField('Obyekt', max_length=200, blank=True)
    details = models.JSONField('Tafsilot', default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField('Vaqt', auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Jurnal yozuvi'
        verbose_name_plural = 'Faoliyat jurnali'

    def __str__(self):
        return f'{self.actor_name}: {self.verb} {self.target_label}'
