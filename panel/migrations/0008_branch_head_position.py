from django.db import migrations


def add_position(apps, schema_editor):
    from panel.perms import PRESETS
    Position = apps.get_model('panel', 'Position')
    name, is_owner, perms = next(p for p in PRESETS if p[0] == 'Filial rahbari')
    if Position.objects.filter(name=name).exists():
        return
    director = Position.objects.filter(name='Direktor').first()
    order = (director.order + 1) if director else 0
    Position.objects.filter(order__gte=order).exclude(pk=director.pk if director else None).update(order=models_F('order'))
    Position.objects.create(name=name, is_owner=is_owner, default_perms=list(perms), order=order)


def models_F(field):
    from django.db.models import F
    return F(field) + 1


def remove_position(apps, schema_editor):
    apps.get_model('panel', 'Position').objects.filter(name='Filial rahbari', staff__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [('panel', '0007_meals_permissions')]
    operations = [migrations.RunPython(add_position, remove_position)]
