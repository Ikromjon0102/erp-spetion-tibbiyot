from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from accounts.phone import to_digits
from tgbot import services
from tgbot.models import LinkCode


class Command(BaseCommand):
    help = "Ota-ona uchun bir martalik ulash havolasi: tg_link +998911234567"

    def add_arguments(self, parser):
        parser.add_argument('phone')

    def handle(self, phone, **o):
        user = User.objects.filter(phone_digits=to_digits(phone)).first()
        if not user:
            raise CommandError("Bunday raqamli foydalanuvchi yo'q")
        me = (services.api('getMe') or {}).get('result', {}).get('username', 'BOT')
        self.stdout.write(f'{user}: https://t.me/{me}?start={LinkCode.objects.create(user=user).code}')
