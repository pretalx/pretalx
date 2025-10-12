# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Florian Moesch

from contextlib import suppress

from django.http import Http404, HttpResponseRedirect
from django_scopes import scopes_disabled

from pretalx.person.models.user import User
from pretalx.submission.models.submission import Submission


@scopes_disabled()
def shortlink_view(request, code, *args, **kwargs):
    with suppress(Submission.DoesNotExist):
        submission = Submission.objects.select_related("event").get(code=code)
        if request.user.has_perm("submission.orga_list_submission", submission):
            return HttpResponseRedirect(submission.orga_urls.base)
        if request.user.has_perm("submission.view_public_submission", submission):
            return HttpResponseRedirect(submission.urls.public)
    with suppress(User.DoesNotExist):
        user = User.objects.get(code=code)
        if request.user.has_perm("person.administrator_user", user):
            return HttpResponseRedirect(user.orga_urls.admin)
        profiles = user.profiles.select_related("event").order_by("-created")
        for profile in profiles:
            if request.user.has_perm("person.orga_list_speakerprofile", profile):
                return HttpResponseRedirect(profile.orga_urls.base)
        if profile := profiles.first():
            if request.user == user:
                return HttpResponseRedirect(profile.event.urls.user)
            if request.user.has_perm("person.view_speakerprofile", profile):
                return HttpResponseRedirect(profile.urls.public)
    raise Http404()
