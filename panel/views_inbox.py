"""Rahbariyatga xabar: founder bir yoki bir nechta rahbarni (direktor, filial rahbari, hisobchi...) tanlab yozadi; xabar panelda
turadi va Telegram'ga ham boradi. A'zolar javob yozadi (yozishma), founder kim o'qiganini ko'radi.
Founder quyi xodimlarga ismi bilan emas, «Rahbariyat» bo'lib ko'rinadi (founder ko'rinmasligi qoidasi)."""
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone


from . import audit
from .access import is_owner, panel_required
from .models import StaffProfile, Thread, ThreadMember, ThreadMessage

OWNER_LABEL = 'Rahbariyat'


def unread_count(user):
    return ThreadMember.objects.filter(user=user).filter(Q(last_read_at__isnull=True) | Q(last_read_at__lt=F('thread__last_message_at'))).count()


def author_label(author, viewer):
    if author is None:
        return "O'chirilgan foydalanuvchi"
    if is_owner(author) and not is_owner(viewer):
        return OWNER_LABEL
    prof = getattr(author, 'staff_profile', None)
    pos = prof.position.name if prof else ''
    return f"{author.get_full_name() or author.username}" + (f' · {pos}' if pos else '')


def recipients_qs():
    """Xabar oladiganlar: faol panel xodimlari (founderlardan tashqari)."""
    return (StaffProfile.objects.filter(is_active=True, user__is_active=True, position__is_owner=False, user__is_superuser=False)
            .select_related('user', 'position').prefetch_related('user__branches__organization').order_by('position__order', 'user__last_name'))


def _notify(thread, author, body, exclude):
    from tgbot.services import esc, notify
    users = [m.user for m in thread.members.select_related('user') if m.user_id != exclude]
    if not users:
        return
    who = OWNER_LABEL if is_owner(author) else (author.get_full_name() or author.username)
    notify(users, f'✉️ <b>{esc(who)}</b> — {esc(thread.subject)}\n\n{esc(body[:700])}', reverse('panel:thread', args=[thread.pk]))


@panel_required()
def inbox(request):
    rows = (ThreadMember.objects.filter(user=request.user).select_related('thread', 'thread__created_by')
            .order_by('-thread__last_message_at'))
    threads = []
    for m in rows:
        last = m.thread.messages.select_related('author').last()
        threads.append({'t': m.thread, 'unread': m.unread, 'last': last,
                        'last_by': author_label(last.author, request.user) if last else '',
                        'n_members': m.thread.members.count() - 1})
    return render(request, 'panel/inbox.html', {'nav': 'inbox', 'threads': threads, 'can_write': is_owner(request.user)})


class NewThreadForm(forms.Form):
    subject = forms.CharField(label='Mavzu', max_length=200, widget=forms.TextInput(attrs={'placeholder': "Masalan: Dekabr oyi rejasi"}))
    body = forms.CharField(label='Xabar', max_length=4000, widget=forms.Textarea(attrs={'rows': 6, 'placeholder': 'Xabar matni…'}))
    to = forms.ModelMultipleChoiceField(label='Kimga', queryset=StaffProfile.objects.none(), widget=forms.CheckboxSelectMultiple,
                                        error_messages={'required': 'Kamida bitta rahbarni tanlang'})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['to'].queryset = recipients_qs()


@panel_required()
def thread_new(request):
    if not is_owner(request.user):
        raise PermissionDenied("Rahbariyatga yozishma ochish — founder uchun")
    form = NewThreadForm(request.POST or None, initial={'to': request.GET.getlist('to')})
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        now = timezone.now()
        with transaction.atomic():
            t = Thread.objects.create(subject=d['subject'].strip(), created_by=request.user, last_message_at=now)
            ThreadMessage.objects.create(thread=t, author=request.user, body=d['body'].strip())
            ThreadMember.objects.create(thread=t, user=request.user, last_read_at=now)
            ThreadMember.objects.bulk_create([ThreadMember(thread=t, user=p.user) for p in d['to']])
        _notify(t, request.user, d['body'], exclude=request.user.pk)
        audit.log(request, 'Rahbariyatga xabar yozdi', t, label=t.subject, details={'kimga': [str(p.user) for p in d['to']]}, target_type='thread')
        messages.success(request, f"Yuborildi: {len(d['to'])} kishiga (panelda va Telegram'da)")
        return redirect('panel:thread', pk=t.pk)
    groups = {}
    for p in form.fields['to'].queryset:
        orgs = sorted({b.organization.label for b in p.user.branches.all()})
        p.where = ', '.join(orgs) or '—'
        groups.setdefault(p.position.name, []).append(p)
    return render(request, 'panel/inbox_new.html', {'nav': 'inbox', 'form': form, 'groups': groups,
                                                     'checked': {str(x) for x in (form['to'].value() or [])}})


class ReplyForm(forms.Form):
    body = forms.CharField(label='Javob', max_length=4000, widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Javob yozing…'}))


@panel_required()
def thread(request, pk):
    t = get_object_or_404(Thread, pk=pk)
    me = ThreadMember.objects.filter(thread=t, user=request.user).first()
    if me is None:
        raise PermissionDenied
    form = ReplyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        body = form.cleaned_data['body'].strip()
        now = timezone.now()
        ThreadMessage.objects.create(thread=t, author=request.user, body=body)
        Thread.objects.filter(pk=t.pk).update(last_message_at=now)
        ThreadMember.objects.filter(pk=me.pk).update(last_read_at=now)
        t.last_message_at = now
        _notify(t, request.user, body, exclude=request.user.pk)
        return redirect(f"{reverse('panel:thread', args=[t.pk])}#oxiri")
    ThreadMember.objects.filter(pk=me.pk).update(last_read_at=timezone.now())
    owner = is_owner(request.user)
    msgs = [{'m': m, 'who': author_label(m.author, request.user), 'mine': m.author_id == request.user.pk}
            for m in t.messages.select_related('author', 'author__staff_profile__position')]
    members = []
    if owner:       # founder: kim o'qigan / o'qimagan
        for m in t.members.select_related('user', 'user__staff_profile__position').exclude(user=request.user):
            seen = m.last_read_at is not None and m.last_read_at >= t.last_message_at
            members.append({'name': author_label(m.user, request.user), 'seen': seen, 'at': m.last_read_at})
    return render(request, 'panel/inbox_thread.html', {'nav': 'inbox', 't': t, 'msgs': msgs, 'form': form, 'members': members,
                                                       'owner': owner})
