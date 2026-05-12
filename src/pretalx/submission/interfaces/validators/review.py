# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_review_scores_present(event, scores):
    if event.review_settings.get("score_mandatory") and len(scores) == 0:
        raise ValidationError(_("Please provide at least one review score!"))


def validate_review_scores_unique_categories(scores):
    if len(scores) != len({s.category_id for s in scores}):
        raise ValidationError(_("You can only assign one score per category!"))


def validate_non_independent_category_remains(category):
    if (
        not category.event.score_categories.exclude(pk=category.pk)
        .filter(is_independent=False)
        .exists()
    ):
        raise ValidationError(
            _("You need to keep at least one non-independent score category!")
        )
