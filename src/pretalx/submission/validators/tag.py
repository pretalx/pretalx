# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.db.models import Value
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


def validate_unique_tag(tag):
    if not (tag.event_id and tag.tag):
        return
    duplicates = (
        tag.event.tags.exclude(pk=tag.pk)
        .annotate(lowered_tag=Lower("tag"))
        .filter(lowered_tag=Lower(Value(tag.tag)))
    )
    if duplicates.exists():
        raise ValidationError({"tag": _("You already have a tag by this name!")})
