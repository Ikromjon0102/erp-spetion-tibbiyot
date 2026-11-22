from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.passwords import issue_temp_password
from accounts.phone import to_digits
from accounts.student_import import _unique_username

from org.scope import branch_ids, branches_for, pick_branch, scope_staff

from . import audit
from .hubs import org_hub
from .access import is_owner, panel_required, perms_of
from .forms import PositionForm, StaffCreateForm
from .models import AuditLog, Position, StaffProfile
from .perms import ALL_PERMS, CATALOG, LABELS, normalize


def _matrix(selected, allowed, locked=False):
    """Ruxsatlar jadvali uchun ma'lumot. `allowed` — hozirgi foydalanuvchi bera oladigan ruxsatlar."""
    selected = set(selected)
    return [{'key': key, 'name': name, 'actions': [
        {'code': f'{key}.{a}', 'label': label, 'checked': locked or f'{key}.{a}' in selected,
         'enabled': (not locked) and f'{key}.{a}' in allowed}
        for a, label in actions]} for key, name, actions in CATALOG]


def _secret(request, text):
    messages.add_message(request, messages.SUCCESS, text, extra_tags='secret')


def _other_owner_exists(excluding_user_id):
    """Shundan boshqa faol "to'liq ruxsatli" (superuser yoki maktab egasi) bormi — oxirgisini chetlatmaslik uchun."""
    if User.objects.filter(is_superuser=True, is_active=True).exclude(pk=excluding_user_id).exists():
        return True
    return StaffProfile.objects.filter(position__is_owner=True, is_active=True, user__is_active=True).exclude(user_id=excluding_user_id).exists()


def _perm_diff(old, new):
    old, new = set(old), set(new)
    return {'qo\'shildi': [LABELS[p] for p in sorted(new - old)], 'olib tashlandi': [LABELS[p] for p in sorted(old - new)]}


# ------------------------------------------------------------------ xodimlar

@panel_required('staff.view')
@org_hub('staff')
def staff_list(request):
    profiles = list(scope_staff(StaffProfile.objects.select_related('user', 'position'), request.user).order_by('position__order', 'user__last_name'))
    profile_user_ids = {p.user_id for p in profiles}
    technical = [u for u in User.objects.filter(is_superuser=True, is_active=True) if u.pk not in profile_user_ids]
    return render(request, 'panel/staff.html', {'nav': 'staff', 'profiles': profiles, 'technical': technical,
                                                'can_manage': 'staff.manage' in perms_of(request.user)})


@panel_required('staff.manage')
def staff_add(request):
    me = request.user
    form = StaffCreateForm(request.POST or None)
    if not is_owner(me):
        form.fields['position'].queryset = Position.objects.filter(is_owner=False)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        digits = to_digits(d['phone'])
        position = d['position']
        existing = User.objects.filter(phone_digits=digits).order_by('id').first()
        if existing and (existing.is_superuser or StaffProfile.objects.filter(user=existing).exists()):
            form.add_error('phone', 'Bu raqam bilan xodim allaqachon mavjud.')
        else:
            granted = perms_of(me)
            perms = [p for p in normalize(position.default_perms) if p in granted]
            with transaction.atomic():
                created = existing is None
                if created:
                    user = User(username=digits if not User.objects.filter(username=digits).exists() else _unique_username(digits),
                                first_name=d['first_name'], last_name=d['last_name'], phone=d['phone'], role=User.Role.STAFF)
                    user.set_unusable_password()
                    user.save()
                else:
                    user = existing
                profile = StaffProfile.objects.create(user=user, position=position, perms=perms)
                user.branches.add(*(branches_for(me) if branch_ids(me) is not None else [pick_branch(me)]))
            audit.log(request, "Xodim qo'shdi", profile, label=f"{user.get_full_name() or user.username} — {position.name}",
                      details={'lavozim': position.name, 'ruxsatlar': [LABELS[p] for p in perms]}, target_type='staff')
            if created:
                password = issue_temp_password(user)
                _secret(request, f"{user.get_full_name()} qo'shildi. Login: {d['phone']} · bir martalik parol: {password}  "
                                 "(faqat hozir ko'rinadi; birinchi kirishda yangi parol qo'yadi)")
            else:
                messages.success(request, f"{user.get_full_name() or user.username} ({user.get_role_display()}) mavjud hisobga panel ruxsati berildi. "
                                          "Parol o'zgarmadi.")
            return redirect('panel:staff_detail', pk=profile.pk)
    return render(request, 'panel/staff_add.html', {'nav': 'staff', 'form': form})


