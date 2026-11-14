from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from .models import Student, User
from .passwords import issue_temp_password


@admin.register(User)
class SchoolUserAdmin(UserAdmin):
    list_display = ('username', 'get_full_name', 'role', 'phone', 'must_change_password', 'is_active')
    list_editable = ('phone',)  # telefonlarni ro'yxatning o'zida tez kiritish uchun
    list_filter = ('role', 'is_active', 'must_change_password')
    search_fields = ('username', 'first_name', 'last_name', 'phone')
    actions = ['password_from_phone', 'temp_password']
    fieldsets = UserAdmin.fieldsets + (('Maktab', {'fields': ('role', 'phone', 'must_change_password', 'is_demo')}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Maktab', {'fields': ('first_name', 'last_name', 'role', 'phone')}),)

    @admin.action(description="Ustozlar: parolni telefonning oxirgi 4 raqamiga o'rnatish")
    def password_from_phone(self, request, queryset):
        done, no_phone, parents, others = 0, [], [], []
        for u in queryset:
            digits = ''.join(ch for ch in u.phone if ch.isdigit())
            if u.is_parent:  # ota-onalarda bolalar ma'lumoti bor: 4 xonali parol xavfsiz emas
                parents.append(str(u))
            elif not u.is_teacher:  # admin va o'quvchilar parolini bu amal bilan o'zgartirmaymiz
                others.append(str(u))
            elif len(digits) < 4:
                no_phone.append(str(u))
            else:
                u.set_password(digits[-4:])
                u.must_change_password = True  # birinchi kirishdan keyin o'zi yangi parol qo'yadi
                u.save()
                done += 1
        self.message_user(request, f"{done} ta ustozning paroli telefonning oxirgi 4 raqamiga o'rnatildi "
                                   "(birinchi kirishda yangi parol so'raladi).")
        if no_phone:
            self.message_user(request, "Telefon kiritilmagani uchun o'tkazib yuborildi: " + ', '.join(no_phone),
                              level=messages.WARNING)
        if others:
            self.message_user(request, "Faqat ustozlar uchun, o'tkazib yuborildi: " + ', '.join(others),
                              level=messages.WARNING)
        if parents:
            self.message_user(request, "Ota-onalar o'tkazib yuborildi (ular uchun \"Bir martalik parol berish\" amalini "
                                       "ishlating): " + ', '.join(parents), level=messages.WARNING)

    @admin.action(description="Bir martalik parol berish (birinchi kirishda yangisini qo'yadi)")
    def temp_password(self, request, queryset):
        lines = []
        for u in queryset:
            lines.append(f'{u.get_full_name() or u.username}  |  login: {u.phone or u.username}  |  parol: {issue_temp_password(u)}')
        self.message_user(request, 'Bir martalik parollar (faqat hozir ko\'rinadi, ota-onaga yetkazing):\n' + '\n'.join(lines))


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('user', 'group', 'birth_date')
    list_filter = ('group',)
    search_fields = ('user__first_name', 'user__last_name', 'user__username')
    filter_horizontal = ('parents',)
