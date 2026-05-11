# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import string

from django.core.validators import RegexValidator
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from i18nfield.fields import I18nCharField

from pretalx.common.models.mixins import PretalxModel
from pretalx.common.text.phrases import phrases
from pretalx.common.urls import EventUrls, build_absolute_uri
from pretalx.event.models.event import FULL_SLUG_REGEX
from pretalx.event.rules import (
    can_change_any_organiser_settings,
    can_change_organiser_settings,
    can_change_teams,
    has_any_organiser_permissions,
    is_any_organiser,
)
from pretalx.person.models import User


class Organiser(PretalxModel):
    """The Organiser model represents the entity responsible for at least one.

    :class:`~pretalx.event.models.event.Event`.
    """

    name = I18nCharField(max_length=190, verbose_name=_("Name"))
    slug = models.SlugField(
        max_length=50,
        db_index=True,
        unique=True,
        validators=[
            RegexValidator(
                regex=FULL_SLUG_REGEX, message=phrases.base.slug_validator_message
            )
        ],
        verbose_name=_("Short form"),
        help_text=_(
            "Should be short, only contain lowercase letters and numbers, and must be unique, as it is used in URLs."
        ),
    )

    objects = models.Manager()

    class Meta:
        rules_permissions = {
            "view": has_any_organiser_permissions,
            "update": can_change_organiser_settings,
            "list": can_change_any_organiser_settings,
            "view_any": is_any_organiser,
        }

    def __str__(self) -> str:
        """Used in generated forms."""
        return str(self.name)

    class orga_urls(EventUrls):
        base = "/orga/organiser/{self.slug}/"
        settings = "{base}settings/"
        delete = "{settings}delete/"
        teams = "{base}teams/"
        new_team = "{teams}new/"
        user_search = "{base}api/users/"

    @cached_property
    def organiser(self):
        return self


TEAM_PERMISSIONS = {
    "list": can_change_teams,
    "view": can_change_teams,
    "create": can_change_teams,
    "update": can_change_teams,
    "delete": can_change_teams,
    "invite": can_change_teams,
    "delete_invite": can_change_teams,
    "remove_member": can_change_teams,
}


class Team(PretalxModel):
    """A team is a group of people working for the same organiser.

    Team members (of type :class:`~pretalx.person.models.user.User`) share
    permissions for one or several events of
    :class:`~pretalx.event.models.organiser.Organiser`.  People can be in
    multiple Teams, and will have all permissions *any* of their teams has.
    """

    organiser = models.ForeignKey(
        to=Organiser, related_name="teams", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=190, verbose_name=_("Team name"))
    members = models.ManyToManyField(
        to=User, related_name="teams", verbose_name=_("Team members")
    )
    all_events = models.BooleanField(
        default=False,
        verbose_name=_(
            "Apply permissions to all events by this organiser (including newly created ones)"
        ),
    )
    limit_events = models.ManyToManyField(
        to="Event", verbose_name=_("Limit permissions to these events"), blank=True
    )
    limit_tracks = models.ManyToManyField(
        to="submission.Track",
        verbose_name=_("Limit to tracks"),
        blank=True,
        related_name="limit_teams",
    )
    can_create_events = models.BooleanField(
        default=False, verbose_name=_("Can create events")
    )
    can_change_teams = models.BooleanField(
        default=False, verbose_name=_("Can change teams and permissions")
    )
    can_change_organiser_settings = models.BooleanField(
        default=False, verbose_name=_("Can change organiser settings")
    )
    can_change_event_settings = models.BooleanField(
        default=False, verbose_name=_("Can change event settings")
    )
    can_change_submissions = models.BooleanField(
        default=False, verbose_name=_("Can work with and change proposals")
    )
    is_reviewer = models.BooleanField(default=False, verbose_name=_("Is a reviewer"))
    force_hide_speaker_names = models.BooleanField(
        verbose_name=_("Always hide speaker names"),
        help_text=_(
            "Normally, anonymisation is configured in the event review settings. "
            "This setting will <strong>override the event settings</strong> and always hide speaker names for this team."
        ),
        default=False,
    )

    objects = models.Manager()

    class Meta:
        rules_permissions = TEAM_PERMISSIONS

    def __str__(self) -> str:
        """Help with debugging."""
        return _("{name} on {orga}").format(
            name=str(self.name), orga=str(self.organiser)
        )

    @cached_property
    def permission_set(self) -> set:
        """A set of all permissions this team has, as strings."""
        attribs = dir(self)
        return {
            attr
            for attr in attribs
            if attr.startswith(("can_", "is_")) and getattr(self, attr, False) is True
        }

    @cached_property
    def permission_set_display(self) -> set:
        """The same as :meth:`permission_set`, but with human-readable names."""
        return {
            getattr(self._meta.get_field(attr), "verbose_name", None) or attr
            for attr in self.permission_set
        }

    @cached_property
    def events(self):
        if self.all_events:
            return self.organiser.events.all()
        return self.limit_events.all()

    class orga_urls(EventUrls):
        base = "{self.organiser.orga_urls.teams}{self.pk}/"
        delete = "{base}delete/"


def generate_invite_token():
    return get_random_string(
        allowed_chars=string.ascii_lowercase + string.digits, length=32
    )


class TeamInvite(PretalxModel):
    """A TeamInvite is someone who has been invited to a team but hasn't accept
    the invitation yet."""

    team = models.ForeignKey(to=Team, related_name="invites", on_delete=models.CASCADE)
    email = models.EmailField(null=True, blank=True, verbose_name=_("Email"))
    token = models.CharField(
        default=generate_invite_token, max_length=64, null=True, blank=True, unique=True
    )

    objects = models.Manager()

    class Meta:
        rules_permissions = TEAM_PERMISSIONS

    def __str__(self) -> str:
        """Help with debugging."""
        return _("Invite to team {team} for {email}").format(
            team=str(self.team), email=self.email
        )

    @cached_property
    def organiser(self):
        return self.team.organiser

    @cached_property
    def invitation_url(self):
        return build_absolute_uri("orga:invitation.view", kwargs={"code": self.token})
