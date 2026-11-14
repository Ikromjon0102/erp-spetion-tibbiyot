from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .models import Announcement, AnnouncementRead
from .services import read_summary, read_times, recipients_of

SENT = mark_safe('<span style="color:#8a948d;font-weight:700" title="Yuborildi">✓</span>')
READ = mark_safe('<span style="color:#1b8a3c;font-weight:700" title="Oqildi">✓✓</span>')


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'audience', 'group', 'created_at', 'read_status')
    list_filter = ('audience', 'group')
    readonly_fields = ('recipients_status',)

    @admin.display(description="O'qilgan")
    def read_status(self, obj):
        total, read = read_summary(obj)
        if not total:
            return '—'
        icon = READ if read == total else SENT
        return format_html('{} <b>{}</b>/{}', icon, read, total)

    @admin.display(description="Kim o'qidi")
    def recipients_status(self, obj):
        """Telegramdagi kabi: ✓ — yuborildi (hali ochmagan), ✓✓ — o'qildi (vaqti bilan)."""
        if not obj.pk:
            return "E'lon saqlangandan keyin ko'rinadi"
        recipients, times = recipients_of(obj), read_times(obj)
        if not recipients:
            return "Qabul qiluvchi yo'q (yoki hali hech kimda parol yo'q)"
        rows = []
        for u in sorted(recipients, key=lambda u: (u.pk not in times, times.get(u.pk) or 0, u.last_name, u.first_name)):
            read_at = times.get(u.pk)
            status = READ if read_at else SENT
            when = timezone.localtime(read_at).strftime('%d.%m.%Y %H:%M') if read_at else 'hali ochmagan'
            roles = ', '.join(filter(None, [u.get_role_display(), 'ota-ona' if u.is_teacher and u.has_children else '']))
            rows.append((status, u.get_full_name() or u.username, roles, when))
        total, read = len(recipients), len(times.keys() & {u.pk for u in recipients})
        head = format_html('<p><b>{}</b> / {} ta qabul qiluvchi o\'qigan. Paroli yo\'q hisoblar (hali kirmagan) sanalmaydi.</p>', read, total)
        table = format_html('<table><thead><tr><th></th><th>Ism</th><th>Rol</th><th>Vaqt</th></tr></thead><tbody>{}</tbody></table>',
                            format_html_join('', '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>', rows))
        return format_html('{}{}', head, table)

    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(AnnouncementRead)
class AnnouncementReadAdmin(admin.ModelAdmin):
    list_display = ('announcement', 'user', 'read_at')
    list_filter = ('announcement',)
    date_hierarchy = 'read_at'

    def has_add_permission(self, request):
        return False
