# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication

from pretalx.person.models import UserApiToken


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


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
            raise exceptions.AuthenticationFailed("Invalid token.") from None

        return token.user, token
