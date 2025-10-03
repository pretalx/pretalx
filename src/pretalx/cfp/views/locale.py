import datetime as dt

from django.conf import settings
from django.http import HttpResponseRedirect
from django.views.generic import View

from pretalx.common.views.generic import get_next_url


class LocaleSet(View):
    def get(self, request, *args, **kwargs):
        url = get_next_url(request, omit_params=["lang"]) or "/"
        resp = HttpResponseRedirect(url)
        locale = request.GET.get("locale")
        if locale in (lc for lc, __ in settings.LANGUAGES):
            if request.user.is_authenticated:
                request.user.locale = locale
                request.user.save()

            max_age = dt.timedelta(seconds=10 * 365 * 24 * 60 * 60)
            if hasattr(dt, "UTC"):
                expires = dt.datetime.now(dt.UTC) + max_age
            else:
                # TODO: drop when we stop supporting Python 3.10,
                # which is end of life in October 2026
                expires = dt.datetime.utcnow() + max_age
            resp.set_cookie(
                settings.LANGUAGE_COOKIE_NAME,
                locale,
                max_age=max_age,
                expires=expires.strftime("%a, %d-%b-%Y %H:%M:%S GMT"),
                domain=settings.SESSION_COOKIE_DOMAIN,
            )
        return resp
