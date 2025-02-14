import string

from django.db import models
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _

from pretalx.common.models.mixins import PretalxModel
from pretalx.event.models import Team
from pretalx.person.models import User


def generate_api_token():
    return get_random_string(
        length=64, allowed_chars=string.ascii_lowercase + string.digits
    )


class UserApiToken(PretalxModel):
    name = models.CharField(max_length=190, verbose_name=_("Name"))
    token = models.CharField(default=generate_api_token, max_length=64)
    user = models.ForeignKey(
        to=User,
        related_name="api_tokens",
        on_delete=models.CASCADE,
    )
    # TODO: make sure the token is deactivated if the user is removed from the team
    # TODO: show that users have active tokens in team list
    team = models.ForeignKey(
        to=Team,
        related_name="api_tokens",
        on_delete=models.CASCADE,
        verbose_name=_("Team"),
    )
    # TODO: make sure we check token.expires before allowing access
    expires = models.DateTimeField(null=True, blank=True, verbose_name=_("Expiry date"))
    # TODO document field structure
    endpoints = models.JSONField(default=dict, blank=True)
    version = models.CharField(
        max_length=12, null=True, blank=True, verbose_name=_("API version")
    )
