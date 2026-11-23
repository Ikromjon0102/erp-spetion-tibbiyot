"""Ustoz sahifasi uchun ma'lumot: faqat ustozning o'z tashkilotlari.

Qoidalar (2026-11-23, founder fikri):
- Ustoz faqat O'Z tashkilotlarini ko'radi (o'z filiallari + dars beradigan guruhlarining filiallari). Boshqa tashkilot darslari yuklanmaydi.
- Maktab va bog'chada «Sinflar» bo'limi — shu filial(lar)ning barcha sinflari jadvali (ustoz sinf jadvalini ko'ra oladi).
- O'quv markazda — faqat ustozning o'z guruhlari (boshqa ustozlarning guruhlari kerak emas).
- Bir nechta tashkilotda ishlasa, darslar tashkilot bo'yicha ajratib ko'rsatiladi.
"""
from datetime import timedelta

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from academics.constants import DAY_CODES
from academics.models import Lesson
from org.models import Branch, default_branch

CENTER = 'center'


def teacher_branches(user):
    """Ustoz ishlaydigan filiallar: belgilangan filiallar + dars beradigan guruhlari filiallari."""
    ids = set(user.branches.values_list('pk', flat=True))
    ids |= set(user.teachings.exclude(group__branch__isnull=True).values_list('group__branch_id', flat=True))
    if not ids:
        ids = {default_branch().pk}
    return list(Branch.objects.filter(pk__in=ids).select_related('organization').order_by('organization__order', 'organization__name', 'order', 'name'))


def lessons_for(user, branches):
    """O'z darslari (hamma joyda) + maktab/bog'cha filiallaridagi barcha sinflar darslari (sinf jadvali uchun)."""
    school_branch_ids = [b.pk for b in branches if b.organization.kind != CENTER]
    cond = Q(teaching__teacher=user)
    if school_branch_ids:
        cond |= Q(teaching__group__branch_id__in=school_branch_ids)
    return (Lesson.objects.filter(cond, active=True)
            .select_related('teaching__subject', 'teaching__group__branch__organization', 'teaching__teacher').distinct())


def orgs_payload(branches):
    seen, out = set(), []
    for b in branches:
        o = b.organization
        if o.pk not in seen:
            seen.add(o.pk)
            out.append({'id': o.pk, 'label': o.label, 'color': o.brand_color, 'center': o.kind == CENTER, 'kind': o.kind, 'meals': o.meals_enabled})
    return out


def display_monday(day):
    """Jadval ko'rsatadigan haftaning dushanbasi (yakshanba kuni — keyingi hafta, sahifadagi kabi)."""
    return day - timedelta(days=day.weekday()) if day.weekday() < 6 else day + timedelta(days=1)


def week_menus(branches, monday):
    """Hafta (Du–Sha) taomnomasi, taomnoma yoqilgan tashkilotlar uchun: {org_id: {'YYYY-MM-DD': [ovqat]}}.
    Ovqat: {key, type, start, end, dishes: [{name, photo}]} — dars jadvalida o'z soatida qisqa qator, bosilsa batafsil."""
    from datetime import datetime
    from meals.services import menu_for_date
    out, seen = {}, set()
    for b in branches:
        org = b.organization
        if org.pk in seen or not org.meals_enabled:
            continue
        seen.add(org.pk)
        per = {}
        for i in range(6):
            d = monday + timedelta(days=i)
            rows = []
            for m in menu_for_date(org, d)['meals']:
                if not m['served']:
                    continue
                start = m['type'].start_time()
                end = (datetime.combine(d, start) + timedelta(minutes=30)).time()
                rows.append({'key': f'{org.pk}-{d.isoformat()}-{m["type"].pk}', 'type': m['type'].name,
                             'start': f'{start:%H:%M}', 'end': f'{end:%H:%M}',
                             'dishes': [{'name': x.name, 'photo': reverse('dish_photo', args=[x.pk]) if x.photo else ''} for x in m['dishes']]})
            if rows:
                per[d.isoformat()] = rows
        out[org.pk] = per
    return out


def org_themes(branches):
    """Har tashkilot uchun sahifa ranglari (CSS o'zgaruvchilari): tashkilot tanlanganda butun sahifa shu rangga o'tadi."""
    from org import theme
    out = {}
    for b in branches:
        o = b.organization
        if o.pk not in out:
            color = o.brand_color if theme.is_valid(o.brand_color) else theme.DEFAULT_COLOR
            out[o.pk] = {'css': str(theme.css(color)), 'accent': color.upper()}
    return out


def lesson_item(l):
    g = l.teaching.group
    org = g.branch.organization if g.branch_id else None
    teacher = l.teaching.teacher
    return {
        'id': l.id, 'day': DAY_CODES[l.weekday], 'period': l.period, 'start': f'{l.start:%H:%M}', 'end': f'{l.end:%H:%M}',
        'class': g.name, 'classKey': f'{g.pk}', 'subject': l.teaching.subject.name,
        'org': org.pk if org else None, 'branch': g.branch.name if g.branch_id else '',
        'teacherId': l.teaching.teacher_id,
        'teacher': (teacher.get_full_name() or teacher.username) if teacher else '',
    }
