"""Bot buyruqlari: bog'lash (kontakt yoki kod), /bugun, /baholar, /parol (parolni tiklash), /chiqish."""
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from access.services import is_break_time, today_summary
from accounts.models import User
from accounts.passwords import issue_temp_password
from accounts.phone import to_digits
from journal.models import Grade

from .models import LinkCode, TelegramLink
from .services import app_url, esc, send

CONTACT_KB = {'keyboard': [[{'text': '📱 Telefon raqamni yuborish', 'request_contact': True}]],
              'resize_keyboard': True, 'one_time_keyboard': True}
MENU_KB = {'keyboard': [[{'text': '📍 Bugun'}, {'text': '📝 Baholar'}], [{'text': '🔑 Parolni tiklash'}]], 'resize_keyboard': True}
RESET_YES = '✅ Ha, yangi parol'
RESET_KB = {'keyboard': [[{'text': RESET_YES}], [{'text': 'Bekor qilish'}]], 'resize_keyboard': True, 'one_time_keyboard': True}
RESET_COOLDOWN = 10 * 60      # soniya: bir hisobga ketma-ket parol so'rab bo'lmaydi

WELCOME = ("Assalomu alaykum! Bu — maktab boti. Farzandingizning maktabga kelgani-ketgani, baholari, vazifalari va "
           "e'lonlar shu yerga keladi.\n\nBoshlash uchun maktabda ro'yxatdan o'tgan telefon raqamingizni yuboring "
           "(pastdagi tugma).")


def children_of(user):
    return list(user.children.filter(user__is_active=True).select_related('user', 'group'))


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
    if low in ('/ilova', '📱 ilovani ochish'):
        # Mini App faqat inline tugma yoki menyu tugmasi orqali ochilganda initData oladi (klaviatura tugmasida bo'sh bo'ladi)
        return send(chat_id, 'Ilovani ochish uchun tugmani bosing 👇',
                    reply_markup={'inline_keyboard': [[{'text': '📱 Ilovani ochish', 'web_app': {'url': app_url()}}]]})
    if low in ('/parol', '🔑 parolni tiklash'):
        if not _can_reset(linked.user):
            return send(chat_id, "Bu hisobning parolini bot orqali tiklab bo'lmaydi. Maktab ma'muriyatiga murojaat qiling.",
                        reply_markup=MENU_KB)
        return send(chat_id, "Yangi bir martalik parol berilsinmi?\n\nEski parolingiz ishlamay qoladi, saytga birinchi kirishda "
                             "yangi parol o'rnatasiz.", reply_markup=RESET_KB)
    if low == RESET_YES.lower():
        return reset_password(chat_id, linked.user)
    if low == 'bekor qilish':
        return send(chat_id, 'Bekor qilindi. Parolingiz o\'zgarmadi.', reply_markup=MENU_KB)
    if low == '/chiqish':
        linked.delete()
        return send(chat_id, "Bog'lanish o'chirildi. Qayta ulash uchun /start", reply_markup={'remove_keyboard': True})
    send(chat_id, 'Buyruqlar: /bugun — bugungi holat, /baholar — oxirgi baholar, /parol — parolni tiklash, /chiqish — uzish',
         reply_markup=MENU_KB)


def _can_reset(user):
    """Bot orqali faqat oddiy ota-ona hisobi parolini tiklash mumkin (ustoz, xodim va admin — ma'muriyat orqali)."""
    from panel.models import StaffProfile
    return (user.is_active and user.role == User.Role.PARENT and not user.is_superuser and not user.is_staff
            and not StaffProfile.objects.filter(user=user).exists())


def reset_password(chat_id, user):
    from panel.models import AuditLog
    if not _can_reset(user):
        return send(chat_id, "Bu hisobning parolini bot orqali tiklab bo'lmaydi. Maktab ma'muriyatiga murojaat qiling.",
                    reply_markup=MENU_KB)
    key = f'tg-reset:{user.pk}'
    if not cache.add(key, 1, RESET_COOLDOWN):
        return send(chat_id, "Parol yaqinda berilgan. Birozdan keyin (10 daqiqa) qayta urinib ko'ring.", reply_markup=MENU_KB)
    password = issue_temp_password(user)
    AuditLog.objects.create(actor=user, actor_name=user.get_full_name() or user.username, verb='Parolni Telegram orqali tikladi',
                            target_type='user', target_id=user.pk, target_label=(user.get_full_name() or user.username)[:200])
    send(chat_id, f"🔑 Bir martalik parol: <code>{esc(password)}</code>\n"
                  f"Login: <code>{esc(user.phone or user.username)}</code>\n\n"
                  "Saytga shu parol bilan kiring — darhol o'zingizning yangi parolingizni o'rnatasiz. "
                  "Bu xabarni kirgach o'chirib tashlang.", reply_markup=MENU_KB)


def today(chat_id, user):
    lines = []
    for k in children_of(user):
        row = today_summary(k)
        s = '❌ hali kelmagan'
        if row and row['arrived']:
            s = f"✅ keldi {row['arrived']:%H:%M}"
            if row['left']:
                s += f", 🚶 tashqarida {row['left']:%H:%M} dan" if is_break_time(org=k.branch.organization if k.branch_id else None) else f", 🚪 chiqdi {row['left']:%H:%M}"
        lines.append(f'<b>{esc(k.user.get_full_name())}</b>: {s}')
    send(chat_id, '\n'.join(lines) or 'Farzand topilmadi')


def grades(chat_id, user):
    lines = []
    for k in children_of(user):
        gs = Grade.objects.filter(student=k).select_related('teaching__subject').order_by('-date', '-id')[:5]
        body = '\n'.join(f'  {g.date:%d.%m} {esc(g.teaching.subject)}: <b>{g.score}</b>' for g in gs) or "  hali baho yo'q"
        lines.append(f'<b>{esc(k.user.get_full_name())}</b>\n{body}')
    send(chat_id, '\n\n'.join(lines) or 'Farzand topilmadi')
