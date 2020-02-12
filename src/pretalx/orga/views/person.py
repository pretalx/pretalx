import urllib

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.generic import View

from pretalx.person.models import User


class UserList(View):
    def dispatch(self, request, *args, **kwargs):
        search = request.GET.get("search")
        if not search or len(search) < 2:
            return JsonResponse({"count": 0, "results": []})

        events = self.request.user.get_events_for_permission(
            can_change_submissions=True
        )
        queryset = User.objects.filter(
            Q(name__icontains=search) | Q(email__icontains=search),
            profiles__event__in=events,
        )
        if request.GET.get("orga", "false").lower() == "true":
            queryset = queryset.filter(teams__in=request.event.teams)

        return JsonResponse(
            {
                "count": len(queryset),
                "results": [
                    {"email": user.email, "name": user.name} for user in queryset
                ],
            }
        )


class SubuserView(View):
    def dispatch(self, request, *args, **kwargs):
        request.user.is_administrator = request.user.is_superuser
        request.user.is_superuser = False
        request.user.save(update_fields=["is_administrator", "is_superuser"])
        messages.success(
            request, _("You are now an administrator instead of a superuser.")
        )
        params = request.GET.copy()
        url = urllib.parse.unquote(params.pop("next", [""])[0])
        if url and url_has_allowed_host_and_scheme(url, allowed_hosts=None):
            return redirect(url + ("?" + params.urlencode() if params else ""))
        return redirect(reverse("orga:event.list"))
