# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.timezone import now


def update_token_events(token):
    """Drop events the token's user can no longer reach; expire the token if
    nothing remains. Called when a user loses team access."""
    permitted = set(token.user.get_events_with_any_permission())
    to_remove = set(token.events.all()) - permitted
    if not to_remove:
        return
    token.events.remove(*to_remove)
    if not token.events.exists():
        token.expires = now()
        token.save(update_fields=["expires"])
