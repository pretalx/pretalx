import importlib
from contextlib import suppress

from allauth.account.views import confirm_email
from allauth.socialaccount import providers
from django.apps import apps
from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.static import static

plugin_patterns = []
for app in apps.get_app_configs():
    if hasattr(app, 'PretalxPluginMeta'):
        if importlib.util.find_spec(app.name + '.urls'):
            urlmod = importlib.import_module(app.name + '.urls')
            single_plugin_patterns = []
            if hasattr(urlmod, 'urlpatterns'):
                single_plugin_patterns += urlmod.urlpatterns
            plugin_patterns.append(
                url(r'', include((single_plugin_patterns, app.label)))
            )

# For django-allauth, based on
# https://stackoverflow.com/questions/27157396/django-allauth-how-can-i-only-allow-signup-login-through-social/41454423#41454423
auth_patterns = [
    url(r'^confirm-email/(?P<key>[-:\w]+)/$', confirm_email, name='account_confirm_email'),
]
for provider in providers.registry.get_list():
    try:
        prov_mod = importlib.import_module(provider.get_package() + '.urls')
    except ImportError:
        continue
    prov_urlpatterns = getattr(prov_mod, 'urlpatterns', None)
    if prov_urlpatterns:
        auth_patterns += prov_urlpatterns

urlpatterns = [
    url(r'^orga/', include('pretalx.orga.urls', namespace='orga')),
    url(r'^api/', include('pretalx.api.urls', namespace='api')),
    url('^auth/', include(auth_patterns)),
    url(r'', include('pretalx.agenda.urls', namespace='agenda')),
    url(r'', include('pretalx.cfp.urls', namespace='cfp')),
    url(r'', include((plugin_patterns, 'plugins'))),
]

if settings.DEBUG:
    with suppress(ImportError):
        import debug_toolbar
        urlpatterns += [
            url(r'^__debug__/', include(debug_toolbar.urls)),
        ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
