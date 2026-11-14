import secrets

from django.db import models


def _new_token():
    return secrets.token_urlsafe(24)


class Device(models.Model):
    """Hikvision yuz tanish terminali. Har bir qurilma o'z manziliga (token) yuboradi,
    shuning uchun kirish/chiqish yo'nalishi qurilmaning o'zidan aniqlanadi."""

    class Direction(models.TextChoices):
        IN = 'in', 'Kirish'
        OUT = 'out', 'Chiqish'

    name = models.CharField('Nomi', max_length=60, help_text='Masalan: Kirish-1')
    direction = models.CharField('Yo\'nalish', max_length=3, choices=Direction.choices)
    token = models.CharField('Maxfiy token', max_length=64, unique=True, default=_new_token, editable=False)
    is_active = models.BooleanField('Faol', default=True)
    last_seen = models.DateTimeField('Oxirgi signal', null=True, blank=True, editable=False)

    host = models.CharField('Qurilma manzili (IP)', max_length=100, blank=True, help_text="Rasmlarni yuborish uchun. Masalan: 192.168.1.64")
    port = models.PositiveIntegerField('Port', default=80)
    use_https = models.BooleanField('HTTPS', default=False)
    username = models.CharField('Qurilma logini', max_length=60, blank=True, default='admin')
    password = models.CharField('Qurilma paroli', max_length=100, blank=True)
    last_sync_at = models.DateTimeField('Oxirgi sync', null=True, blank=True, editable=False)
    last_sync_note = models.CharField('Oxirgi sync natijasi', max_length=300, blank=True, editable=False)

    class Meta:
        verbose_name = 'Qurilma'
        verbose_name_plural = 'Qurilmalar'
        ordering = ['direction', 'name']

    @property
    def push_path(self):
        return f'/api/access/hikvision/{self.token}/'

    def __str__(self):
        return f'{self.name} ({self.get_direction_display()})'


class AccessEvent(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='events', verbose_name='Qurilma')
    student = models.ForeignKey('accounts.Student', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='access_events', verbose_name='O\'quvchi')
    employee_no = models.CharField('Qurilmadagi ID', max_length=32, db_index=True)
    person_name = models.CharField('Qurilmadagi ism', max_length=100, blank=True)
    direction = models.CharField('Yo\'nalish', max_length=3, choices=Device.Direction.choices)
    occurred_at = models.DateTimeField('Vaqti')
    sub_type = models.IntegerField('Hodisa kodi', null=True, blank=True)
    raw = models.TextField('Xom ma\'lumot', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Kirish-chiqish'
        verbose_name_plural = 'Kirish-chiqishlar'
        ordering = ['-occurred_at']
        unique_together = ('device', 'employee_no', 'occurred_at')  # qurilma qayta yuborsa, takrorlanmaydi

    def __str__(self):
        return f'{self.student or self.employee_no} {self.get_direction_display()} {self.occurred_at:%d.%m %H:%M}'


class FaceSync(models.Model):
    """Qaysi odamning qaysi rasmi qaysi qurilmaga yuborilgan (o'zgarmagan bo'lsa qayta yuborilmaydi)."""
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='face_syncs')
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='face_syncs')
    employee_no = models.CharField(max_length=32)
    digest = models.CharField(max_length=64, blank=True)
    ok = models.BooleanField(default=False)
    error = models.CharField(max_length=300, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('device', 'user')
        verbose_name = 'Rasm sync holati'
        verbose_name_plural = 'Rasm sync holati'
