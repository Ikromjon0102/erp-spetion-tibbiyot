"""Voqealar bo'yicha ota-onalarga xabar: kelish/ketish, baho, vazifa, e'lon."""
from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from access.models import AccessEvent
from journal.models import Grade, Homework
from notices.models import Announcement

from .services import esc, notify


def _parents(student):
    return list(student.parents.all())


@receiver(post_save, sender=AccessEvent)
def on_access(sender, instance, created, **kw):
    if not created or not instance.student_id or instance.occurred_at < timezone.now() - timedelta(minutes=30):
        return
    t = timezone.localtime(instance.occurred_at).strftime('%H:%M')
    name = esc(instance.student.user.get_full_name())
    if instance.direction == 'in':
        text = f'✅ <b>{name}</b> {t} da maktabga keldi'
    else:
        text = f'🚪 <b>{name}</b> {t} da maktabdan chiqdi'
    notify(_parents(instance.student), text, f'/oquvchi/{instance.student_id}/')


@receiver(post_save, sender=Grade)
def on_grade(sender, instance, created, **kw):
    if not created:
        return
    note = f'\n💬 {esc(instance.comment)}' if instance.comment else ''
    notify(_parents(instance.student),
           f'📝 <b>{esc(instance.student.user.get_full_name())}</b> — {esc(instance.teaching.subject)}: '
           f'<b>{instance.score}</b>{note}', f'/oquvchi/{instance.student_id}/')


@receiver(post_save, sender=Homework)
def on_homework(sender, instance, created, **kw):
    if not created:
        return
    from accounts.models import User
    parents = User.objects.filter(children__group=instance.teaching.group).distinct()
    notify(parents, f'📚 Yangi vazifa — <b>{esc(instance.teaching.subject)}</b> '
                    f'(muddat: {instance.due_date:%d.%m})\n{esc(instance.text[:300])}', '/')


@receiver(post_save, sender=Announcement)
def on_announcement(sender, instance, created, **kw):
    if not created or instance.audience == 'students' or instance.title.startswith('[Sinov]'):
        return
    from notices.services import recipients_of
    notify(recipients_of(instance), f'📢 <b>{esc(instance.title)}</b>\n{esc(instance.body[:600])}', '/elonlar/')
