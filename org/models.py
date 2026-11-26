from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models


class Organization(models.Model):
    """Tashkilot: tibbiyot maktabi, asosiy maktab, bog'cha, o'quv markaz. Hammasi bitta tizimda yashaydi, ma'lumotlar
    tashkilot bo'yicha ajratiladi. Ota-ona bitta telefon raqam bilan kirib, farzandlarini turli tashkilotlardan ko'radi."""

    class Kind(models.TextChoices):
        SCHOOL = 'school', 'Maktab'
        KINDERGARTEN = 'kindergarten', "Bog'cha"
        CENTER = 'center', "O'quv markaz"

    name = models.CharField('Nomi', max_length=120, unique=True)
    short_name = models.CharField('Qisqa nomi', max_length=40, blank=True)
    kind = models.CharField('Turi', max_length=12, choices=Kind.choices, default=Kind.SCHOOL)
    brand_color = models.CharField('Brend rangi (HEX)', max_length=7, default='#166534',
                                   validators=[RegexValidator(r'^#[0-9a-fA-F]{6}$', 'Rang #RRGGBB ko\'rinishida bo\'lsin, masalan #166534')],
                                   help_text="Ilova fon rangi: tibbiyot #166534 (to'q yashil), asosiy maktab to'q ko'k, "
                                             "o'quv markaz qizil, bog'cha to'q sariq. Logo hammasida bir xil")
    meals_enabled = models.BooleanField('Taomnoma moduli', default=False,
                                        help_text="Maktab va bog'chada yoqiladi, o'quv markazda kerak emas")
    expenses_enabled = models.BooleanField('Xarajatlar moduli', default=True)
    gallery_enabled = models.BooleanField('Galereya moduli', default=False,
                                          help_text="Bolalar rasmlari albomi; ota-ona faqat o'z farzandi belgilangan rasmlarni ko'radi")
    leave_notify_from = models.TimeField("Chiqish xabarlari vaqti", null=True, blank=True,
                                         help_text="Bo'sh bo'lsa umumiy sozlama (Qurilmalar sahifasi). Bog'cha va markazning ish soati boshqa bo'lishi mumkin")
    advance_day = models.PositiveSmallIntegerField('Avans kuni', default=15, validators=[MinValueValidator(1), MaxValueValidator(28)],
                                                   help_text="Har oyning shu kuni avans beriladi; yakuniy hisob — oyning oxirgi kuni")
    is_active = models.BooleanField('Faol', default=True)
    order = models.PositiveSmallIntegerField('Tartib', default=0)

    class Meta:
        verbose_name = 'Tashkilot'
        verbose_name_plural = 'Tashkilotlar'
        ordering = ['order', 'name']

    @property
    def label(self):
        return self.short_name or self.name

    def __str__(self):
        return self.name


class Branch(models.Model):
    """Filial (kampus) — tashkilot ichida. Maktab va bog'chada odatda bitta ("Asosiy"), o'quv markazda 4-5 ta."""
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name='branches',
                                     verbose_name='Tashkilot')
    name = models.CharField('Filial nomi', max_length=100)
    address = models.CharField('Manzil', max_length=200, blank=True)
    phone = models.CharField('Telefon', max_length=30, blank=True)
    is_active = models.BooleanField('Faol', default=True)
    order = models.PositiveSmallIntegerField('Tartib', default=0)

    class Meta:
        verbose_name = 'Filial'
        verbose_name_plural = 'Filiallar'
        ordering = ['organization__order', 'order', 'name']
        constraints = [models.UniqueConstraint(fields=['organization', 'name'], name='uniq_branch_name_per_org')]

    def __str__(self):
        return f'{self.organization.label} — {self.name}'


def default_branch():
    """Birinchi faol filial (yangi yozuvlar filial ko'rsatilmasa shunga bog'lanadi)."""
    return Branch.objects.filter(is_active=True).first() or Branch.objects.first()
