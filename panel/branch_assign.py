"""Ustoz va xodimning ish filiallarini panelda belgilash.

Qoida: tahrirlovchi faqat O'ZI ruxsat olgan filiallarni qo'sha/olib tashlay oladi; boshqa filiallar (masalan direktor ko'rmaydigan markaz filiali)
o'zgarishsiz qoladi. Kamida bitta filial bo'lishi shart. Tanlangan ish maydoni (`Ish maydoni`) bu yerda hisobga olinmaydi —
tahrirlovchining asl ruxsati ishlatiladi.
"""
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from org.models import Branch
from org.scope import _base_branch_ids

from . import audit
from .access import is_owner, panel_required


def editable_branches(editor):
    """Tahrirlovchi tanlay oladigan filiallar (tashkilot, nom bo'yicha)."""
    base = _base_branch_ids(editor)
    qs = Branch.objects.filter(is_active=True).select_related('organization').order_by('organization__name', 'name')
    return list(qs if base is None else qs.filter(pk__in=base))


def branch_choices(editor, target):
    """Shablon uchun: [{'org': Organization, 'items': [{'branch', 'on'}]}]."""
    current = set(target.branches.values_list('pk', flat=True))
    groups, seen = [], {}
    for b in editable_branches(editor):
        if b.organization_id not in seen:
            seen[b.organization_id] = {'org': b.organization, 'items': []}
            groups.append(seen[b.organization_id])
        seen[b.organization_id]['items'].append({'branch': b, 'on': b.pk in current})
    return groups


def apply_branches(request, target, label, target_type):
    """POST dagi `branch` ro'yxatini qo'llaydi. True — saqlandi."""
    allowed = {b.pk for b in editable_branches(request.user)}
    try:
        chosen = {int(x) for x in request.POST.getlist('branch')} & allowed
    except ValueError:
        chosen = set()
    current = set(target.branches.values_list('pk', flat=True))
    new = chosen | (current - allowed)          # ruxsatsiz filiallar tegilmaydi
    if not new:
        messages.error(request, "Kamida bitta filial tanlang.")
        return False
    if new == current:
        messages.info(request, "O'zgarish yo'q.")
        return True
    names = {b.pk: str(b) for b in Branch.objects.filter(pk__in=current | new).select_related('organization')}
    with transaction.atomic():
        target.branches.set(new)
    audit.log(request, "Filiallarini o'zgartirdi", target, label=label, target_type=target_type,
              details={'filiallar': audit.change(', '.join(sorted(names[i] for i in current)), ', '.join(sorted(names[i] for i in new)))})
    messages.success(request, 'Filiallar saqlandi.')
    return True


@panel_required('teachers.change')
@require_POST
def teacher_branches(request, pk):
    from .views_teachers import teachers_qs
    user = get_object_or_404(teachers_qs(request.user), pk=pk)
    apply_branches(request, user, user.get_full_name() or user.username, 'teacher')
    return redirect('panel:teacher', pk=user.pk)


@panel_required('staff.manage')
@require_POST
def staff_branches(request, pk):
    from org.scope import scope_staff
    from .models import StaffProfile
    profile = get_object_or_404(scope_staff(StaffProfile.objects.select_related('user', 'position'), request.user), pk=pk)
    me = request.user
    if profile.user_id == me.id or (profile.is_owner and not is_owner(me)):
        messages.error(request, "Bu xodimning filiallarini o'zgartirishga huquqingiz yo'q.")
    else:
        apply_branches(request, profile.user, profile.user.get_full_name() or profile.user.username, 'staff')
    return redirect('panel:staff_detail', pk=profile.pk)
