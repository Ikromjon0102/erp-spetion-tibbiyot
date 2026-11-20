import zipfile
from io import BytesIO

from django import forms
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from access.hikvision import Client, DeviceError
from access.models import AccessSettings, Device, FaceSync
from access.sync import eligible_users, pending_count, sync_device, sync_in_background
from accounts.face_ids import next_staff_id, next_teacher_id as _next_teacher_id
from accounts.models import Student, User
from accounts.photos import PhotoError, prepare as prepare_photo, remove_photo, save_photo
from billing.reports import real_students

from . import audit
from .access import can, panel_required, perms_of
from .models import StaffProfile

IMAGE_EXT = ('.jpg', '.jpeg', '.png')
ZIP_LIMIT = 60 * 1024 * 1024
ZIP_FILES = 1500


class DeviceForm(forms.ModelForm):
    password = forms.CharField(label='Qurilma paroli', required=False, widget=forms.PasswordInput(render_value=False),
                               help_text="Bo'sh qoldirsangiz, eski parol saqlanadi")

    class Meta:
        model = Device
        fields = ['name', 'direction', 'host', 'port', 'use_https', 'username', 'password', 'is_active']

    def clean_password(self):
        return self.cleaned_data['password'] or (self.instance.password if self.instance.pk else '')


def next_teacher_id():
    """Ustoz uchun Face ID: 7001 dan boshlanadi (o'quvchilar 9001 dan, shuning uchun to'qnashmaydi)."""
    return _next_teacher_id()


def person_user(student_pk=None, teacher_pk=None):
    if student_pk:
        return get_object_or_404(Student.objects.select_related('user'), pk=student_pk).user
    return get_object_or_404(User, pk=teacher_pk, role=User.Role.TEACHER, is_demo=False)


def photo_ok(form, upload):
    """Qo'shish formasidagi ixtiyoriy rasmni oldindan tekshiradi: noto'g'ri bo'lsa forma xatosi qo'shadi (yozuv yaratilmaydi)."""
    if not upload:
        return True
    try:
        prepare_photo(upload)
    except PhotoError as e:
        form.add_error(None, str(e))
        return False
    finally:
        upload.seek(0)
    return True


def apply_photo(request, user, upload, label):
    """Rasmni saqlaydi, kerak bo'lsa ustozga Face ID beradi va qurilmalarga yuborishni boshlaydi."""
    try:
        save_photo(user, upload)
    except PhotoError as e:
        messages.error(request, str(e))
        return False
    if not user.access_id and user.role in (User.Role.TEACHER, User.Role.STAFF):
        user.access_id = next_teacher_id() if user.role == User.Role.TEACHER else next_staff_id()
        user.save(update_fields=['access_id'])
    audit.log(request, 'Yuz rasmini yukladi', user, label=label, target_type='photo')
    sync_in_background(user.pk)
    if user.role == User.Role.STUDENT and not user.device_id:
        messages.warning(request, "Rasm saqlandi, lekin o'quvchida Face ID yo'q — qurilmaga yuborish uchun o'quvchi kartasida Face ID kiriting.")
    else:
        messages.success(request, "Rasm saqlandi. Qurilmalarga avtomatik yuboriladi (natija «Qurilmalar» sahifasida).")
    return True


@require_POST
@panel_required('students.change')
def student_photo(request, pk):
    user = person_user(student_pk=pk)
    upload = request.FILES.get('photo')
    if not upload:
        messages.error(request, 'Rasm tanlanmadi')
    else:
        apply_photo(request, user, upload, user.get_full_name())
    return redirect('panel:student', pk=pk)


@require_POST
@panel_required('students.change')
def student_photo_delete(request, pk):
    user = person_user(student_pk=pk)
    remove_photo(user)
    audit.log(request, "Yuz rasmini o'chirdi", user, label=user.get_full_name(), target_type='photo')
    sync_in_background()
    messages.success(request, "Rasm o'chirildi (qurilmadan ham olib tashlanadi)")
    return redirect('panel:student', pk=pk)


