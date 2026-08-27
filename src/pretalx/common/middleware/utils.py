# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

UNAUTHENTICATED_ORGA_URLS = frozenset(
    (
        "invitation.view",
        "login",
        "logout",
        "auth.reset",
        "auth.recover",
        "auth.verify",
        "event.login",
        "event.auth.reset",
        "event.auth.recover",
        "event.auth.verify",
    )
)
