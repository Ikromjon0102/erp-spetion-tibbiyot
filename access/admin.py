from django.contrib import admin

from .models import AccessEvent, Device


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'direction', 'is_active', 'last_seen', 'push_path')
    readonly_fields = ('push_path', 'last_seen')
    fields = ('name', 'direction', 'is_active', 'push_path', 'last_seen')

    @admin.display(description='Qurilmaga kiritiladigan manzil (path)')
    def push_path(self, obj):
        return obj.push_path if obj.pk else 'Saqlangandan keyin ko\'rinadi'


@admin.register(AccessEvent)
class AccessEventAdmin(admin.ModelAdmin):
    list_display = ('occurred_at', 'student', 'employee_no', 'person_name', 'direction', 'device')
    list_filter = ('direction', 'device', ('student', admin.EmptyFieldListFilter))
    search_fields = ('employee_no', 'person_name', 'student__user__first_name', 'student__user__last_name')
    date_hierarchy = 'occurred_at'
    readonly_fields = ('raw',)
