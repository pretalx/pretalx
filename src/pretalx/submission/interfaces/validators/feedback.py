# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_speaker_on_talk(talk, speaker):
    if talk and speaker and not talk.speakers.filter(pk=speaker.pk).exists():
        raise ValidationError(
            {"speaker": _("This speaker is not a speaker of the given submission.")}
        )
