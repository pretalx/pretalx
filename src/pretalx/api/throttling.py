# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle


class AuthenticatedRateThrottle(SimpleRateThrottle):
    scope = "user"

    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope) or None

    def get_cache_key(self, request, view):
        if not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}
