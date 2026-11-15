"""Bot buyruqlari: bog'lash (kontakt yoki kod), /bugun, /baholar, /chiqish."""
from datetime import timedelta

from django.utils import timezone

from access.models import AccessEvent
from accounts.models import User
from accounts.phone import to_digits
from journal.models import Grade

from .models import LinkCode, TelegramLink
from .services import app_url, esc, send

CONTACT_KB = {'keyboard': [[{'text': '📱 Telefon raqamni yuborish', 'request_contact': True}]],
              'resize_keyboard': True, 'one_time_keyboard': True}
MENU_KB = {'keyboard': [[{'text': '📱 Ilovani ochish', 'web_app': {'url': app_url()}}],
                        [{'text': '📍 Bugun'}, {'text': '📝 Baholar'}]], 'resize_keyboard': True}

WELCOME = ("Assalomu alaykum! Bu — maktab boti. Farzandingizning maktabga kelgani-ketgani, baholari, vazifalari va "
           "e'lonlar shu yerga keladi.\n\nBoshlash uchun maktabda ro'yxatdan o'tgan telefon raqamingizni yuboring "
           "(pastdagi tugma).")


def children_of(user):
    return list(user.children.select_related('user', 'group'))


def link(chat_id, username, user):
    TelegramLink.objects.update_or_create(chat_id=chat_id, defaults={'user': user, 'username': username or ''})
    kids = children_of(user)
    names = '\n'.join(f'• {esc(k.user.get_full_name())} ({esc(k.group or "—")})' for k in kids) or '—'
    send(chat_id, f'✅ Ulandi, {esc(user.get_full_name())}!\n\nFarzandlaringiz:\n{names}', reply_markup=MENU_KB)


def handle(update):
    msg = update.get('message')
    if not msg:
        return
    chat_id = msg['chat']['id']
    frm = msg.get('from') or {}
    text = (msg.get('text') or '').strip()
    linked = TelegramLink.objects.filter(chat_id=chat_id).select_related('user').first()

    if msg.get('contact'):
        c = msg['contact']
        if c.get('user_id') != frm.get('id'):       # boshqa odamning kontaktini yuborib bo'lmaydi
            return send(chat_id, "Iltimos, faqat o'zingizning raqamingizni (pastdagi tugma orqali) yuboring.",
                        reply_markup=CONTACT_KB)
        digits = to_digits('+' + str(c.get('phone_number', '')).lstrip('+'))
        user = None
        if digits:
            user = next((u for u in User.objects.filter(phone_digits=digits, is_active=True) if u.has_children), None)
        if not user:
            return send(chat_id, "Bu raqam maktabda ota-ona sifatida topilmadi. Maktab ma'muriyatiga murojaat qiling.")
        return link(chat_id, frm.get('username'), user)

    if text.startswith('/start'):
        code = text.split(maxsplit=1)[1].strip() if ' ' in text else ''
        if code:
            lc = (LinkCode.objects.filter(code=code, created_at__gte=timezone.now() - timedelta(days=3))
                  .select_related('user').first())
            if lc:
                lc.delete()
                return link(chat_id, frm.get('username'), lc.user)
            return send(chat_id, "Havola eskirgan yoki noto'g'ri. Maktabdan yangisini so'rang yoki telefon "
                                 "raqamingizni yuboring.", reply_markup=CONTACT_KB)
        if linked:
            return send(chat_id, 'Menyudan tanlang 👇', reply_markup=MENU_KB)
        return send(chat_id, WELCOME, reply_markup=CONTACT_KB)

    if not linked:
        return send(chat_id, WELCOME, reply_markup=CONTACT_KB)

    low = text.lower()
    if low in ('/bugun', '📍 bugun'):
        return today(chat_id, linked.user)
    if low in ('/baholar', '📝 baholar'):
        return grades(chat_id, linked.user)
    if low == '/chiqish':
        linked.delete()
        return send(chat_id, "Bog'lanish o'chirildi. Qayta ulash uchun /start", reply_markup={'remove_keyboard': True})
    send(chat_id, 'Buyruqlar: /bugun — bugungi holat, /baholar — oxirgi baholar, /chiqish — uzish', reply_markup=MENU_KB)


def _hm(e):
    return timezone.localtime(e.occurred_at).strftime('%H:%M')


def today(chat_id, user):
    day, lines = timezone.localdate(), []
    for k in children_of(user):
        ev = list(AccessEvent.objects.filter(student=k, occurred_at__date=day).order_by('occurred_at'))
        ins, outs = [e for e in ev if e.direction == 'in'], [e for e in ev if e.direction == 'out']
        s = '❌ hali kelmagan'
        if ins:
            s = f'✅ keldi {_hm(ins[0])}'
            if outs and outs[-1].occurred_at > ins[0].occurred_at:
                s += f', 🚪 chiqdi {_hm(outs[-1])}'
        lines.append(f'<b>{esc(k.user.get_full_name())}</b>: {s}')
    send(chat_id, '\n'.join(lines) or 'Farzand topilmadi')


def grades(chat_id, user):
    lines = []
    for k in children_of(user):
        gs = Grade.objects.filter(student=k).select_related('teaching__subject').order_by('-date', '-id')[:5]
        body = '\n'.join(f'  {g.date:%d.%m} {esc(g.teaching.subject)}: <b>{g.score}</b>' for g in gs) or "  hali baho yo'q"
        lines.append(f'<b>{esc(k.user.get_full_name())}</b>\n{body}')
    send(chat_id, '\n\n'.join(lines) or 'Farzand topilmadi')
