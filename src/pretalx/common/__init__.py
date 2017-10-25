from contextlib import suppress

from django.apps import AppConfig


class CommonConfig(AppConfig):
    name = 'pretalx.common'

    def ready(self):
        from pretalx.event.models import Event
        from pretalx.common.tasks import regenerate_css

        for event in Event.objects.all():
            regenerate_css.apply_async(args=(event.pk,))


with suppress(ImportError):
    import pretalx.celery_app as celery  # NOQA
