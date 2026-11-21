from django.conf import settings
from django.db import models


class Announcement(models.Model):
    class Audience(models.TextChoices):
        ALL = 'all', 'Hamma'
        TEACHERS = 'teachers', 'Ustozlar'
        PARENTS = 'parents', 'Ota-onalar'
        STUDENTS = 'students', 'O\'quvchilar'

    title = models.CharField('Sarlavha', max_length=200)
    body = models.TextField('Matn')
    audience = models.CharField('Kimlar uchun', max_length=10, choices=Audience.choices, default=Audience.ALL)
    group = models.ForeignKey('academics.Group', on_delete=models.CASCADE, null=True, blank=True,
                              verbose_name='Guruh (ixtiyoriy)',
                              help_text='Bo\'sh qoldirilsa, barcha guruhlarga ko\'rinadi')
    branch = models.ForeignKey('org.Branch', on_delete=models.PROTECT, null=True, blank=True, related_name='announcements',
                               verbose_name='Filial')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                               related_name='announcements', verbose_name='Muallif')
    created_at = models.DateTimeField('Yaratilgan', auto_now_add=True)

    class Meta:
        verbose_name = 'E\'lon'
        verbose_name_plural = 'E\'lonlar'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.branch_id is None:
            self.branch_id = self.group.branch_id if self.group_id else None
            if self.branch_id is None:
                from org.models import default_branch
                self.branch = default_branch()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class AnnouncementRead(models.Model):
    """Foydalanuvchi e'lonni ochib o'qigani (admin uchun: kim va qachon o'qigan)."""
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name='reads', verbose_name="E'lon")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='announcement_reads',
                             verbose_name='Foydalanuvchi')
    read_at = models.DateTimeField("O'qilgan vaqt", auto_now_add=True)

    class Meta:
        verbose_name = "O'qilgan e'lon"
        verbose_name_plural = "O'qilgan e'lonlar"
        unique_together = ('announcement', 'user')
        ordering = ['-read_at']

    def __str__(self):
        return f'{self.user} — {self.announcement} ({self.read_at:%d.%m %H:%M})'
