from django.db import migrations
from django.db.models import Max


def add_position(apps, schema_editor):
    """«Fotograf» — bog'chada rasm/videoga olib ota-onalarga tarqatadigan xodim: faqat galereya (2026-11-26)."""
    Position = apps.get_model('panel', 'Position')
    if Position.objects.filter(name='Fotograf').exists():
        return
    order = (Position.objects.aggregate(m=Max('order'))['m'] or 0) + 1
    Position.objects.create(name='Fotograf', is_owner=False, default_perms=['gallery.view', 'gallery.manage'], order=order)


def remove_position(apps, schema_editor):
    apps.get_model('panel', 'Position').objects.filter(name='Fotograf', staff__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [('panel', '0010_gallery_permissions')]
    operations = [migrations.RunPython(add_position, remove_position)]
