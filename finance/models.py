from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

SALARY_CATEGORY = 'Maosh'


class Method(models.TextChoices):
    CASH = 'cash', 'Naqd'
    CARD = 'card', 'Plastik karta'
    TRANSFER = 'transfer', "Pul o'tkazmasi (bank)"


class ExpenseCategory(models.Model):
    name = models.CharField('Nomi', max_length=60, unique=True)
    order = models.PositiveSmallIntegerField('Tartib', default=0)
    is_system = models.BooleanField('Tizim kategoriyasi', default=False, editable=False,
                                    help_text="Masalan «Maosh»: oyliklar to'langanda avtomatik shu kategoriyaga yoziladi")

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Xarajat kategoriyasi'
        verbose_name_plural = 'Xarajat kategoriyalari'

    def __str__(self):
        return self.name


class Expense(models.Model):
    """Bitta xarajat (chiqim). Har doim filialga bog'lanadi; ko'rish ruxsati filial bo'yicha."""
    branch = models.ForeignKey('org.Branch', on_delete=models.PROTECT, related_name='expenses', verbose_name='Filial')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='expenses', verbose_name='Kategoriya')
    date = models.DateField('Sana', default=timezone.localdate)
    amount = models.DecimalField('Summa (so\'m)', max_digits=14, decimal_places=0, validators=[MinValueValidator(1)])
    payee = models.CharField('Kimga / nima uchun', max_length=150, blank=True)
    method = models.CharField("To'lov usuli", max_length=10, choices=Method.choices, default=Method.CASH)
    note = models.CharField('Izoh', max_length=300, blank=True)
    receipt = models.ImageField('Chek rasmi', upload_to='receipts/', blank=True, null=True)
    recurring = models.ForeignKey('RecurringExpense', on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses',
                                  editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Xarajat'
        verbose_name_plural = 'Xarajatlar'

    def __str__(self):
        return f'{self.date:%d.%m.%Y} {self.category} {self.amount}'


class RecurringExpense(models.Model):
    """Har oy takrorlanadigan xarajat (ijara, kommunal...). Oyiga bir marta Expense yaratiladi (`create_for`)."""
    branch = models.ForeignKey('org.Branch', on_delete=models.PROTECT, related_name='recurring_expenses', verbose_name='Filial')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, verbose_name='Kategoriya')
    amount = models.DecimalField("Summa (so'm)", max_digits=14, decimal_places=0, validators=[MinValueValidator(1)])
    payee = models.CharField('Kimga / nima uchun', max_length=150, blank=True)
    day = models.PositiveSmallIntegerField('Oyning nechanchi kuni', default=1, validators=[MinValueValidator(1), MaxValueValidator(28)])
    method = models.CharField("To'lov usuli", max_length=10, choices=Method.choices, default=Method.TRANSFER)
    start_month = models.DateField('Qaysi oydan', default=timezone.localdate)
    end_month = models.DateField('Qaysi oygacha (bo\'sh = muddatsiz)', null=True, blank=True)
    is_active = models.BooleanField('Faol', default=True)

    class Meta:
        ordering = ['branch', 'category', 'payee']
        verbose_name = 'Takroriy xarajat'
        verbose_name_plural = 'Takroriy xarajatlar'

    def covers(self, month):
        first = month.replace(day=1)
        return (self.is_active and self.start_month.replace(day=1) <= first
                and (self.end_month is None or first <= self.end_month.replace(day=1)))

    def create_for(self, month, user=None):
        """Berilgan oy uchun xarajat yozadi (oyda bir marta); yozilgan bo'lsa yoki oy qamramasa None."""
        month = month.replace(day=1)
        if not self.covers(month) or self.expenses.filter(date__year=month.year, date__month=month.month).exists():
            return None
        return Expense.objects.create(branch=self.branch, category=self.category, date=month.replace(day=self.day), amount=self.amount,
                                      payee=self.payee, method=self.method, recurring=self, created_by=user, note='Takroriy xarajat')

    def __str__(self):
        return f'{self.category} {self.amount} ({self.payee})'


