# SPDX-FileCopyrightText: 2025-present Florian Moesch
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_filters
from django_scopes import scopes_disabled

from pretalx.person.models import User
from pretalx.submission.models import Feedback, Submission

with scopes_disabled():

    class FeedbackFilter(django_filters.FilterSet):
        talk = django_filters.ModelChoiceFilter(
            queryset=Submission.objects.none(),
            field_name="talk",
            to_field_name="code",
            help_text="Filter by talk code",
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            event = getattr(kwargs.get("request"), "event", None)
            if event:
                self.filters["talk"].queryset = event.talks.all()

        class Meta:
            model = Feedback
            fields = (
                "talk",
            )
