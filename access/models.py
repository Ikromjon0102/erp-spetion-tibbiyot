import secrets
from datetime import time

from django.core.cache import cache
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
    branch = models.ForeignKey('org.Branch', on_delete=models.PROTECT, null=True, blank=True, related_name='devices',
                               verbose_name='Filial')
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

    def save(self, *args, **kwargs):
        if self.branch_id is None:
            from org.models import default_branch
            self.branch = default_branch()
        super().save(*args, **kwargs)

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


LEAVE_CACHE_KEY = 'access_leave_notify_from'


class AccessSettings(models.Model):
    """Kirish-chiqish sozlamalari (bitta yozuv). Paneldan o'zgartiriladi."""
    leave_notify_from = models.TimeField(
        'Chiqish xabarlari boshlanadigan vaqt', default=time(16, 0),
        help_text="Shu vaqtdan oldingi chiqish skanlari tanaffus hisoblanadi: ota-onaga «chiqdi» xabari yuborilmaydi, holat «Tashqarida» bo'ladi")

    class Meta:
        verbose_name = 'Kirish-chiqish sozlamasi'
        verbose_name_plural = 'Kirish-chiqish sozlamalari'

    @classmethod
    def get(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(LEAVE_CACHE_KEY)


def leave_from(org=None):
    """Chiqish xabarlari boshlanadigan vaqt (datetime.time). Tashkilotda o'z vaqti bo'lsa — o'shasi, bo'lmasa umumiy (30 soniya keshlanadi)."""
    if org is not None and getattr(org, 'leave_notify_from', None):
        return org.leave_notify_from
    value = cache.get(LEAVE_CACHE_KEY)
    if value is None:
        value = AccessSettings.get().leave_notify_from
        cache.set(LEAVE_CACHE_KEY, value, 30)
    return value


def org_of_student(student):
    """O'quvchining tashkiloti (filial orqali) yoki None."""
    return student.branch.organization if getattr(student, 'branch_id', None) else None


def earliest_leave_from():
    """Barcha tashkilotlar ichidagi eng erta chiqish vaqti (cron buyrug'i shundan oldin hech narsa qilmaydi)."""
    from org.models import Organization
    times = [t for t in Organization.objects.filter(is_active=True).values_list('leave_notify_from', flat=True) if t]
    return min(times + [leave_from()])


class PresenceNotice(models.Model):
    """Ota-onaga yuborilgan «keldi» / «chiqdi» xabarlari: har bir o'quvchi uchun kuniga har turdan bittadan."""
    KINDS = [('in', 'Keldi'), ('left', 'Chiqdi')]
    student = models.ForeignKey('accounts.Student', on_delete=models.CASCADE, related_name='presence_notices')
    date = models.DateField()
    kind = models.CharField(max_length=4, choices=KINDS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'date', 'kind')


# ---- maktab kompyuteridagi agent (rasmlarni terminallarga yuboradi) ----------------------------------------------------

def hash_secret(value):
    import hashlib
    return hashlib.sha256(value.encode()).hexdigest()


class Agent(models.Model):
    """Binodagi kompyuterga o'rnatilgan agent. Faqat o'z filialining terminallari va odamlarini ko'radi.
    Kalit bazada ochiq saqlanmaydi (faqat sha256); paneldan bekor qilinsa darhol ishlamay qoladi."""
    ONLINE_SECONDS = 180

    branch = models.ForeignKey('org.Branch', on_delete=models.PROTECT, related_name='agents', verbose_name='Filial')
    name = models.CharField('Kompyuter nomi', max_length=100, blank=True)
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    key_hint = models.CharField(max_length=12, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    is_active = models.BooleanField('Faol', default=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_ip = models.CharField(max_length=64, blank=True)
    version = models.CharField(max_length=20, blank=True)
    state = models.JSONField(default=dict, blank=True)        # {device_id: {ip, mac, online, users, faces, error, at}}
    offline_alerted = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Agent'
        verbose_name_plural = 'Agentlar'
        ordering = ['-is_active', 'branch_id', '-created_at']

    @property
    def online(self):
        from django.utils import timezone
        return bool(self.is_active and self.last_seen_at and (timezone.now() - self.last_seen_at).total_seconds() < self.ONLINE_SECONDS)

    def __str__(self):
        return f'{self.name or "Agent"} ({self.branch})'


class AgentPairing(models.Model):
    """Bir martalik ulash kodi: panelda filial uchun yaratiladi, agentga kiritiladi (24 soat amal qiladi)."""
    TTL_HOURS = 24

    branch = models.ForeignKey('org.Branch', on_delete=models.CASCADE, related_name='agent_pairings')
    code_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    agent = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    @classmethod
    def issue(cls, branch, user=None):
        """Yangi kod (ochiq matni faqat shu yerda qaytadi). Shu filialning eski ishlatilmagan kodlari bekor qilinadi."""
        from datetime import timedelta
        from django.utils import timezone
        cls.objects.filter(branch=branch, used_at__isnull=True).delete()
        while True:
            digits = ''.join(secrets.choice('0123456789') for _ in range(8))
            code = f'{digits[:4]}-{digits[4:]}'
            if not cls.objects.filter(code_hash=hash_secret(digits)).exists():
                break
        cls.objects.create(branch=branch, code_hash=hash_secret(digits), created_by=user,
                           expires_at=timezone.now() + timedelta(hours=cls.TTL_HOURS))
        return code
