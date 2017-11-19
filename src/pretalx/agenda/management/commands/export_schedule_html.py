from bakery.management.commands.build import Command as BakeryBuildCommand
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.urlresolvers import get_callable
from django.utils import translation

from pretalx.event.models import Event


class Command(BakeryBuildCommand):
    help = 'Exports event schedule as a static HTML dump'

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('event', type=str)

    def handle(self, *args, **options):
        try:
            event = Event.objects.get(slug__iexact=options['event'])
        except Event.DoesNotExist:
            raise CommandError('Could not find event with slug "{}"'.format(options['event']))

        self._exporting_event = event
        translation.activate(event.locale)

        settings.COMPRESS_ENABLED = True
        settings.COMPRESS_OFFLINE = True
        call_command('rebuild')  # collect static files and combine/compress them

        super().handle(*args, **options)

    def build_views(self):
        for view_str in self.view_list:
            view = get_callable(view_str)
            view(_exporting_event=self._exporting_event).build_method()
