from contextlib import suppress

from django.http import HttpResponseRedirect
from django_scopes import scopes_disabled

from pretalx.person.models.user import User
from pretalx.submission.models.submission import Submission


@scopes_disabled()
def shortlink_view(request, code, *args, **kwargs):
    with suppress(Submission.DoesNotExist):
        submission = Submission.objects.get(code=code)
        if not request.user.is_anonymous and request.user.has_perm(
            "event.orga_access_event", submission.event
        ):
            return HttpResponseRedirect(submission.orga_urls.base)
        return HttpResponseRedirect(submission.urls.public)
    with suppress(User.DoesNotExist):
        user = User.objects.get(code=code)
        if not request.user.is_anonymous and request.user.is_administrator:
            return HttpResponseRedirect(user.orga_urls.admin)
        if profile := user.profiles.order_by("-created").first():
            if not request.user.is_anonymous and request.user.has_perm(
                "event.orga_access_event", profile.event
            ):
                return HttpResponseRedirect(profile.orga_urls.base)
            if request.user == user:
                return HttpResponseRedirect(profile.event.urls.user)
            return HttpResponseRedirect(profile.urls.public)
    return HttpResponseRedirect("/404")
