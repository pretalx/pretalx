# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_email_unique(email, *, exclude_user=None):
    """Raise ``ValidationError`` when ``email`` collides with another
    user's address (case-insensitive).

    ``exclude_user`` is for the editing case: an unchanged email would
    otherwise collide with the caller's own row.
    """
    from pretalx.person.models import User  # noqa: PLC0415 -- predicate

    qs = User.objects.all()
    if exclude_user is not None:
        qs = qs.exclude(pk=exclude_user.pk)
    if qs.filter(email__iexact=email).exists():
        raise ValidationError(
            {
                "email": _("There already exists an account for this email address.")
                + " "
                + _("Please choose a different email address.")
            }
        )
