from django.apps import AppConfig


class OrgConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'org'
    verbose_name = 'Tashkilot'

    def ready(self):
        from . import signals  # noqa: F401
