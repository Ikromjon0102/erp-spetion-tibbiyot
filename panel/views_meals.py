"""Taomnoma boshqaruvi (panel). Oshpaz platformaga kirmaydi: menyuni va taomlar rasmini xodim (zavxoz, hisobchi, direktor...)
bir marta kiritadi, ruxsat `meals.*` — founder kerakli odamga beradi. Rasm bir marta yuklanadi va har siklda qayta ishlatiladi."""
import re
from datetime import date, time

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from meals import services
from meals.models import WEEKDAYS, Dish, MealType, MenuEntry, NoMealDay
from org.scope import current_org, orgs_for

from . import audit
from .access import panel_required, perms_of


def _back(org, name='panel:meals'):
    return redirect(f"{reverse(name)}?org={org.pk}")


def _norm(text):
    """Fayl/taom nomini solishtirish uchun: kichik harf, _ - . bo'shliqqa, ortiqcha bo'shliqlarsiz."""
    return ' '.join(re.sub(r"[_\-.]+", ' ', text.lower()).split())


@panel_required('meals.view')
def meals(request):
    granted = perms_of(request.user)
    org = current_org(request)
    ctx = {'nav': 'meals', 'org': org, 'orgs': list(orgs_for(request.user)), 'can_manage': 'meals.manage' in granted}
    if not org.meals_enabled:
        return render(request, 'panel/meals.html', ctx)
    plan = services.get_plan(org)
    types = list(MealType.objects.filter(organization=org, is_active=True))
    entries = {(e.cycle_day, e.meal_type_id): e for e in MenuEntry.objects.filter(organization=org).prefetch_related('items__dish')}
    rows = []
    for day in range(1, plan.cycle_length + 1):
        cells = []
        for mt in types:
            e = entries.get((day, mt.pk))
            dishes = [i.dish for i in sorted(e.items.all(), key=lambda i: (i.order, i.id))] if e else []
            cells.append({'type': mt, 'dishes': dishes, 'not_served': bool(e and e.not_served), 'empty': e is None or (not dishes and not e.not_served)})
        rows.append({'day': day, 'cells': cells})
    today = timezone.localdate()
    ctx.update({'plan': plan, 'types': types, 'rows': rows, 'today': today, 'today_day': plan.cycle_day(today),
                'no_photo': Dish.objects.filter(photo='').count() + Dish.objects.filter(photo__isnull=True).count()})
    return render(request, 'panel/meals.html', ctx)


@panel_required('meals.manage')
def meals_day(request, day):
    org = current_org(request)
    plan = services.get_plan(org)
    if not org.meals_enabled or not 1 <= day <= plan.cycle_length:
        raise Http404
    types = list(MealType.objects.filter(organization=org, is_active=True))
    entries = {e.meal_type_id: e for e in MenuEntry.objects.filter(organization=org, cycle_day=day).prefetch_related('items__dish')}
    if request.method == 'POST':
        for mt in types:
            names = services.split_dishes(request.POST.get(f'meal_{mt.pk}', ''))
            services.set_entry(org, day, mt, names, not_served=bool(request.POST.get(f'ns_{mt.pk}')))
        audit.log(request, "Menyuni o'zgartirdi", label=f'{org.label} · {day}-kun', target_type='meals')
        messages.success(request, f'{day}-kun menyusi saqlandi')
        return _back(org)
    fields = []
    for mt in types:
        e = entries.get(mt.pk)
        fields.append({'type': mt, 'text': ', '.join(d.name for d in e.ordered_dishes()) if e else '', 'not_served': bool(e and e.not_served)})
    return render(request, 'panel/meals_day.html', {'nav': 'meals', 'org': org, 'day': day, 'fields': fields, 'length': plan.cycle_length,
                                                    'dish_names': list(Dish.objects.values_list('name', flat=True))})


# ------------------------------------------------------------------ taomlar va rasmlar

@panel_required('meals.view')
def dishes(request):
    granted = perms_of(request.user)
    q = request.GET.get('q', '').strip()
    only = request.GET.get('rasm', '')
    qs = Dish.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)
    if only == 'yoq':
        qs = qs.filter(photo='') | qs.filter(photo__isnull=True)
    return render(request, 'panel/dishes.html', {'nav': 'meals', 'dishes': qs.distinct().order_by('name'), 'q': q, 'only': only,
                                                 'total': Dish.objects.count(), 'can_manage': 'meals.manage' in granted,
                                                 'org': current_org(request)})


class DishForm(forms.ModelForm):
    class Meta:
        model = Dish
        fields = ['name']
        labels = {'name': 'Taom nomi'}

    def clean_name(self):
        name = ' '.join(self.cleaned_data['name'].split())
        clash = Dish.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError('Bu nomdagi taom allaqachon bor')
        return name


@panel_required('meals.manage')
def dish_edit(request, pk):
    dish = get_object_or_404(Dish, pk=pk)
    form = DishForm(request.POST or None, instance=dish)
    upload = request.FILES.get('photo')
    if request.method == 'POST' and form.is_valid():
        form.save()
        ok = True
        if request.POST.get('remove_photo') and dish.photo:
            dish.photo.delete(save=True)
        if upload:
            try:
                services.save_dish_photo(dish, upload)
            except ValueError as e:
                form.add_error(None, str(e))
                ok = False
        if ok:
            audit.log(request, "Taomni o'zgartirdi", dish, label=dish.name, target_type='meals')
            messages.success(request, 'Saqlandi')
            return redirect('panel:dishes')
    return render(request, 'panel/dish_form.html', {'nav': 'meals', 'form': form, 'dish': dish})


