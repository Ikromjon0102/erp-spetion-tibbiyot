from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

WEEKDAYS = [(0, 'Du'), (1, 'Se'), (2, 'Ch'), (3, 'Pa'), (4, 'Ju'), (5, 'Sh'), (6, 'Ya')]


class Dish(models.Model):
    """Taom. Rasmi bir marta yuklanadi va menyuning hamma kunlarida, har siklda qayta ishlatiladi (oshpaz platformaga kirmaydi).
    Bitta taom bir nechta tashkilotda ishlatilishi mumkin (non, choy, osh...), shuning uchun umumiy."""
    name = models.CharField('Nomi', max_length=120, unique=True)
    photo = models.ImageField('Rasmi', upload_to='dishes/', blank=True, null=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Taom'
        verbose_name_plural = 'Taomlar'

    def __str__(self):
        return self.name


class MealPlan(models.Model):
    """Tashkilotning taomnoma sozlamasi: sikl uzunligi (14 kun), qaysi kunlari ovqat beriladi va sikl qaysi kundan boshlangani.
    Sikl faqat ovqat beriladigan kunlar bo'yicha ketadi: dam olish, bayram va ta'til kunlarida to'xtab turadi."""
    organization = models.OneToOneField('org.Organization', on_delete=models.CASCADE, related_name='meal_plan', verbose_name='Tashkilot')
    cycle_length = models.PositiveSmallIntegerField('Sikl uzunligi (kun)', default=14, validators=[MinValueValidator(1), MaxValueValidator(31)])
    weekdays = models.CharField('Ovqat beriladigan hafta kunlari', max_length=20, default='0,1,2,3,4,5')
    anchor_date = models.DateField('Sikl hisobi boshlangan sana', default=timezone.localdate)
    anchor_day = models.PositiveSmallIntegerField('Shu sanadagi sikl kuni', default=1, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = 'Taomnoma sozlamasi'
        verbose_name_plural = 'Taomnoma sozlamalari'

    @property
    def days(self):
        return {int(x) for x in self.weekdays.split(',') if x.strip().isdigit()}

    def is_served_day(self, d):
        if d.weekday() not in self.days:
            return False
        return not NoMealDay.objects.filter(organization_id=self.organization_id, start__lte=d, end__gte=d).exists()

    def cycle_day(self, d):
        """Berilgan sana sikldagi nechanchi kun (1..cycle_length); ovqat berilmaydigan kun yoki hisob boshidan oldingi sana bo'lsa None."""
        if d < self.anchor_date or not self.is_served_day(d):
            return None
        holidays = list(NoMealDay.objects.filter(organization_id=self.organization_id, end__gte=self.anchor_date, start__lte=d))
        days, served, cur = self.days, 0, self.anchor_date
        while cur < d:
            if cur.weekday() in days and not any(h.start <= cur <= h.end for h in holidays):
                served += 1
            cur += timedelta(days=1)
        return (self.anchor_day - 1 + served) % self.cycle_length + 1

    def set_today(self, day, today=None):
        """«Bugun sikldagi N-kun» deb belgilash: hisob shu sanadan boshlanadi."""
        self.anchor_date, self.anchor_day = today or timezone.localdate(), min(max(day, 1), self.cycle_length)

    def set_weekdays(self, new_days, today=None):
        """Ovqat beriladigan kunlar o'zgarganda (masalan dekabrdan shanba qo'shilsa) sikl hisobi buzilmasligi uchun
        avval bugungi sikl kunini eski sozlama bo'yicha aniqlab, hisobni bugundan qayta boshlaymiz."""
        today = today or timezone.localdate()
        current = self.cycle_day(today)
        if current is None:     # bugun ovqat berilmaydi: keyingi ovqat beriladigan kun uchun hisoblaymiz
            probe = today
            for _ in range(14):
                probe += timedelta(days=1)
                current = self.cycle_day(probe)
                if current is not None:
                    break
            today = probe if current is not None else today
        self.weekdays = ','.join(str(d) for d in sorted(new_days))
        if current is not None:
            self.anchor_date, self.anchor_day = today, current

    def __str__(self):
        return f'{self.organization} — {self.cycle_length} kunlik sikl'


class MealType(models.Model):
    """Ovqat turi (tushlik, ikkinchi tushlik/poldnik, nonushta...). Tashkilot o'zi qaysilari borligini belgilaydi."""
    organization = models.ForeignKey('org.Organization', on_delete=models.CASCADE, related_name='meal_types', verbose_name='Tashkilot')
    name = models.CharField('Nomi', max_length=60)
    order = models.PositiveSmallIntegerField('Tartib', default=0)
    is_active = models.BooleanField('Faol', default=True)

    class Meta:
        ordering = ['order', 'id']
        constraints = [models.UniqueConstraint(fields=['organization', 'name'], name='uniq_mealtype_per_org')]
        verbose_name = 'Ovqat turi'
        verbose_name_plural = 'Ovqat turlari'

    def __str__(self):
        return self.name


class MenuEntry(models.Model):
    """Sikldagi bir kun, bir ovqat turi uchun taomlar. `not_served` — o'sha kuni bu ovqat «ko'zda tutilmagan» (masalan poldnik yo'q)."""
    organization = models.ForeignKey('org.Organization', on_delete=models.CASCADE, related_name='menu_entries')
    cycle_day = models.PositiveSmallIntegerField('Sikl kuni')
    meal_type = models.ForeignKey(MealType, on_delete=models.CASCADE, related_name='entries')
    dishes = models.ManyToManyField(Dish, through='MenuDish', related_name='entries')
    not_served = models.BooleanField("Ko'zda tutilmagan", default=False)

    class Meta:
        ordering = ['cycle_day', 'meal_type__order']
        constraints = [models.UniqueConstraint(fields=['organization', 'cycle_day', 'meal_type'], name='uniq_menu_entry')]
        verbose_name = 'Menyu yozuvi'
        verbose_name_plural = 'Menyu yozuvlari'

    def ordered_dishes(self):
        return [md.dish for md in self.items.select_related('dish').order_by('order', 'id')]

    def __str__(self):
        return f'{self.cycle_day}-kun · {self.meal_type}'


class MenuDish(models.Model):
    entry = models.ForeignKey(MenuEntry, on_delete=models.CASCADE, related_name='items')
    dish = models.ForeignKey(Dish, on_delete=models.PROTECT, related_name='menu_items')
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        constraints = [models.UniqueConstraint(fields=['entry', 'dish'], name='uniq_menu_dish')]


class NoMealDay(models.Model):
    """Ovqat berilmaydigan kunlar (bayram, ta'til): bu kunlarda sikl to'xtab turadi."""
    organization = models.ForeignKey('org.Organization', on_delete=models.CASCADE, related_name='no_meal_days')
    start = models.DateField('Boshlanishi')
    end = models.DateField('Tugashi')
    reason = models.CharField('Sabab', max_length=100, blank=True)

    class Meta:
        ordering = ['-start']
        verbose_name = "Ovqatsiz kun (ta'til)"
        verbose_name_plural = "Ovqatsiz kunlar (ta'til)"

    def __str__(self):
        return f'{self.start:%d.%m.%Y}–{self.end:%d.%m.%Y} {self.reason}'
