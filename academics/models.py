from django.conf import settings
from django.db import models


class Group(models.Model):
    name = models.CharField('Guruh nomi', max_length=50, unique=True)
    year = models.PositiveSmallIntegerField('O\'quv yili (boshlanishi)', default=2026)

    class Meta:
        verbose_name = 'Guruh'
        verbose_name_plural = 'Guruhlar'
        ordering = ['name']

    def __str__(self):
        return self.name


class Subject(models.Model):
    name = models.CharField('Fan nomi', max_length=100, unique=True)

    class Meta:
        verbose_name = 'Fan'
        verbose_name_plural = 'Fanlar'
        ordering = ['name']

    def __str__(self):
        return self.name


class Teaching(models.Model):
    """Ustoz + fan + guruh bog'lanishi (kim kimga qaysi fanni o'qitadi)."""
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='teachings', limit_choices_to={'role': 'teacher'},
                                verbose_name='Ustoz')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='teachings', verbose_name='Fan')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='teachings', verbose_name='Guruh')

    class Meta:
        verbose_name = 'Dars biriktirish'
        verbose_name_plural = 'Darslar biriktirish'
        unique_together = ('teacher', 'subject', 'group')

    def __str__(self):
        return f'{self.subject} — {self.group} ({self.teacher or "ustozsiz"})'


class Lesson(models.Model):
    class Weekday(models.IntegerChoices):
        MON = 0, 'Dushanba'
        TUE = 1, 'Seshanba'
        WED = 2, 'Chorshanba'
        THU = 3, 'Payshanba'
        FRI = 4, 'Juma'
        SAT = 5, 'Shanba'

    teaching = models.ForeignKey(Teaching, on_delete=models.CASCADE, related_name='lessons', verbose_name='Dars')
    weekday = models.PositiveSmallIntegerField('Hafta kuni', choices=Weekday.choices)
    period = models.PositiveSmallIntegerField('Dars soati (1-8)', default=1)
    start = models.TimeField('Boshlanishi')
    end = models.TimeField('Tugashi')
    room = models.CharField('Xona', max_length=30, blank=True)
    # Jadval yangilanganda eski darslar o'chirilmaydi (davomat tarixi saqlansin), faqat yashiriladi
    active = models.BooleanField('Faol', default=True)

    class Meta:
        verbose_name = 'Dars jadvali'
        verbose_name_plural = 'Dars jadvali'
        ordering = ['weekday', 'period', 'start']

    def __str__(self):
        return f'{self.get_weekday_display()} {self.period}-soat — {self.teaching}'
