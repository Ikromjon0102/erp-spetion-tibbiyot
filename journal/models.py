from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'present', 'Keldi'
        LATE = 'late', 'Kechikdi'
        EXCUSED = 'excused', 'Sababli'
        ABSENT = 'absent', 'Kelmadi'

    student = models.ForeignKey('accounts.Student', on_delete=models.CASCADE, related_name='attendance',
                                verbose_name='O\'quvchi')
    lesson = models.ForeignKey('academics.Lesson', on_delete=models.CASCADE, related_name='attendance',
                               verbose_name='Dars soati')
    date = models.DateField('Sana', default=timezone.localdate)
    status = models.CharField('Holat', max_length=10, choices=Status.choices, default=Status.PRESENT)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='+', editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Davomat'
        verbose_name_plural = 'Davomat'
        unique_together = ('student', 'lesson', 'date')
        ordering = ['-date', 'lesson__period']

    def __str__(self):
        return f'{self.student} {self.date} {self.get_status_display()}'


class Grade(models.Model):
    class Kind(models.TextChoices):
        CURRENT = 'current', 'Joriy'
        TEST = 'test', 'Nazorat ishi'
        EXAM = 'exam', 'Imtihon'

    student = models.ForeignKey('accounts.Student', on_delete=models.CASCADE, related_name='grades',
                                verbose_name='O\'quvchi')
    teaching = models.ForeignKey('academics.Teaching', on_delete=models.CASCADE, related_name='grades',
                                 verbose_name='Dars')
    date = models.DateField('Sana', default=timezone.localdate)
    score = models.PositiveSmallIntegerField('Baho (1-5)', validators=[MinValueValidator(1), MaxValueValidator(5)])
    kind = models.CharField('Turi', max_length=10, choices=Kind.choices, default=Kind.CURRENT)
    comment = models.CharField('Izoh', max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   related_name='+', editable=False)
    # Qaysi dars soatida qo'yilgan: bir darsda o'quvchiga faqat bitta baho (eski yozuvlarda bo'sh bo'lishi mumkin)
    lesson = models.ForeignKey('academics.Lesson', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='lesson_grades', verbose_name='Dars soati')

    class Meta:
        verbose_name = 'Baho'
        verbose_name_plural = 'Baholar'
        ordering = ['-date', '-id']
        constraints = [
            models.UniqueConstraint(fields=['student', 'lesson', 'date'], condition=models.Q(lesson__isnull=False),
                                    name='one_grade_per_student_lesson_day'),
        ]

    def __str__(self):
        return f'{self.student} — {self.score}'


class Homework(models.Model):
    """Sinfga berilgan uy vazifasi (matn). Ota-ona o'z farzandi sinfidagi vazifalarni fan bo'yicha ko'radi."""
    teaching = models.ForeignKey('academics.Teaching', on_delete=models.CASCADE, related_name='homeworks',
                                 verbose_name='Ustoz, fan va sinf')
    text = models.TextField('Vazifa matni', max_length=2000)
    due_date = models.DateField('Topshirish sanasi')
    assigned_on = models.DateField('Berilgan sana', default=timezone.localdate)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   related_name='+', editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Vazifa'
        verbose_name_plural = 'Vazifalar'
        ordering = ['-assigned_on', '-id']

    def __str__(self):
        return f'{self.teaching.subject} · {self.teaching.group} · {self.due_date:%d.%m}'


class HomeworkRead(models.Model):
    """Ota-ona vazifani ochib ko'rgani (qizil nuqta shu bo'yicha yo'qoladi)."""
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE, related_name='reads')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='homework_reads')
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('homework', 'user')
