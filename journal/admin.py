from django.contrib import admin

from .models import Attendance, Grade, Homework


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('student', 'lesson', 'date', 'status')
    list_filter = ('status', 'date', 'lesson__teaching__group')


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('student', 'teaching', 'date', 'score', 'kind')
    list_filter = ('kind', 'teaching__group')


@admin.register(Homework)
class HomeworkAdmin(admin.ModelAdmin):
    list_display = ('teaching', 'due_date', 'assigned_on', 'short_text')
    list_filter = ('teaching__group', 'teaching__subject', 'teaching__teacher', 'assigned_on')
    search_fields = ('text',)
    date_hierarchy = 'due_date'

    @admin.display(description='Matn')
    def short_text(self, obj):
        return obj.text[:70] + ('…' if len(obj.text) > 70 else '')

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
