# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

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
                .prefetch_related("events")
                .get(token=key)
            )
        except model.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid token.")

        if not token.is_active:
            raise exceptions.AuthenticationFailed("Token inactive or deleted.")

        return token.user, token