@panel_required('staff.view')
def staff_detail(request, pk):
    me, granted = request.user, perms_of(request.user)
    profile = get_object_or_404(scope_staff(StaffProfile.objects.select_related('user', 'position'), me), pk=pk)
    is_self = profile.user_id == me.id
    editable = 'staff.manage' in granted and not is_self and (is_owner(me) or not profile.is_owner)
    positions = Position.objects.all() if is_owner(me) else Position.objects.filter(is_owner=False)

    if request.method == 'POST':
        if not editable:
            messages.error(request, "Bu xodimning ruxsatlarini o'zgartirishga huquqingiz yo'q.")
            return redirect('panel:staff_detail', pk=profile.pk)
        position = get_object_or_404(Position, pk=request.POST.get('position'))
        if position.is_owner and not is_owner(me):
            messages.error(request, "'Maktab egasi' lavozimini faqat egasi bera oladi.")
            return redirect('panel:staff_detail', pk=profile.pk)
        perms = normalize(position.default_perms if 'apply_preset' in request.POST else request.POST.getlist('perms'))
        if not is_owner(me):
            perms = [p for p in perms if p in granted]      # o'zida yo'q ruxsatni boshqaga bera olmaydi
        active = 'is_active' in request.POST
        if profile.is_owner and (not position.is_owner or not active) and not _other_owner_exists(profile.user_id):
            messages.error(request, "Bu oxirgi 'to'liq ruxsatli' xodim — uni chetlatib bo'lmaydi.")
            return redirect('panel:staff_detail', pk=profile.pk)
        before_perms, before_pos, before_active = list(profile.perms), profile.position.name, profile.is_active
        with transaction.atomic():
            profile.position, profile.perms, profile.is_active = position, perms, active
            profile.save()
            if profile.user.role == User.Role.STAFF and profile.user.is_active != active:
                profile.user.is_active = active
                profile.user.save(update_fields=['is_active'])
        details = _perm_diff(before_perms, perms)
        if before_pos != position.name:
            details['lavozim'] = audit.change(before_pos, position.name)
        if before_active != active:
            details['holat'] = audit.change('faol' if before_active else 'nofaol', 'faol' if active else 'nofaol')
        audit.log(request, "Xodim ruxsatlarini o'zgartirdi", profile, label=profile.user.get_full_name() or profile.user.username,
                  details={k: v for k, v in details.items() if v}, target_type='staff')
        messages.success(request, 'Saqlandi.')
        return redirect('panel:staff_detail', pk=profile.pk)

    allowed = set(granted) if not is_owner(me) else None
    matrix = _matrix(profile.perms, allowed if allowed is not None else set(ALL_PERMS), locked=profile.is_owner)
    return render(request, 'panel/staff_detail.html', {
        'nav': 'staff', 'p': profile, 'editable': editable, 'is_self': is_self, 'positions': positions, 'matrix': matrix,
        'recent': AuditLog.objects.filter(target_type='staff', target_id=profile.pk)[:10],
    })


@panel_required('staff.manage')
@require_POST
def staff_password(request, pk):
    me = request.user
    profile = get_object_or_404(StaffProfile.objects.select_related('user'), pk=pk)
    if profile.user_id == me.id or (profile.is_owner and not is_owner(me)):
        messages.error(request, "Bu xodimning parolini bu yerdan o'zgartirib bo'lmaydi (o'zingiznikini 'Parolni o'zgartirish' orqali).")
    else:
        password = issue_temp_password(profile.user)
        audit.log(request, 'Bir martalik parol berdi', profile, label=profile.user.get_full_name() or profile.user.username, target_type='staff')
        _secret(request, f"{profile.user.get_full_name()} — login: {profile.user.phone or profile.user.username} · bir martalik parol: {password}  "
                         "(faqat hozir ko'rinadi)")
    return redirect('panel:staff_detail', pk=profile.pk)