@require_POST
@panel_required('teachers.change')
def teacher_photo(request, pk):
    user = person_user(teacher_pk=pk)
    upload = request.FILES.get('photo')
    if not upload:
        messages.error(request, 'Rasm tanlanmadi')
    else:
        apply_photo(request, user, upload, user.get_full_name())
    return redirect('panel:teacher', pk=pk)


@require_POST
@panel_required('teachers.change')
def teacher_photo_delete(request, pk):
    user = person_user(teacher_pk=pk)
    remove_photo(user)
    audit.log(request, "Yuz rasmini o'chirdi", user, label=user.get_full_name(), target_type='photo')
    sync_in_background()
    messages.success(request, "Rasm o'chirildi (qurilmadan ham olib tashlanadi)")
    return redirect('panel:teacher', pk=pk)


def _staff_user(pk):
    profile = get_object_or_404(StaffProfile.objects.select_related('user'), pk=pk)
    if profile.user.role == User.Role.STUDENT or profile.user.is_demo:
        raise Http404
    return profile.user


@require_POST
@panel_required('staff.manage')
def staff_photo(request, pk):
    user = _staff_user(pk)
    upload = request.FILES.get('photo')
    if not upload:
        messages.error(request, 'Rasm tanlanmadi')
    else:
        apply_photo(request, user, upload, user.get_full_name())
    return redirect('panel:staff_detail', pk=pk)


@require_POST
@panel_required('staff.manage')
def staff_photo_delete(request, pk):
    user = _staff_user(pk)
    remove_photo(user)
    audit.log(request, "Yuz rasmini o'chirdi", user, label=user.get_full_name(), target_type='photo')
    sync_in_background()
    messages.success(request, "Rasm o'chirildi (qurilmadan ham olib tashlanadi)")
    return redirect('panel:staff_detail', pk=pk)


@panel_required('devices.view')
def devices(request):
    granted = perms_of(request.user)
    people = eligible_users()
    rows = []
    for d in Device.objects.all():
        rows.append({'d': d, 'pending': pending_count(d, people) if d.host else None,
                     'failed': d.face_syncs.filter(ok=False).count()})
    students = real_students()
    stats = {'students': students.count(), 'students_photo': students.exclude(user__photo='').exclude(user__photo__isnull=True).count(),
             'teachers': User.objects.filter(role=User.Role.TEACHER, is_demo=False).count(),
             'teachers_photo': User.objects.filter(role=User.Role.TEACHER, is_demo=False).exclude(photo='').exclude(photo__isnull=True).count(),
             'ready': len(people)}
    errors = list(FaceSync.objects.filter(ok=False).select_related('user', 'device').order_by('-updated_at')[:15])
    return render(request, 'panel/devices.html', {'nav': 'devices', 'rows': rows, 'stats': stats, 'errors': errors, 'manage': 'devices.manage' in granted,
                                                  'leave_from': AccessSettings.get().leave_notify_from})


@require_POST
@panel_required('devices.manage')
def access_settings(request):
    from datetime import datetime
    try:
        value = datetime.strptime(request.POST.get('leave_from', '').strip(), '%H:%M').time()
    except ValueError:
        messages.error(request, "Vaqtni SS:DD ko'rinishida kiriting (masalan 16:00)")
        return redirect('panel:devices')
    obj = AccessSettings.get()
    old = obj.leave_notify_from
    obj.leave_notify_from = value
    obj.save()
    audit.log(request, "Chiqish xabari vaqtini o'zgartirdi", label='Kirish-chiqish sozlamasi', target_type='settings',
              details={'vaqt': audit.change(old.strftime('%H:%M'), value.strftime('%H:%M'))})
    messages.success(request, f"Chiqish xabarlari {value:%H:%M} dan boshlab yuboriladi")
    return redirect('panel:devices')


