from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render

from accounts.models import Student
from panel.access import can

from .models import Payment


def receipt(request, pk, pay):
    """To'lov cheki: o'quvchining ota-onasi, maktab ma'muriyati yoki to'lovlarni ko'rish ruxsati bor xodim ko'ra oladi."""
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    student = get_object_or_404(Student.objects.select_related('user', 'group'), pk=pk)
    user = request.user
    allowed = (student.parents.filter(pk=user.pk).exists() or user.is_school_admin or can(user, 'payments.view'))
    if not allowed:
        raise PermissionDenied
    p = get_object_or_404(Payment.objects.select_related('received_by'), pk=pay, student=student)
    back = request.META.get('HTTP_REFERER') or '/'
    return render(request, 'billing/receipt.html', {'p': p, 'student': student, 'back': back})
