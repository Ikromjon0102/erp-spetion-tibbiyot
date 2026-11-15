from django.core.management.base import BaseCommand, CommandError

from tgbot import services


class Command(BaseCommand):
    help = "Telegram webhookni o'rnatadi/o'chiradi: tg_webhook https://med.spetion.uz  |  tg_webhook --delete"

    def add_arguments(self, parser):
        parser.add_argument('base_url', nargs='?')
        parser.add_argument('--delete', action='store_true')

    def handle(self, base_url, delete, **o):
        if not services.token():
            raise CommandError("BOT_TOKEN .env da yo'q")
        if delete:
            return self.stdout.write(str(services.api('deleteWebhook')))
        if not base_url:
            raise CommandError('Domen kerak: tg_webhook https://med.spetion.uz')
        r = services.api('setWebhook', url=base_url.rstrip('/') + '/tg/webhook/', secret_token=services.webhook_secret(),
                         allowed_updates=['message'], drop_pending_updates=True)
        services.api('setMyCommands', commands=[
            {'command': 'bugun', 'description': 'Bugungi holat'}, {'command': 'baholar', 'description': 'Oxirgi baholar'},
            {'command': 'chiqish', 'description': 'Botni uzish'}])
        services.api('setChatMenuButton', menu_button={
            'type': 'web_app', 'text': 'Ilova', 'web_app': {'url': base_url.rstrip('/') + '/tg/app/'}})
        self.stdout.write(str(r))