@panel_required('devices.manage')
def device_edit(request, pk=None):
    obj = get_object_or_404(Device, pk=pk) if pk else None
    form = DeviceForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        d = form.save()
        audit.log(request, "Qurilmani sozladi" if obj else "Qurilma qo'shdi", d, label=str(d), details={'manzil': d.host or '—'}, target_type='device')
        messages.success(request, 'Saqlandi')
        return redirect('panel:devices')
    return render(request, 'panel/device_form.html', {'nav': 'devices', 'form': form, 'obj': obj, 'title': 'Qurilmani sozlash' if obj else "Qurilma qo'shish"})


@require_POST
@panel_required('devices.manage')
def device_test(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not device.host:
        messages.error(request, 'Avval qurilma manzilini kiriting')
    else:
        try:
            Client(device).info()
            messages.success(request, f'{device.name}: ulanish muvaffaqiyatli')
        except DeviceError as e:
            messages.error(request, f'{device.name}: {e}')
    return redirect('panel:devices')


@require_POST
@panel_required('devices.manage')
def device_sync(request, pk=None):
    if pk:
        device = get_object_or_404(Device, pk=pk)
        result = sync_device(device)
        if result['error']:
            messages.error(request, f"{device.name}: {result['error']}")
        else:
            messages.success(request, f"{device.name}: yuborildi {result['sent']}, o'zgarmagan {result['skipped']}, o'chirildi {result['removed']}, xato {result['failed']}")
    else:
        sync_in_background()
        messages.success(request, "Sync fonda boshlandi. Natijani shu sahifada ko'rasiz (yangilab turing).")
    audit.log(request, 'Rasmlarni sync qildi', label=str(pk or 'hamma qurilma'), target_type='device')
    return redirect('panel:devices')


@require_POST
@panel_required('devices.manage')
def faces_zip(request):
    """ZIP: fayl nomi = Face ID (masalan 1001.jpg yoki 7001.png). O'quvchi yoki ustoz Face ID si bo'yicha topiladi."""
    upload = request.FILES.get('zip')
    if not upload or upload.size > ZIP_LIMIT:
        messages.error(request, "ZIP faylni tanlang (60 MB gacha)")
        return redirect('panel:devices')
    try:
        zf = zipfile.ZipFile(upload)
        names = [n for n in zf.namelist() if not n.endswith('/') and '__MACOSX' not in n and n.lower().endswith(IMAGE_EXT)]
    except zipfile.BadZipFile:
        messages.error(request, "Bu ZIP fayl emas yoki buzilgan")
        return redirect('panel:devices')
    if len(names) > ZIP_FILES:
        messages.error(request, f"Faylda juda ko'p rasm ({len(names)}); {ZIP_FILES} tagacha")
        return redirect('panel:devices')
    done, unknown, bad = 0, [], []
    for name in names:
        face_id = name.rsplit('/', 1)[-1].rsplit('.', 1)[0].strip()
        student = Student.objects.filter(access_id=face_id).select_related('user').first()
        user = student.user if student else User.objects.filter(access_id=face_id, role=User.Role.TEACHER).first()
        if not user:
            unknown.append(face_id)
            continue
        try:
            save_photo(user, BytesIO(zf.read(name)))
            done += 1
        except PhotoError as e:
            bad.append(f'{face_id} ({e})')
    audit.log(request, "Rasmlarni ZIP bilan yukladi", label=f'{done} ta', details={'saqlandi': done, 'Face ID topilmadi': len(unknown), 'xato': len(bad)}, target_type='photo')
    if done:
        sync_in_background()
        messages.success(request, f"{done} ta rasm saqlandi, qurilmalarga yuboriladi.")
    if unknown:
        messages.warning(request, f"Face ID topilmadi ({len(unknown)} ta): " + ', '.join(unknown[:15]) + (' …' if len(unknown) > 15 else ''))
    if bad:
        messages.error(request, "Rasm xato: " + '; '.join(bad[:8]))
    if not names:
        messages.error(request, "ZIP ichida rasm (jpg/png) topilmadi")
    return redirect('panel:devices')
