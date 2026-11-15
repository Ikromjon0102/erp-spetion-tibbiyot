"""Hikvision Face ID (Employee ID) larni avtomatik berish.

O'quvchilar 9001 dan, ustoz/xodimlar 7001 dan boshlanadi. Raqam har doim diapazondagi eng kattasidan keyingisi bo'ladi
(bo'shab qolgan raqamlar qayta berilmaydi), shuning uchun qurilmada qolgan eski odam bilan adashib ketmaydi.
"""
STUDENT_BASE = 9001
TEACHER_BASE = 7001
BAND = 1000      # 9001..9999, 7001..7999


def _used():
    from accounts.models import Student, User
    taken = set(Student.objects.exclude(access_id__isnull=True).values_list('access_id', flat=True))
    taken |= set(User.objects.exclude(access_id__isnull=True).values_list('access_id', flat=True))
    return {t for t in taken if t}


def _next(base, taken):
    nums = [int(t) for t in taken if t.isdigit() and base <= int(t) < base + BAND - 1]
    n = max(nums) + 1 if nums else base
    while str(n) in taken:      # (ehtiyot uchun)
        n += 1
    return str(n)


def next_student_id(taken=None):
    return _next(STUDENT_BASE, _used() if taken is None else taken)


def next_teacher_id(taken=None):
    return _next(TEACHER_BASE, _used() if taken is None else taken)
