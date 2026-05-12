# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.api.versions import CURRENT_VERSION


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


def upgrade_token(token):
    with scopes_disabled():
        token.version = CURRENT_VERSION
        token.save(update_fields=["version"])
        token.user.log_action("pretalx.user.token.upgrade", data=token.serialize())


def revoke_token(token):
    with scopes_disabled():
        token.expires = now()
        token.save(update_fields=["expires"])
        token.user.log_action("pretalx.user.token.revoke", data=token.serialize())
