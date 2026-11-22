from django.conf import settings
from django.db import models


class ExamLink(models.Model):
    """ERP o'quvchisi ↔ exam platformasidagi o'quvchi. Juftni xodim tasdiqlaydi (ism avtomatik taklif qilinadi)."""
    student = models.OneToOneField('accounts.Student', on_delete=models.CASCADE, related_name='exam_link')
    exam_student_id = models.PositiveIntegerField('Exam o\'quvchi ID', unique=True)
    exam_name = models.CharField('Exam\'dagi ism', max_length=255, blank=True)
    exam_class = models.CharField('Exam\'dagi sinf', max_length=40, blank=True)
    linked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Exam bog\'lanishi'
        verbose_name_plural = 'Exam bog\'lanishlari'

    def __str__(self):
        return f'{self.student} ↔ exam #{self.exam_student_id}'
