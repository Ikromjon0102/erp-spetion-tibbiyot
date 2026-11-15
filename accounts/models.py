from django.contrib.auth.models import AbstractUser
from django.db import models, transaction

from .phone import to_digits


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Ma\'muriyat'
        TEACHER = 'teacher', 'Ustoz'
        PARENT = 'parent', 'Ota-ona'
        STUDENT = 'student', 'O\'quvchi'
        STAFF = 'staff', 'Xodim'

    role = models.CharField('Rol', max_length=10, choices=Role.choices, default=Role.STUDENT)
    phone = models.CharField('Telefon', max_length=20, blank=True)
    phone_digits = models.CharField('Telefon (raqamlar)', max_length=15, blank=True, db_index=True, editable=False)
    is_demo = models.BooleanField(
        'Sinov hisob', default=False,
        help_text="Sinov uchun: davomat va bahoni istalgan kun va vaqtda qo'yish mumkin (oddiy ustozlarda bunday emas)")
    must_change_password = models.BooleanField(
        'Parolni almashtirishi shart', default=False,
        help_text='Bir martalik parol berilganda yoqiladi; foydalanuvchi yangi parol qo\'ygach o\'chadi')

    photo = models.ImageField('Yuz rasmi (Hikvision uchun)', upload_to='faces/', blank=True, null=True)
    access_id = models.CharField('Face ID (ustozlar uchun)', max_length=32, unique=True, null=True, blank=True,
                                 help_text="Qurilmadagi Employee ID. O'quvchilarda bu ID o'quvchi kartasida turadi")

    @property
    def device_id(self):
        """Qurilmada shu odamni tanish uchun ID: o'quvchi — o'quvchi kartasidagi, ustoz — o'z Face ID si."""
        student = getattr(self, 'student', None)
        return (student.access_id if student else self.access_id) or ''

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        self.phone_digits = to_digits(self.phone)
        with transaction.atomic():
            super().save(*args, **kwargs)
            if self.is_teacher and self.phone_digits:
                self.absorb_parent_accounts()

    def absorb_parent_accounts(self):
        """Ustozning telefon raqami ota-ona hisobidagi raqam bilan bir xil bo'lsa — bu bitta odam: ota-ona hisobi
        o'chirilib, farzandlari shu (ustoz) hisobiga o'tkaziladi. Natijada bitta login bilan ikkala rol ishlaydi."""
        for parent in User.objects.filter(phone_digits=self.phone_digits, role=self.Role.PARENT).exclude(pk=self.pk):
            for child in list(parent.children.all()):
                child.parents.add(self)
                child.parents.remove(parent)
            parent.delete()

    @property
    def has_children(self):
        """Shu hisob kamida bitta o'quvchining ota-onasi sifatida biriktirilganmi (ustoz ham ota-ona bo'lishi mumkin)."""
        return self.pk is not None and self.children.exists()

    @property
    def is_school_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_parent(self):
        return self.role == self.Role.PARENT

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    def __str__(self):
        return self.get_full_name() or self.username


class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student',
                                limit_choices_to={'role': 'student'}, verbose_name='Foydalanuvchi')
    group = models.ForeignKey('academics.Group', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='students', verbose_name='Guruh')
    parents = models.ManyToManyField(User, blank=True, related_name='children',
                                     limit_choices_to={'role__in': ['parent', 'teacher']},  # ustoz ham ota-ona bo'lishi mumkin
                                     verbose_name='Ota-onalari')
    birth_date = models.DateField('Tug\'ilgan sana', null=True, blank=True)
    access_id = models.CharField(
        'Face ID (qurilmadagi ID)', max_length=32, unique=True, null=True, blank=True,
        help_text='Bo\'sh qoldirsangiz avtomatik beriladi (9001 dan). Qurilmada ID allaqachon kiritilgan bo\'lsa, shuni yozing')

    class Meta:
        verbose_name = 'O\'quvchi'
        verbose_name_plural = 'O\'quvchilar'

    def save(self, *args, **kwargs):
        if not self.access_id:
            # Face ID bo'sh bo'lsa o'zi beriladi (9001 dan); sinov hisoblariga berilmaydi
            self.access_id = None
            if not getattr(self.user, 'is_demo', False):
                from accounts.face_ids import next_student_id
                self.access_id = next_student_id()
        super().save(*args, **kwargs)
        if self.access_id:  # ID keyinroq kiritilsa, oldin kelgan "egasiz" kirish-chiqishlar ham bog'lanadi
            from access.models import AccessEvent
            AccessEvent.objects.filter(student__isnull=True, employee_no=self.access_id).update(student=self)

    def __str__(self):
        return str(self.user)
