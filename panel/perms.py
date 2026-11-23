"""Boshqaruv paneli ruxsatlari katalogi. Ruxsat kodi: 'modul.amal'. Har bir xodimga alohida belgilanadi;
lavozim faqat boshlang'ich namuna (belgilarni oldindan qo'yib beradi)."""

CATALOG = [
    ('students', "O'quvchilar", [
        ('view', "Ro'yxat va o'quvchi kartasini ko'rish"),
        ('add', "O'quvchi qo'shish"),
        ('change', "Tahrirlash va ota-ona biriktirish"),
        ('import', "Excel'dan yuklash"),
    ]),
    ('teachers', "Ustozlar", [
        ('view', "Ro'yxat va ustoz kartasini ko'rish"),
        ('add', "Ustoz qo'shish"),
        ('change', "Tahrirlash, dars biriktirish, parolni tiklash, nofaol qilish"),
    ]),
    ('parents', "Ota-onalar", [
        ('view', "Ro'yxat va ota-ona kartasini ko'rish"),
        ('add', "Ota-ona qo'shish"),
        ('change', "Tahrirlash, farzand biriktirish, parolni tiklash"),
    ]),
    ('schedule', "Dars jadvali", [
        ('view', "Jadvalni ko'rish"),
        ('change', "Dars qo'shish, o'zgartirish va olib tashlash"),
    ]),
    ('devices', "Qurilmalar va yuz rasmlari", [
        ('view', "Qurilmalar holati va rasm sync natijasini ko'rish"),
        ('manage', "Qurilma sozlash, rasmlarni ZIP bilan yuklash, sync qilish"),
    ]),
    ('sensitive', "Maxfiy ma'lumotlar", [
        ('phones', "Telefon raqamlarni ko'rish"),
        ('grades', "Baholarni ko'rish"),
    ]),
    ('payments', "To'lovlar", [
        ('view', "To'lovlar, qarzdorlar va chegirmalarni ko'rish"),
        ('accept', "To'lov qabul qilish"),
        ('discounts', "Chegirmalarni boshqarish va o'quvchilarga biriktirish"),
        ('settings', "Oylik narx va to'lov muddatini belgilash"),
        ('reports', "Hisobotlarni yuklab olish (Excel / PDF)"),
        ('void', "To'lovni bekor qilish"),
    ]),
    ('groups', "Sinflar", [
        ('view', "Ko'rish"),
        ('change', "Qo'shish va tahrirlash"),
    ]),
    ('monitoring', "Kunlik nazorat", [
        ('view', "Kim kelgan, davomat olinmaganlar, qurilmalar holati"),
    ]),
    ('announcements', "E'lonlar", [
        ('view', "Ko'rish va kim o'qiganini bilish"),
        ('add', "Yangi e'lon yuborish"),
        ('change', "E'lonni tahrirlash va o'chirish"),
    ]),
    ('staff', "Xodimlar", [
        ('view', "Xodimlar ro'yxatini ko'rish"),
        ('manage', "Xodim qo'shish va ruxsatlarni boshqarish"),
    ]),
    ('expenses', "Xarajatlar", [
        ('view', "Xarajatlar va kirim-chiqim hisobotini ko'rish"),
        ('add', "Xarajat qo'shish"),
        ('change', "Xarajatni tahrirlash va o'chirish"),
        ('manage', "Takroriy xarajatlar (ijara, kommunal...)"),
    ]),
    ('payroll', "Oyliklar", [
        ('view', "Oyliklarni ko'rish"),
        ('manage', "Oylik qoidalari, hisoblash va to'lash"),
    ]),
    ('meals', "Taomnoma", [
        ('view', "Taomnomani ko'rish"),
        ('manage', "Menyu, taomlar rasmi va ovqatsiz kunlarni boshqarish"),
    ]),
    ('org', "Tashkilot", [
        ('settings', "Exam platformasi bilan bog'lash (tashkilot va brend sozlamasi — faqat maktab egasida)"),
    ]),
    ('audit', "Faoliyat jurnali", [
        ('view', "Ko'rish"),
    ]),
]

ALL_PERMS = [f'{module}.{action}' for module, _, actions in CATALOG for action, _ in actions]
LABELS = {f'{m}.{a}': label for m, _, actions in CATALOG for a, label in actions}

# Boshqa amal tanlansa, shu modulning "ko'rish" ruxsati ham kerak (ko'rmasdan tahrirlab bo'lmaydi)
NEEDS_VIEW = {'parents', 'schedule', 'devices', 'teachers', 'students', 'groups', 'announcements', 'staff', 'payments', 'expenses', 'payroll', 'meals'}


def normalize(perms):
    """Noma'lum kodlarni tashlaydi, takrorlarni olib tashlaydi va kerakli 'ko'rish' ruxsatlarini qo'shadi."""
    chosen = {p for p in perms if p in ALL_PERMS}
    for module in NEEDS_VIEW:
        if any(p.startswith(module + '.') for p in chosen):
            chosen.add(f'{module}.view')
    return sorted(chosen, key=ALL_PERMS.index)


def _all_except(*excluded):
    return [p for p in ALL_PERMS if p not in excluded]


# Lavozim namunalari: (to'liq ruxsat egasimi, ruxsatlar). Maktab egasi tahrirlay oladi.
PRESETS = [
    ('Maktab egasi', True, ALL_PERMS),
    # Xarajat va oyliklar maxfiy: Direktorda ham yo'q, «Maktab egasi» (founder) kerakli odamga alohida beradi
    ('Direktor', False, _all_except('staff.manage', *[p for p in ALL_PERMS if p.startswith(('expenses.', 'payroll.'))])),
    ("Zam (o'quv ishlari)", False, ['students.view', 'students.change', 'teachers.view', 'teachers.change', 'schedule.view', 'schedule.change', 'parents.view', 'sensitive.grades', 'groups.view', 'groups.change',
                                    'monitoring.view', 'announcements.view', 'announcements.add', 'announcements.change']),
    ('Reception', False, ['students.view', 'teachers.view', 'parents.view', 'parents.add', 'parents.change', 'schedule.view', 'students.add', 'students.change', 'sensitive.phones', 'groups.view',
                          'monitoring.view', 'announcements.view', 'payments.view', 'payments.accept']),
    ('Hisobchi', False, ['students.view', 'sensitive.phones', 'payments.view', 'payments.reports', 'groups.view',
                         'announcements.view', 'expenses.view', 'expenses.add', 'expenses.change', 'expenses.manage', 'payroll.view', 'payroll.manage']),
    ('Zavxoz', False, ['schedule.view', 'devices.view', 'groups.view', 'monitoring.view', 'announcements.view', 'meals.view', 'meals.manage']),
]
