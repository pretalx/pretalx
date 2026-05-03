# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_resource_link_xor_file(*, link, resource):
    if link and resource:
        raise ValidationError(
            _("Please either provide a link or upload a file, you cannot do both!")
        )
    if not link and not resource:
        raise ValidationError(_("Please provide a link or upload a file!"))