@panel_required('staff.manage')
@require_POST
def staff_remove(request, pk):
    me = request.user
    profile = get_object_or_404(StaffProfile.objects.select_related('user', 'position'), pk=pk)
    if profile.user_id == me.id or (profile.is_owner and not is_owner(me)):
        messages.error(request, "Bu xodimdan panel ruxsatini olib bo'lmaydi.")
    elif profile.is_owner and not _other_owner_exists(profile.user_id):
        messages.error(request, "Bu oxirgi 'to'liq ruxsatli' xodim — uni olib tashlab bo'lmaydi.")
    else:
        user, label = profile.user, f"{profile.user.get_full_name() or profile.user.username} — {profile.position.name}"
        with transaction.atomic():
            profile.delete()
            if user.role == User.Role.STAFF:       # faqat panel uchun ochilgan hisob: kirishni ham yopamiz
                user.is_active = False
                user.save(update_fields=['is_active'])
        audit.log(request, "Xodimdan panel ruxsatini oldi", label=label, target_type='staff')
        messages.success(request, 'Xodim paneldan olib tashlandi.')
        return redirect('panel:staff')
    return redirect('panel:staff_detail', pk=profile.pk)


# ------------------------------------------------------------------ lavozimlar

@panel_required('staff.view')
def positions(request):
    rows = Position.objects.annotate(n=Count('staff'))
    return render(request, 'panel/positions.html', {'nav': 'positions', 'positions': rows,
                                                    'can_manage': 'staff.manage' in perms_of(request.user), 'labels': LABELS})


@panel_required('staff.manage')
def position_edit(request, pk=None):
    me, granted = request.user, perms_of(request.user)
    position = get_object_or_404(Position, pk=pk) if pk else None
    if position and position.is_owner and not is_owner(me):
        messages.error(request, "'Maktab egasi' lavozimini faqat egasi o'zgartira oladi.")
        return redirect('panel:positions')
    form = PositionForm(request.POST or None, initial={'name': position.name, 'is_owner': position.is_owner} if position else None)
    if not is_owner(me):
        form.fields['is_owner'].disabled = True
    allowed = set(ALL_PERMS) if is_owner(me) else set(granted)
    if request.method == 'POST' and form.is_valid():
        name = form.cleaned_data['name'].strip()
        if Position.objects.filter(name__iexact=name).exclude(pk=position.pk if position else None).exists():
            form.add_error('name', 'Bunday lavozim bor.')
        else:
            perms = [p for p in normalize(request.POST.getlist('perms')) if p in allowed]
            flag = form.cleaned_data['is_owner'] if is_owner(me) else (position.is_owner if position else False)
            owner_left = Position.objects.filter(is_owner=True).exclude(pk=position.pk if position else None).exists()
            if position and position.is_owner and not flag and not owner_left and not User.objects.filter(is_superuser=True, is_active=True).exists():
                form.add_error('is_owner', "Hech bo'lmasa bitta 'to'liq ruxsatli' lavozim qolishi kerak.")
            else:
                before = list(position.default_perms) if position else []
                if position is None:
                    position = Position(order=(Position.objects.count() + 1))
                position.name, position.is_owner, position.default_perms = name, flag, perms
                position.save()
                audit.log(request, "Lavozimni o'zgartirdi" if pk else "Lavozim qo'shdi", position, label=position.name,
                          details={k: v for k, v in _perm_diff(before, perms).items() if v}, target_type='position')
                messages.success(request, 'Saqlandi. Bu lavozim faqat yangi xodimlar uchun namuna; mavjud xodimlarning ruxsatlari o\'zgarmaydi.')
                return redirect('panel:positions')
    return render(request, 'panel/position_form.html', {
        'nav': 'positions', 'form': form, 'position': position, 'matrix': _matrix(position.default_perms if position else [], allowed),
        'title': position.name if position else 'Yangi lavozim'})


@panel_required('staff.manage')
@require_POST
def position_delete(request, pk):
    position = get_object_or_404(Position, pk=pk)
    if position.is_owner or position.staff.exists():
        messages.error(request, "Bu lavozimni o'chirib bo'lmaydi (unda xodimlar bor yoki u 'to'liq ruxsatli').")
    else:
        label = position.name
        position.delete()
        audit.log(request, "Lavozimni o'chirdi", label=label, target_type='position')
        messages.success(request, "Lavozim o'chirildi.")
    return redirect('panel:positions')
