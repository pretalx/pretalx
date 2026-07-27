# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from pretalx.submission.enums import QuestionRequired, QuestionVariant


def get_option_count_help_text(text, min_number, max_number):
    if not min_number and not max_number:
        return text
    text = str(text) + " " if text else ""
    if min_number and max_number:
        if min_number == max_number:
            message = _("Please select exactly {count} options.").format(
                count=min_number
            )
        else:
            message = _("Please select between {min} and {max} options.").format(
                min=min_number, max=max_number
            )
    elif min_number:
        message = _("Please select at least {min} options.").format(min=min_number)
    else:
        message = _("Please select at most {max} options.").format(max=max_number)
    return (text + str(message)).strip()


def validate_option_count(value, min_number, max_number):
    count = len(set(value)) if value else 0
    if (min_number and min_number > count) or (max_number and max_number < count):
        error_message = get_option_count_help_text("", min_number, max_number)
        error_message += " " + str(_("You selected {count} options.")).format(
            count=count
        )
        raise ValidationError(error_message)


def validate_question_option_limits(question):
    if (
        question.min_options
        and question.max_options
        and question.min_options > question.max_options
    ):
        raise ValidationError(
            {
                "min_options": _(
                    "Minimum number of options cannot be greater than maximum "
                    "number of options."
                )
            }
        )


def validate_question_min_options_available(question, option_count=None):
    if not question.min_options or question.variant != QuestionVariant.MULTIPLE:
        return
    if option_count is None:
        # option_count may be passed in explicitly in order to check if a new
        # option count is valid before committing it.
        option_count = question.options.count() if question.pk else 0
    if option_count and question.min_options > option_count:
        raise ValidationError(
            {
                "min_options": _(
                    "This custom field only has {count} options, so it cannot "
                    "require {min} of them."
                ).format(count=option_count, min=question.min_options)
            }
        )


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
