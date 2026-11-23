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
            out.append({'id': o.pk, 'label': o.label, 'color': o.brand_color, 'center': o.kind == CENTER, 'kind': o.kind})
    return out


def meals_today(branches, today=None):
    """Bugungi taomnoma (taomnoma yoqilgan tashkilotlar uchun): [{org, color, meals: [{type, time, dishes: [{name, photo}]}]}]."""
    from meals.services import menu_for_date
    today = today or timezone.localdate()
    out, seen = [], set()
    for b in branches:
        org = b.organization
        if org.pk in seen or not org.meals_enabled:
            continue
        seen.add(org.pk)
        menu = menu_for_date(org, today)
        if not menu['served']:
            continue
        out.append({'org': org.label, 'color': org.brand_color, 'meals': [
            {'type': m['type'].name, 'time': f"{m['type'].start_time():%H:%M}",
             'dishes': [{'name': d.name, 'photo': reverse('dish_photo', args=[d.pk]) if d.photo else ''} for d in m['dishes']]}
            for m in menu['meals'] if m['served']]})
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
