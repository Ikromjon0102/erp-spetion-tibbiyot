from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from org import theme
from org.models import Branch, Organization
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


class NewOrgForm(forms.ModelForm):
    first_branch = forms.CharField(label='Birinchi filial nomi', max_length=100, initial='Asosiy',
                                   help_text="Keyin shu sahifada boshqa filiallar qo'shiladi")

    class Meta:
        model = Organization
        fields = ['name', 'short_name', 'kind', 'brand_color', 'meals_enabled']
        labels = {'name': 'Tashkilot nomi', 'short_name': 'Qisqa nomi (ilovada)', 'kind': 'Turi', 'brand_color': 'Brend rangi'}
        widgets = {'brand_color': forms.TextInput(attrs={'type': 'color', 'style': 'width:90px;height:44px;padding:2px'})}

    def clean_brand_color(self):
        value = self.cleaned_data['brand_color'].strip()
        if not theme.is_valid(value):
            raise forms.ValidationError("Rang #RRGGBB ko'rinishida bo'lsin")
        return value.upper()


def _owner_only(request):
    """Tashkilot va filial qo'shish — faqat founder (markaz direktori ham emas)."""
    if not is_owner(request.user):
        raise PermissionDenied("Tashkilot va filial qo'shishni faqat maktab egasi qila oladi.")


def _back(org):
    return redirect(f"{reverse('panel:org_settings')}?org={org.pk}")


@panel_required('org.settings')
def org_add(request):
    _owner_only(request)
    form = NewOrgForm(request.POST or None, initial={'brand_color': '#166534', 'kind': Organization.Kind.CENTER})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            org = form.save()
            Branch.objects.create(organization=org, name=form.cleaned_data['first_branch'].strip() or 'Asosiy')
        audit.log(request, "Tashkilot qo'shdi", org, label=org.name, details={'turi': org.get_kind_display()}, target_type='organization')
        messages.success(request, f"«{org.name}» qo'shildi. Endi filiallar, narx va xodimlarni belgilang.")
        # yangi tashkilot ish maydonida tanlanadi (founder hozir boshqa tashkilotda bo'lishi mumkin)
        nxt = f"{reverse('panel:org_settings')}?org={org.pk}"
        return redirect(f"{reverse('panel:set_scope')}?{urlencode({'s': f'org-{org.pk}', 'next': nxt})}")
    return render(request, 'panel/org_add.html', {'nav': 'org', 'form': form})


@panel_required('org.settings')
@require_POST
def branch_add(request):
    _owner_only(request)
    org = get_object_or_404(Organization, pk=request.POST.get('org'))
    name = ' '.join(request.POST.get('name', '').split())[:100]
    if not name:
        messages.error(request, 'Filial nomini kiriting')
    elif Branch.objects.filter(organization=org, name__iexact=name).exists():
        messages.error(request, f"«{name}» nomli filial bu tashkilotda allaqachon bor")
    else:
        br = Branch.objects.create(organization=org, name=name, address=request.POST.get('address', '').strip()[:200],
                                   phone=request.POST.get('phone', '').strip()[:30],
                                   order=(org.branches.order_by('-order').values_list('order', flat=True).first() or 0) + 1)
        audit.log(request, "Filial qo'shdi", br, label=str(br), target_type='branch')
        messages.success(request, f"«{name}» filiali qo'shildi. Xodim va ustozlarni unga «Ish filiallari» orqali biriktiring.")
    return _back(org)


@panel_required('org.settings')
@require_POST
def branch_edit(request, pk):
    _owner_only(request)
    br = get_object_or_404(Branch.objects.select_related('organization'), pk=pk)
    name = ' '.join(request.POST.get('name', '').split())[:100]
    if not name:
        messages.error(request, 'Filial nomini kiriting')
    elif Branch.objects.filter(organization=br.organization, name__iexact=name).exclude(pk=br.pk).exists():
        messages.error(request, f"«{name}» nomli filial bu tashkilotda allaqachon bor")
    else:
        before = br.name
        br.name, br.address, br.phone = name, request.POST.get('address', '').strip()[:200], request.POST.get('phone', '').strip()[:30]
        br.save(update_fields=['name', 'address', 'phone'])
        audit.log(request, "Filialni o'zgartirdi", br, label=str(br), details={'nom': audit.change(before, name)} if before != name else {},
                  target_type='branch')
        messages.success(request, 'Saqlandi')
    return _back(br.organization)


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
                                                       'owner': owner, 'branches': list(org.branches.order_by('order', 'name')) if owner else []})
