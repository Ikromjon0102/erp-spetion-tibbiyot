from django import forms
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from org import theme
from org.models import Organization
from org.scope import current_org, orgs_for

from . import audit
from .access import is_owner, panel_required


class OrgForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ['name', 'short_name', 'brand_color', 'meals_enabled', 'expenses_enabled']
        labels = {'name': 'Tashkilot nomi', 'short_name': 'Qisqa nomi (ilovada)', 'brand_color': 'Brend rangi'}
        widgets = {'brand_color': forms.TextInput(attrs={'type': 'color', 'style': 'width:90px;height:44px;padding:2px'})}

    def __init__(self, *args, owner=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not owner:       # modullarni yoqish-o'chirishni faqat egasi (founder) qiladi
            del self.fields['meals_enabled'], self.fields['expenses_enabled']

    def clean_brand_color(self):
        value = self.cleaned_data['brand_color'].strip()
        if not theme.is_valid(value):
            raise forms.ValidationError("Rang #RRGGBB ko'rinishida bo'lsin, masalan #166534")
        return value.upper()


@panel_required('org.settings')
def org_settings(request):
    """Tashkilot nomi va brend rangi. Faqat o'z tashkilotini o'zgartira oladi; modullarni yoqish — faqat egasi."""
    org = current_org(request)
    owner = is_owner(request.user)
    form = OrgForm(request.POST or None, instance=org, owner=owner)
    if request.method == 'POST' and form.is_valid():
        changed = form.changed_data
        form.save()
        audit.log(request, "Tashkilot sozlamasini o'zgartirdi", org, label=org.name, details={"o'zgargan maydonlar": changed}, target_type='organization')
        messages.success(request, 'Saqlandi. Ilova rangi yangilandi.')
        return redirect(f"{reverse('panel:org_settings')}?org={org.pk}")
    return render(request, 'panel/org_settings.html', {'nav': 'org', 'form': form, 'org': org, 'orgs': list(orgs_for(request.user)),
                                                       })
