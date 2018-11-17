import hashlib
import logging
import os

import django_libsass
import sass
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.templatetags.static import static

from pretalx.celery_app import app
from pretalx.event.models import Event

logger = logging.getLogger(__name__)


@app.task()
def regenerate_css(event_id: int):
    event = Event.objects.filter(pk=event_id).first()
    if not event:
        logger.error('In regenerate_css: Event ID {} not found.'.format(event_id))
        return
    local_apps = ['agenda', 'cfp']

    if not event.primary_color:
        for local_app in local_apps:
            event.settings.delete('{}_css_file'.format(local_app))
            event.settings.delete('{}_css_checksum'.format(local_app))
        return

    for local_app in local_apps:
        path = os.path.join(settings.STATIC_ROOT, local_app, 'scss/main.scss')
        sassrules = []

        if event.primary_color:
            sassrules.append('$brand-primary: {};'.format(event.primary_color))
            sassrules.append('@import "{}";'.format(path))

        custom_functions = dict(django_libsass.CUSTOM_FUNCTIONS)
        custom_functions['static'] = static
        css = sass.compile(
            string="\n".join(sassrules),
            output_style='compressed',
            custom_functions=custom_functions,
        )
        checksum = hashlib.sha1(css.encode('utf-8')).hexdigest()
        fname = '{}/{}.{}.css'.format(event.slug, local_app, checksum[:16])

        if event.settings.get('{}_css_checksum'.format(local_app), '') != checksum:
            newname = default_storage.save(fname, ContentFile(css.encode('utf-8')))
            event.settings.set('{}_css_file'.format(local_app), '/media/{}'.format(newname))
            event.settings.set('{}_css_checksum'.format(local_app), checksum)