class SalaryRule(models.Model):
    """Xodimning oylik qoidasi. Kuchga kirish sanasi bilan saqlanadi: oylik o'zgarsa yangi qoida qo'shiladi, eski oylar o'zgarmaydi.
    Qat'iy oylik yoki foiz (xodimning o'quvchilari shu oy qilgan to'lovdan)."""

    class Kind(models.TextChoices):
        FIXED = 'fixed', "Qat'iy oylik"
        PERCENT = 'percent', "Foiz (o'quvchilar to'lovidan)"

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='salary_rules', verbose_name='Xodim')
    branch = models.ForeignKey('org.Branch', on_delete=models.PROTECT, related_name='salary_rules', verbose_name='Filial')
    effective_from = models.DateField('Qaysi oydan kuchga kiradi', default=timezone.localdate)
    kind = models.CharField('Turi', max_length=8, choices=Kind.choices, default=Kind.FIXED)
    amount = models.DecimalField("Oylik (so'm)", max_digits=14, decimal_places=0, default=0, validators=[MinValueValidator(0)])
    percent = models.DecimalField('Foiz (%)', max_digits=5, decimal_places=2, default=Decimal('40'),
                                  validators=[MinValueValidator(0), MaxValueValidator(100)])
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_from', '-id']
        verbose_name = 'Oylik qoidasi'
        verbose_name_plural = 'Oylik qoidalari'

    @classmethod
    def current(cls, employee, branch, month):
        """Berilgan oyda amal qiladigan qoida: kuchga kirish sanasi oy boshidan oshmagan eng yangisi."""
        month = month.replace(day=1)
        return cls.objects.filter(employee=employee, branch=branch, effective_from__lte=_month_end(month)).order_by('-effective_from', '-id').first()

    def describe(self):
        return f'{self.amount:,.0f} so\'m'.replace(',', ' ') if self.kind == self.Kind.FIXED else f'{self.percent:g}%'

    def __str__(self):
        return f'{self.employee} — {self.describe()}'


def _month_end(month):
    nxt = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


class Payslip(models.Model):
    """Xodimning bir oy uchun oyligi: hisoblangan asosiy summa + mukofot − ushlanma. To'lovlar (avans, oylik) `SalaryPayment`da."""
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payslips', verbose_name='Xodim')
    branch = models.ForeignKey('org.Branch', on_delete=models.PROTECT, related_name='payslips', verbose_name='Filial')
    month = models.DateField('Oy (1-sana)')
    kind = models.CharField('Turi', max_length=8, choices=SalaryRule.Kind.choices)
    base_amount = models.DecimalField('Hisoblangan', max_digits=14, decimal_places=0, default=0)
    bonus = models.DecimalField('Mukofot', max_digits=14, decimal_places=0, default=0, validators=[MinValueValidator(0)])
    deduction = models.DecimalField('Ushlanma (jarima)', max_digits=14, decimal_places=0, default=0, validators=[MinValueValidator(0)])
    calc_note = models.CharField('Hisob izohi', max_length=200, blank=True)
    note = models.CharField('Izoh', max_length=200, blank=True)

    class Meta:
        ordering = ['-month', 'employee__last_name', 'employee__first_name']
        constraints = [models.UniqueConstraint(fields=['employee', 'branch', 'month'], name='uniq_payslip_employee_branch_month')]
        verbose_name = 'Oylik hisobi'
        verbose_name_plural = 'Oylik hisoblari'

    @property
    def total(self):
        """To'lanishi kerak umumiy summa."""
        return max(self.base_amount + self.bonus - self.deduction, Decimal(0))

    @property
    def paid(self):
        return sum((p.amount for p in self.payments.all()), Decimal(0))

    @property
    def remaining(self):
        return self.total - self.paid

    def __str__(self):
        return f'{self.employee} {self.month:%m.%Y}: {self.total}'


class SalaryPayment(models.Model):
    """Oylikdan to'langan summa (avans yoki oylik). Yozilganda avtomatik «Maosh» kategoriyasida xarajat yaratiladi."""

    class Kind(models.TextChoices):
        ADVANCE = 'advance', 'Avans'
        SALARY = 'salary', 'Oylik'

    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField("Summa", max_digits=14, decimal_places=0, validators=[MinValueValidator(1)])
    kind = models.CharField('Turi', max_length=8, choices=Kind.choices, default=Kind.SALARY)
    paid_on = models.DateField('Sana', default=timezone.localdate)
    method = models.CharField("To'lov usuli", max_length=10, choices=Method.choices, default=Method.CASH)
    expense = models.OneToOneField(Expense, on_delete=models.SET_NULL, null=True, blank=True, related_name='salary_payment', editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-paid_on', '-id']
        verbose_name = "Oylik to'lovi"
        verbose_name_plural = "Oylik to'lovlari"
