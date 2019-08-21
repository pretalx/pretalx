from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.http import is_safe_url
from django.utils.translation import override
from django.views.generic import View

from pretalx.common.phrases import phrases


class LocaleSet(View):

    def get(self, request, *args, **kwargs):
        url = request.GET.get('next', request.headers.get('Referer', '/'))
        url = url if is_safe_url(url, allowed_hosts=None) else '/'
        resp = HttpResponseRedirect(url)

        locale = request.GET.get('locale')
        if locale in [lc for lc, ll in settings.LANGUAGES]:
            if request.user.is_authenticated:
                request.user.locale = locale
                request.user.save()

            max_age = 10 * 365 * 24 * 60 * 60
            resp.set_cookie(settings.LANGUAGE_COOKIE_NAME, locale, max_age=max_age,
                            expires=(datetime.utcnow() + timedelta(seconds=max_age)).strftime(
                                '%a, %d-%b-%Y %H:%M:%S GMT'),
                            domain=settings.SESSION_COOKIE_DOMAIN)
            with override(locale):
                messages.success(request, str(phrases.cfp.locale_change_success))

        return resp
