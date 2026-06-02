# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from pretalx.submission.enums import QuestionRequired


def validate_question_deadline(question):
    """``question_required=AFTER_DEADLINE`` requires a ``deadline`` to be set;
    the ``required`` property crashes otherwise.
    """
    if (
        question.question_required == QuestionRequired.AFTER_DEADLINE
        and not question.deadline
    ):
        raise ValidationError(
            {
                "deadline": _(
                    "Please select a deadline after which the field should "
                    "become mandatory."
                )
            }
        )


def _validate_identifier_unique(*, qs, identifier, instance, message):
    """Case-insensitive uniqueness within a given queryset.

    The model-level ``unique_together`` constraint is case-sensitive;
    this is stricter to avoid identifiers that differ only in case.
    """
    if not identifier:
        return
    qs = qs.filter(identifier__iexact=identifier)
    if instance and not instance._state.adding:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        raise ValidationError({"identifier": message})


def validate_question_identifier_unique(*, event, identifier, instance=None):
    _validate_identifier_unique(
        qs=event.questions(manager="all_objects"),
        identifier=identifier,
        instance=instance,
        message=_("This identifier is already used for a different question."),
    )


def validate_answer_option_identifier_unique(*, question, identifier, instance=None):
    _validate_identifier_unique(
        qs=question.options.all(),
        identifier=identifier,
        instance=instance,
        message=_("This identifier is already used for a different option."),
    )
