from django.contrib import admin

from .models import Group, Lesson, Subject, Teaching

admin.site.register(Group)
admin.site.register(Subject)


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1


@admin.register(Teaching)
class TeachingAdmin(admin.ModelAdmin):
    list_display = ('subject', 'group', 'teacher')
    list_filter = ('group', 'teacher')
    inlines = [LessonInline]
