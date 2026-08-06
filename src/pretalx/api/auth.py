# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django.utils.timezone import now
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication

from pretalx.person.models import UserApiToken


class UserTokenAuthentication(TokenAuthentication):
    model = UserApiToken

    def authenticate_credentials(self, key):
        model = self.get_model()
        try:
            token = (
                model.objects.active()
                .select_related("user")
                .prefetch_related("limit_events")
                .get(token=key)
            )
        except model.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid token.") from None

        timestamp = now()
        last_used_interval = dt.timedelta(minutes=1)
        if not token.last_used or token.last_used < timestamp - last_used_interval:
            token.last_used = timestamp
            token.save(update_fields=["last_used"])

        return token.user, token
