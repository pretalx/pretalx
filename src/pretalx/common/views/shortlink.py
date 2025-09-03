from contextlib import suppress

from django.http import Http404, HttpResponseRedirect
from django_scopes import scopes_disabled

from pretalx.person.models.user import User
from pretalx.submission.models.submission import Submission


def has_event_access(user, event):
    return not user.is_anonymous and user.has_perm("event.orga_access_event", event)


@scopes_disabled()
def shortlink_view(request, code, *args, **kwargs):
    with suppress(Submission.DoesNotExist):
        submission = Submission.objects.select_related("event").get(code=code)
        if has_event_access(request.user, submission.event):
            return HttpResponseRedirect(submission.orga_urls.base)
        return HttpResponseRedirect(submission.urls.public)
    with suppress(User.DoesNotExist):
        user = User.objects.get(code=code)
        if not request.user.is_anonymous and request.user.is_administrator:
            return HttpResponseRedirect(user.orga_urls.admin)
        profiles = user.profiles.select_related("event").order_by("-created")
        for profile in profiles:
            if has_event_access(request.user, profile.event):
                return HttpResponseRedirect(profile.orga_urls.base)
        if profile := profiles.first():
            if request.user == user:
                return HttpResponseRedirect(profile.event.urls.user)
            return HttpResponseRedirect(profile.urls.public)
    raise Http404()
