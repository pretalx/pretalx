# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

# Note: When adding new submission filters here, also consider adding them
# to the ReviewFilter as submission__<filter_name> filters.

import django_filters
from django_scopes import scopes_disabled

from pretalx.submission.models import Submission, SubmissionStates

with scopes_disabled():

    class SubmissionFilter(django_filters.FilterSet):
        state = django_filters.MultipleChoiceFilter(
            choices=SubmissionStates.get_choices()
        )
        pending_state = django_filters.MultipleChoiceFilter(
            choices=SubmissionStates.get_choices()
        )

        class Meta:
            model = Submission
            fields = (
                "state",
                "pending_state",
                "content_locale",
                "submission_type",
                "track",
                "is_featured",
            )
