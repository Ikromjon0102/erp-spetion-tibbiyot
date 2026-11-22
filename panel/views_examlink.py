"""Exam platformasi bilan o'quvchilarni bog'lash: tizim sinf+ism bo'yicha juftlarni taklif qiladi, xodim tasdiqlaydi."""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Student
from billing.reports import real_students
from examlink import client, matching
from examlink.models import ExamLink

from . import audit
from .access import panel_required


@panel_required('org.settings')
def examlink(request):
    ctx = {'nav': 'examlink', 'enabled': client.enabled(), 'error': ''}
    students = real_students(request.user).select_related('user', 'group', 'exam_link')
    linked = [s for s in students if hasattr(s, 'exam_link')]
    ctx['linked'] = linked
    todo = [s for s in students if not hasattr(s, 'exam_link')]
    ctx['proposals'], ctx['unmatched'] = [], todo
    if ctx['enabled']:
        try:
            exam = client.fetch_students()
        except client.ExamUnavailable as e:
            ctx['error'] = str(e)
        else:
            taken = set(ExamLink.objects.values_list('exam_student_id', flat=True))
            free = [x for x in exam if x['is_active'] and x['id'] not in taken]
            by_id = {s.pk: s for s in todo}
            pairs = matching.propose([(s.pk, s.user.get_full_name() or s.user.username, s.group.name if s.group else '') for s in todo], free)
            ctx['proposals'] = [{**p, 'student': by_id[p['erp']]} for p in pairs]
            matched = {p['erp'] for p in pairs}
            ctx['unmatched'] = [s for s in todo if s.pk not in matched]
            ctx['exam_total'] = len(exam)
    return render(request, 'panel/examlink.html', ctx)


@panel_required('org.settings')
@require_POST
def examlink_confirm(request):
    """Belgilangan juftlarni saqlaydi. Qiymat: `<erp_id>:<exam_id>`; faqat o'zi ko'ra oladigan o'quvchilar uchun."""
    try:
        exam = {x['id']: x for x in client.fetch_students()}
    except client.ExamUnavailable as e:
        messages.error(request, f"Exam bilan aloqa yo'q: {e}")
        return redirect('panel:examlink')
    allowed = {s.pk: s for s in real_students(request.user)}
    done = 0
    for raw in request.POST.getlist('pair'):
        try:
            sid, xid = (int(v) for v in raw.split(':'))
        except ValueError:
            continue
        s, x = allowed.get(sid), exam.get(xid)
        if s is None or x is None or ExamLink.objects.filter(student=s).exists() or ExamLink.objects.filter(exam_student_id=xid).exists():
            continue
        ExamLink.objects.create(student=s, exam_student_id=xid, exam_name=x['full_name'], exam_class=x['class_name'], linked_by=request.user)
        audit.log(request, 'exam.link', s, label=f"{s.user.get_full_name()} ↔ {x['full_name']}")
        done += 1
    messages.success(request, f'{done} ta o\'quvchi exam bilan bog\'landi')
    return redirect('panel:examlink')


@panel_required('org.settings')
@require_POST
def examlink_unlink(request, pk):
    link = ExamLink.objects.filter(pk=pk, student__in=real_students(request.user)).select_related('student__user').first()
    if link:
        audit.log(request, 'exam.unlink', link.student, label=link.student.user.get_full_name())
        link.delete()
        messages.success(request, 'Bog\'lanish o\'chirildi')
    return redirect('panel:examlink')
