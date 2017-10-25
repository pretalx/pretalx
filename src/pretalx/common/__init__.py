from contextlib import suppress

from django.apps import AppConfig


class CommonConfig(AppConfig):
    name = 'pretalx.common'


with suppress(ImportError):
    import pretalx.celery_app as celery  # NOQA
