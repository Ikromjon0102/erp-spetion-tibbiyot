from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from journal.models import Homework, HomeworkRead
from notices.views import announcements_for, with_read_flags

from .child_data import child_context, overview
from .models import Student
from .permissions import can_view_student
from .phone import normalize_login


MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 10 * 60


class ThrottledLoginView(LoginView):
    """Parollar qisqa (4 raqam) bo'lgani uchun: bir login + bir IP dan 5 ta xato urinishdan keyin 10 daqiqa blok."""
    template_name = 'registration/login.html'

    def _key(self):
        # Telefon har xil formatda yozilsa ham (+998 95..., 95-010..., 950107639) hisoblagich bitta bo'lsin
        username = normalize_login(self.request.POST.get('username')).lower()
        return f"login-fail:{username}:{self.request.META.get('REMOTE_ADDR', '')}"

    def post(self, request, *args, **kwargs):
        if cache.get(self._key(), 0) >= MAX_FAILED_LOGINS:
            self.blocked = True
            return self.form_invalid(self.get_form())
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        cache.delete(self._key())
        return super().form_valid(form)

    def form_invalid(self, form):
        if not getattr(self, 'blocked', False):
            key = self._key()
            cache.set(key, cache.get(key, 0) + 1, LOCKOUT_SECONDS)
        return super().form_invalid(form)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Telefon klaviaturasi loginni bosh harf bilan boshlab yubormasligi uchun
        form.fields['username'].widget.attrs.update(autocapitalize='none', autocorrect='off', spellcheck='false')
        return form

    def get_context_data(self, **kwargs):
        return super().get_context_data(blocked=getattr(self, 'blocked', False), **kwargs)


class NewPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('new_password1', 'new_password2'):
            self.fields[name].widget.attrs.update(autocomplete='new-password')  # brauzer yangi parolni saqlashni taklif qiladi
        self.fields['new_password1'].help_text = 'Kamida 6 ta belgi. Juda oddiy parollar (123456 kabi) qabul qilinmaydi.'

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('new_password1')
        if password and self.user.check_password(password):
            self.add_error('new_password2', 'Yangi parol hozirgisidan (bir martalik paroldan) farq qilishi kerak.')
        return cleaned


@login_required
def change_password(request):
    """Birinchi kirishda (bir martalik parol bilan) yangi parol qo'yish; keyin istalgan vaqtda parolni almashtirish."""
    forced = request.user.must_change_password
    form = NewPasswordForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False)
        user.must_change_password = False
        user.save()
        update_session_auth_hash(request, user)  # tizimdan chiqib ketmasin
        messages.success(request, "Parol o'zgartirildi. Endi shu parol bilan kirasiz.")
        return redirect('home')
    return render(request, 'registration/change_password.html', {'form': form, 'forced': forced})


@login_required
def home(request):
    """Kirgandan keyingi yo'naltirish. Bir nechta imkoniyati bor hisob (ustoz / ota-ona / boshqaruv paneli) oxirgi
    tanlangan rejimda ochiladi; menyudan ikkinchisiga bir bosishda o'tadi."""
    from panel.access import has_panel
    u = request.user
    if request.GET.get('rejim') == 'ota-ona':  # menyudagi "Farzandlarim"
        request.session['mode'] = 'parent'
    children = list(u.children.filter(user__is_active=True).select_related('user', 'group', 'branch__organization'))
    panel = has_panel(u)
    mode = request.session.get('mode')
    if panel and (mode == 'panel' or not (u.is_teacher or children)):
        return redirect('panel:dashboard')
    if u.is_school_admin:
        return redirect('admin:index')
    if u.is_teacher and not (children and mode == 'parent'):
        return redirect('journal:teacher_home')
    if children:
        request.session['mode'] = 'parent'
        if len(children) == 1:  # bitta farzand: to'g'ridan-to'g'ri uning sahifasi
            return redirect('student_detail', pk=children[0].pk)
        request.theme_org = children[0].branch.organization if children[0].branch_id else None
        for c in children:
            c.info = overview(c)
        return render(request, 'app/parent_home.html', {'children': children, 'news': with_read_flags(u, announcements_for(u)[:3])})
    if u.is_parent:
        return render(request, 'app/parent_home.html', {'children': [], 'news': with_read_flags(u, announcements_for(u)[:3])})
    if u.role == u.Role.STAFF:
        raise PermissionDenied("Sizga hozircha boshqaruv paneliga kirish ruxsati berilmagan.")
    student = getattr(u, 'student', None)
    if student is None:
        raise PermissionDenied("Sizga o'quvchi profili biriktirilmagan.")
    return redirect('student_detail', pk=student.pk)


@login_required
def student_detail(request, pk):
    student = get_object_or_404(Student.objects.select_related('user', 'group'), pk=pk)
    if not can_view_student(request.user, student):
        raise PermissionDenied
    if request.user.is_teacher and student.parents.filter(pk=request.user.pk).exists():
        request.session['mode'] = 'parent'  # ustoz o'z farzandini ochdi: keyingi safar ham shu rejimda
    request.theme_org = student.branch.organization if student.branch_id else None   # ilova rangi bolaning tashkiloti rangida
    return render(request, 'app/child.html', child_context(student, request.user))


@login_required
@require_POST
def homework_read(request):
    """Ota-ona (yoki o'quvchi) vazifani ochganda chaqiriladi. Faqat o'z farzandlari/sinfidagi vazifalar belgilanadi."""
    import json
    try:
        ids = [int(i) for i in json.loads(request.body)['ids']][:50]
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'ok': False}, status=400)
    user = request.user
    groups = set(user.children.filter(user__is_active=True).values_list('group_id', flat=True))
    if hasattr(user, 'student'):
        groups.add(user.student.group_id)
    marked = 0
    for hw in Homework.objects.filter(pk__in=ids, teaching__group_id__in=groups):
        _, created = HomeworkRead.objects.get_or_create(homework=hw, user=user)
        marked += created
    return JsonResponse({'ok': True, 'marked': marked})
