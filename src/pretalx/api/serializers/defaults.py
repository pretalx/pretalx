# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

"""
Context-aware defaults for ``HiddenField``, mirroring DRF’s built-in
``CurrentUserDefault``, Used so that scoped fields (event, organiser,
…) are present from ``validated_data`` onwards, populated from the URL.
"""


class CurrentEventDefault:
    """``HiddenField`` default that resolves to ``request.event``."""

    requires_context = True

    def __call__(self, serializer_field):
        return getattr(serializer_field.context.get("request"), "event", None)

    def __repr__(self):
        return f"{self.__class__.__name__}()"


class CurrentOrganiserDefault:
    """``HiddenField`` default that resolves to ``request.organiser``."""

    requires_context = True

    def __call__(self, serializer_field):
        return getattr(serializer_field.context.get("request"), "organiser", None)

    def __repr__(self):
        return f"{self.__class__.__name__}()"
