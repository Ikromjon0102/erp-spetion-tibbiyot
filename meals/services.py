"""Taomnoma xizmatlari: sana bo'yicha menyu, taomlarni nomi bo'yicha topish/yaratish, rasmni kichraytirib saqlash."""
from io import BytesIO

from django.core.files.base import ContentFile

from .models import Dish, MealPlan, MealType, MenuDish, MenuEntry

DEFAULT_TYPES = ['Tushlik', 'Ikkinchi tushlik (poldnik)']
MAX_SIDE = 1000


def get_plan(org, create=True):
    """Tashkilotning taomnoma sozlamasi; yo'q bo'lsa standart (14 kun, Du–Sha, Tushlik va Poldnik) bilan yaratiladi."""
    plan = MealPlan.objects.filter(organization=org).first()
    if plan is None and create:
        plan = MealPlan.objects.create(organization=org)
    if create and not MealType.objects.filter(organization=org).exists():
        for i, name in enumerate(DEFAULT_TYPES, 1):
            MealType.objects.create(organization=org, name=name, order=i)
    return plan


def menu_for_date(org, d):
    """Berilgan sana uchun menyu:
    {'served': bool, 'cycle_day': int|None, 'meals': [{'type': MealType, 'served': bool, 'dishes': [Dish]}]}.
    Tashkilotda taomnoma yoqilmagan, sozlanmagan yoki o'sha kuni ovqat berilmasa — served=False."""
    empty = {'served': False, 'cycle_day': None, 'meals': []}
    if not org.meals_enabled:
        return empty
    plan = get_plan(org, create=False)
    if plan is None:
        return empty
    day = plan.cycle_day(d)
    if day is None:
        return empty
    entries = {e.meal_type_id: e for e in MenuEntry.objects.filter(organization=org, cycle_day=day).prefetch_related('items__dish')}
    meals = []
    for mt in MealType.objects.filter(organization=org, is_active=True):
        entry = entries.get(mt.pk)
        if entry is None or entry.not_served:
            meals.append({'type': mt, 'served': False, 'dishes': []})
            continue
        dishes = [i.dish for i in sorted(entry.items.all(), key=lambda i: (i.order, i.id))]
        meals.append({'type': mt, 'served': bool(dishes), 'dishes': dishes})
    return {'served': any(m['served'] for m in meals), 'cycle_day': day, 'meals': meals}


def split_dishes(text):
    """«Osh, salat, non» yoki har qatorda bittadan -> ['Osh', 'salat', 'non'] (bo'sh va takrorlar tashlanadi)."""
    out, seen = [], set()
    for raw in text.replace('\r', '\n').replace(';', ',').replace('\n', ',').split(','):
        name = ' '.join(raw.split())
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name[:120])
    return out


def find_or_create_dish(name):
    """Taomni nomi bo'yicha (katta-kichik harfga qaramay) topadi, yo'q bo'lsa yaratadi. Bir xil taom (non, choy) bitta rasmni ulashadi."""
    dish = Dish.objects.filter(name__iexact=name).first()
    return dish or Dish.objects.create(name=name[:1].upper() + name[1:])


def set_entry(org, cycle_day, meal_type, names, not_served=False):
    """Sikldagi bir kun va ovqat turi uchun taomlarni qayta yozadi."""
    entry, _ = MenuEntry.objects.get_or_create(organization=org, cycle_day=cycle_day, meal_type=meal_type)
    entry.not_served = not_served
    entry.save(update_fields=['not_served'])
    entry.items.all().delete()
    if not not_served:
        for i, name in enumerate(names):
            MenuDish.objects.create(entry=entry, dish=find_or_create_dish(name), order=i)
    return entry


def save_dish_photo(dish, upload):
    """Rasmni 1000 px gacha kichraytirib JPEG qilib saqlaydi (telefon rasmlari katta, diskni to'ldirmasin). Xato bo'lsa ValueError."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        img = ImageOps.exif_transpose(Image.open(upload)).convert('RGB')
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise ValueError("Rasm fayli emas yoki buzilgan")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = BytesIO()
    img.save(buf, 'JPEG', quality=82, optimize=True)
    if dish.photo:
        dish.photo.delete(save=False)
    dish.photo.save(f'{dish.pk}.jpg', ContentFile(buf.getvalue()), save=True)
    return dish