@require_POST
@panel_required('meals.manage')
def dish_delete(request, pk):
    dish = get_object_or_404(Dish, pk=pk)
    if dish.menu_items.exists():
        messages.error(request, "Bu taom menyuda ishlatilgan: avval menyudan olib tashlang")
    else:
        if dish.photo:
            dish.photo.delete(save=False)
        audit.log(request, "Taomni o'chirdi", label=dish.name, target_type='meals')
        dish.delete()
        messages.success(request, "Taom o'chirildi")
    return redirect('panel:dishes')


@require_POST
@panel_required('meals.manage')
def dishes_bulk(request):
    """Ko'p rasmni bir yo'la yuklash: fayl nomi taom nomiga mos bo'lsin («osh.jpg», «Mol go'shtli osh.png»). Topilmaganlari ro'yxatga chiqadi."""
    by_name = {_norm(d.name): d for d in Dish.objects.all()}
    done, unknown, bad = 0, [], []
    for f in request.FILES.getlist('photos')[:100]:
        stem = f.name.rsplit('.', 1)[0]
        dish = by_name.get(_norm(stem))
        if dish is None:
            unknown.append(stem)
            continue
        try:
            services.save_dish_photo(dish, f)
            done += 1
        except ValueError:
            bad.append(stem)
    if done:
        audit.log(request, "Taom rasmlarini yukladi", label=f'{done} ta', target_type='meals')
        messages.success(request, f'{done} ta taom rasmi saqlandi')
    if unknown:
        messages.warning(request, "Nomi mos taom topilmadi: " + ', '.join(unknown[:12]) + (' …' if len(unknown) > 12 else '')
                         + ". Fayl nomini taom nomiga moslang.")
    if bad:
        messages.error(request, "Rasm emas yoki buzilgan: " + ', '.join(bad[:8]))
    if not request.FILES.getlist('photos'):
        messages.error(request, 'Rasm tanlanmadi')
    return redirect('panel:dishes')


@login_required
def dish_photo(request, pk):
    """Taom rasmi: tizimga kirgan har bir foydalanuvchi (ota-ona, ustoz, xodim) ko'ra oladi. Maxfiy ma'lumot emas."""
    dish = get_object_or_404(Dish, pk=pk)
    if not dish.photo:
        raise Http404
    resp = FileResponse(dish.photo.open('rb'), content_type='image/jpeg')
    resp['Cache-Control'] = 'private, max-age=86400'
    return resp


# ------------------------------------------------------------------ sozlamalar

@panel_required('meals.manage')
def meals_settings(request):
    org = current_org(request)
    if not org.meals_enabled:
        raise Http404
    plan = services.get_plan(org)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'plan':
            days = {int(x) for x in request.POST.getlist('weekdays') if x.isdigit() and 0 <= int(x) <= 6}
            if not days:
                messages.error(request, "Kamida bitta hafta kunini tanlang")
                return _back(org, 'panel:meals_settings')
            if days != plan.days:
                plan.set_weekdays(days)
            try:
                length = int(request.POST.get('cycle_length') or plan.cycle_length)
            except ValueError:
                length = plan.cycle_length
            plan.cycle_length = min(max(length, 1), 31)
            today_day = request.POST.get('today_day', '').strip()
            if today_day.isdigit():
                plan.set_today(int(today_day))
            plan.save()
            audit.log(request, "Taomnoma sozlamasini o'zgartirdi", label=org.label, target_type='meals')
            messages.success(request, 'Saqlandi')
        elif action == 'type_add':
            name = ' '.join(request.POST.get('name', '').split())[:60]
            if name and not MealType.objects.filter(organization=org, name__iexact=name).exists():
                order = (MealType.objects.filter(organization=org).order_by('-order').values_list('order', flat=True).first() or 0) + 1
                MealType.objects.create(organization=org, name=name, order=order)
                messages.success(request, f"«{name}» qo'shildi")
            else:
                messages.error(request, 'Nom kiriting (takrorlanmasin)')
        elif action == 'type_toggle':
            mt = get_object_or_404(MealType, pk=request.POST.get('id'), organization=org)
            mt.is_active = not mt.is_active
            mt.save(update_fields=['is_active'])
        elif action == 'type_time':
            mt = get_object_or_404(MealType, pk=request.POST.get('id'), organization=org)
            raw = request.POST.get('at', '').strip()
            try:
                mt.at = time.fromisoformat(raw) if raw else None
            except ValueError:
                messages.error(request, "Soatni to'g'ri kiriting (masalan 12:30)")
                return _back(org, 'panel:meals_settings')
            mt.save(update_fields=['at'])
            messages.success(request, f"«{mt.name}» vaqti saqlandi")
        elif action == 'holiday_add':
            try:
                start = date.fromisoformat(request.POST.get('start', ''))
                end = date.fromisoformat(request.POST.get('end', '') or request.POST.get('start', ''))
            except ValueError:
                messages.error(request, "Sanani to'g'ri kiriting")
                return _back(org, 'panel:meals_settings')
            if end < start:
                start, end = end, start
            NoMealDay.objects.create(organization=org, start=start, end=end, reason=request.POST.get('reason', '').strip()[:100])
            messages.success(request, "Ovqatsiz kun qo'shildi: shu kunlarda sikl to'xtab turadi")
        elif action == 'holiday_delete':
            NoMealDay.objects.filter(pk=request.POST.get('id'), organization=org).delete()
            messages.success(request, "O'chirildi")
        return _back(org, 'panel:meals_settings')
    today = timezone.localdate()
    return render(request, 'panel/meals_settings.html', {
        'nav': 'meals', 'org': org, 'plan': plan, 'weekdays': [(n, label, n in plan.days) for n, label in WEEKDAYS],
        'types': MealType.objects.filter(organization=org), 'holidays': NoMealDay.objects.filter(organization=org)[:30],
        'today': today, 'today_day': plan.cycle_day(today)})
