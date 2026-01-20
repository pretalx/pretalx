# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_filters
from django_scopes import scopes_disabled

from pretalx.person.models import User
from pretalx.submission.models import (
    Review,
    Submission,
    SubmissionStates,
    SubmissionType,
    Track,
)

with scopes_disabled():

    class ReviewFilter(django_filters.FilterSet):
        submission = django_filters.ModelChoiceFilter(
            queryset=Submission.objects.none(),
            field_name="submission",
            to_field_name="code",
            help_text="Filter by submission code",
        )
        user = django_filters.ModelChoiceFilter(
            queryset=User.objects.none(),
            field_name="user",
            to_field_name="code",
            help_text="Filter by reviewer code",
        )
        speaker = django_filters.ModelChoiceFilter(
            queryset=User.objects.none(),
            field_name="submission__speakers",
            to_field_name="code",
            help_text="Filter by speaker code (for the submission being reviewed)",
        )
        submission__state = django_filters.MultipleChoiceFilter(
            choices=SubmissionStates.get_choices(),
            field_name="submission__state",
            help_text="Filter by submission state",
        )
        submission__pending_state = django_filters.MultipleChoiceFilter(
            choices=SubmissionStates.get_choices(),
            field_name="submission__pending_state",
            help_text="Filter by submission pending state",
        )
        submission__track = django_filters.ModelChoiceFilter(
            queryset=Track.objects.none(),
            field_name="submission__track",
            help_text="Filter by submission track",
        )
        submission__submission_type = django_filters.ModelChoiceFilter(
            queryset=SubmissionType.objects.none(),
            field_name="submission__submission_type",
            help_text="Filter by submission type",
        )
        submission__content_locale = django_filters.CharFilter(
            field_name="submission__content_locale",
            help_text="Filter by submission content locale",
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            event = getattr(kwargs.get("request"), "event", None)
            if event:
                submissions = event.submissions.all()
                self.filters["submission"].queryset = submissions
                self.filters["user"].queryset = event.reviewers.all()
                self.filters["speaker"].queryset = User.objects.filter(
                    submissions__in=submissions
                )
                self.filters["submission__track"].queryset = event.tracks.all()
                self.filters["submission__submission_type"].queryset = (
                    event.submission_types.all()
                )

        class Meta:
            model = Review
            fields = (
                "submission",
                "user",
                "speaker",
                "submission__state",
                "submission__pending_state",
                "submission__track",
                "submission__submission_type",
                "submission__content_locale",
            )
