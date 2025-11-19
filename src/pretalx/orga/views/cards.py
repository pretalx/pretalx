# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from pretalx.common.views.mixins import EventPermissionRequired
from pretalx.submission.models import SubmissionStates


class SubmissionCards(EventPermissionRequired, View):
    permission_required = "submission.orga_update_submission"

    def get_queryset(self):
        return (
            self.request.event.submissions.select_related("submission_type")
            .prefetch_related("speakers")
            .filter(
                state__in=[
                    SubmissionStates.ACCEPTED,
                    SubmissionStates.CONFIRMED,
                    SubmissionStates.SUBMITTED,
                ]
            )
        )

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not queryset.exists():
            messages.warning(request, _("You don’t seem to have any proposals yet."))
            return redirect(request.event.orga_urls.submissions)

        from pretalx.submission.cards import build_cards

        return build_cards(queryset, request.event)
