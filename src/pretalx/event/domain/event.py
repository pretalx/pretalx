# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms


def create_event(*, organiser, locales, **fields):
    """Create an :class:`Event` for ``organiser``.

    ``locales`` is a sequence of language codes; it populates both
    ``locale_array`` and ``content_locale_array``. All other model
    fields are passed through verbatim. ``Event.clean`` is invoked
    explicitly so the slug is normalised and uniqueness is enforced
    even on programmatic callers that bypass form validation —
    mirroring :func:`pretalx.person.domain.user.create_user`.
    """
    locale_array = ",".join(locales)
    event = organiser.events.model(
        organiser=organiser,
        locale_array=locale_array,
        content_locale_array=locale_array,
        **fields,
    )
    event.clean()
    event.save()
    return event
