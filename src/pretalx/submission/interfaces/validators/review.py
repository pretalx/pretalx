# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_non_independent_category_remains(category):
    """An event must keep at least one non-independent score category.

    Called when flipping an existing category to independent or deleting a
    non-independent one — independent categories don't contribute to the
    total score, so removing the last "real" one would leave the event
    unable to rank submissions.
    """
    if (
        not category.event.score_categories.exclude(pk=category.pk)
        .filter(is_independent=False)
        .exists()
    ):
        raise ValidationError(
            _("You need to keep at least one non-independent score category!")
        )
