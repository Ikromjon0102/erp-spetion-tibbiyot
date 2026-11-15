from django import forms

from academics.models import Group
from accounts.models import Student, User
from accounts.phone import to_digits
from accounts.student_import import normalize_phone
from notices.models import Announcement

from .models import Position

DATE = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class PhoneField(forms.CharField):
    """Telefon raqam: istalgan formatda yoziladi, '+998 90 123-45-67' ko'rinishida saqlanadi."""
    def clean(self, value):
        value = super().clean(value)
        if not value and not self.required:
            return ''
        phone = normalize_phone(value)
        if phone is None:
            raise forms.ValidationError("Telefon raqam noto'g'ri. Masalan: +998 90 123-45-67")
        return phone


class StudentForm(forms.Form):
    last_name = forms.CharField(label='Familiya', max_length=150)
    first_name = forms.CharField(label='Ism', max_length=150)
    group = forms.ModelChoiceField(label='Sinf', queryset=Group.objects.all(), required=False, empty_label='— sinfsiz —')
    birth_date = forms.DateField(label="Tug'ilgan sana", required=False, widget=DATE)
    access_id = forms.CharField(label='Face ID (qurilmadagi ID)', max_length=32, required=False,
                                help_text="Bo'sh qoldirsangiz avtomatik beriladi (9001 dan). Qurilmada ID allaqachon bor bo'lsa, shuni yozing")

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        if instance is not None and 'initial' not in kwargs:
            kwargs['initial'] = {'last_name': instance.user.last_name, 'first_name': instance.user.first_name,
                                 'group': instance.group, 'birth_date': instance.birth_date, 'access_id': instance.access_id}
        super().__init__(*args, **kwargs)

    def clean_access_id(self):
        value = self.cleaned_data['access_id'].strip()
        if value:
            taken = Student.objects.filter(access_id=value)
            if self.instance is not None:
                taken = taken.exclude(pk=self.instance.pk)
            if taken.exists():
                raise forms.ValidationError(f"Bu Face ID boshqa o'quvchida: {taken.first().user.get_full_name()}")
        if not value and self.instance is not None:
            return self.instance.access_id      # tahrirda bo'sh qoldirilsa, mavjud ID saqlanadi
        return value or None


class ParentForm(forms.Form):
    name = forms.CharField(label='Ism-familiya', max_length=150)
    phone = PhoneField(label='Telefon raqam')


class StaffCreateForm(forms.Form):
    last_name = forms.CharField(label='Familiya', max_length=150)
    first_name = forms.CharField(label='Ism', max_length=150)
    phone = PhoneField(label='Telefon raqam (login)')
    position = forms.ModelChoiceField(label='Lavozim', queryset=Position.objects.all(), empty_label=None)


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'year']
        labels = {'name': 'Sinf nomi', 'year': "O'quv yili (boshlanishi)"}


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ['title', 'body', 'audience', 'group']
        labels = {'title': 'Sarlavha', 'body': 'Matn', 'audience': 'Kimlar uchun', 'group': 'Sinf (ixtiyoriy)'}
        help_texts = {'group': "Bo'sh qoldirilsa, barcha sinflarga ko'rinadi"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'].empty_label = '— hamma sinflar —'


class PositionForm(forms.Form):
    name = forms.CharField(label='Lavozim nomi', max_length=60)
    is_owner = forms.BooleanField(label="To'liq ruxsat (maktab egasi)", required=False)


class ImportForm(forms.Form):
    group = forms.CharField(label='Sinf nomi', max_length=50, required=False,
                            help_text="Bo'sh qoldirilsa, fayl nomidan olinadi (masalan: '10-sinf o'quvchilari.xlsx' → 10-Sinf)")
    file = forms.FileField(label='Excel fayl (.xlsx)')

    def clean_file(self):
        f = self.cleaned_data['file']
        if not f.name.lower().endswith('.xlsx'):
            raise forms.ValidationError('Faqat .xlsx fayl')
        if f.size > 3 * 1024 * 1024:
            raise forms.ValidationError('Fayl 3 MB dan katta bo\'lmasin')
        return f
