# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_filters
from django_scopes import scopes_disabled

from pretalx.submission.models import Feedback, Submission
from pretalx.submission.rules import submissions_for_user

with scopes_disabled():

    class FeedbackFilter(django_filters.FilterSet):
        submission = django_filters.ModelChoiceFilter(
            queryset=Submission.objects.none(),
            field_name="talk",
            to_field_name="code",
            help_text="Filter by submission code",
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            request = kwargs.get("request")
            event = getattr(request, "event", None)
            user = getattr(request, "user", None)
            self.filters["submission"].queryset = submissions_for_user(event, user)

        class Meta:
            model = Feedback
            fields = ("submission",)
