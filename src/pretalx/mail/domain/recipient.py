# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.person.models import SpeakerProfile


class Recipient:
    """Wraps a SpeakerProfile or a User as a mail recipient."""

    def __init__(self, speaker_or_user):
        if isinstance(speaker_or_user, Recipient):
            self._speaker = speaker_or_user._speaker  # noqa: SLF001 -- same-class copy
            self.user = speaker_or_user.user
        elif isinstance(speaker_or_user, SpeakerProfile):
            self._speaker = speaker_or_user
            self.user = speaker_or_user.user
        else:
            self._speaker = None
            self.user = speaker_or_user

    def __repr__(self):
        return f"Recipient({self._speaker or self.user!r})"

    def __eq__(self, other):
        return (
            isinstance(other, Recipient)
            and self._speaker == other._speaker
            and self.user == other.user
        )

    def __hash__(self):
        return hash((self._speaker, self.user))

    @property
    def email(self) -> str | None:
        if self._speaker:
            return self._speaker.effective_email
        return self.user.email

    @property
    def name(self) -> str:
        return self.get_display_name(allow_empty=True)

    def get_display_name(self, event=None, allow_empty=False) -> str:
        speaker = self._speaker
        if speaker is None and event is not None:
            speaker = self.user.get_speaker(event, create=False)
        return (speaker or self.user).get_display_name(allow_empty=allow_empty)

    @property
    def locale(self) -> str | None:
        if self._speaker:
            return self._speaker.effective_locale
        return self.user.locale

    def get_locale_for_event(self, event) -> str:
        if self._speaker:
            return self._speaker.effective_locale
        return self.user.get_locale_for_event(event)

    def speaker(self, event):
        """The wrapped or derived :class:`SpeakerProfile` for ``event``,
        or ``None``."""
        if self._speaker:
            return self._speaker if self._speaker.event_id == event.pk else None
        if self.user:
            return self.user.get_speaker(event, create=False)
        return None


def recipient_speaker(user, event):
    return Recipient(user).speaker(event)


def recipient_account(user):
    return Recipient(user).user
