# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import html
from contextlib import suppress

from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from rules.contrib.models import RulesModelBase, RulesModelMixin

from pretalx.common.models import TIMEZONE_CHOICES
from pretalx.common.models.mixins import FileCleanupMixin, GenerateCode, LogMixin
from pretalx.common.urls import EventUrls
from pretalx.event.models import Event
from pretalx.person.models.picture import ProfilePictureMixin
from pretalx.person.models.preferences import UserEventPreferences
from pretalx.person.models.profile import SpeakerProfile
from pretalx.person.rules import is_administrator
from pretalx.person.validators import validate_email_unique


class UserQuerySet(models.QuerySet):
    def with_profiles(self, event):
        from pretalx.person.domain.queries.user import (  # noqa: PLC0415 -- thin method
            with_profiles,
        )

        return with_profiles(self, event)

    def with_speaker_code(self, event):
        from pretalx.person.domain.queries.user import (  # noqa: PLC0415 -- thin method
            with_speaker_code,
        )

        return with_speaker_code(self, event)


class UserManager(BaseUserManager):
    """The user manager class."""

    def create_user(self, password=None, **kwargs):
        from pretalx.person.domain.user import (  # noqa: PLC0415 -- thin method
            create_user,
        )

        return create_user(password=password, **kwargs)

    def create_superuser(self, password: str, **kwargs):
        user = self.create_user(password=password, **kwargs)
        user.is_staff = True
        user.is_administrator = True
        user.is_superuser = False
        user.save(update_fields=["is_staff", "is_administrator", "is_superuser"])
        return user


def validate_username(value):
    from pretalx.common.templatetags.rich_text import (  # noqa: PLC0415 -- thin method
        render_markdown,
    )

    result = render_markdown(value)[3:-4]  # strip <p> tags
    result = html.unescape(result)  # permit single <, > etc
    if result != value:
        raise ValidationError(_("Your username must not contain HTML or other markup."))


class User(
    ProfilePictureMixin,
    PermissionsMixin,
    RulesModelMixin,
    GenerateCode,
    LogMixin,
    FileCleanupMixin,
    AbstractBaseUser,
    metaclass=RulesModelBase,
):
    """The pretalx user model.

    Users describe all kinds of persons who interact with pretalx: Organisers, reviewers, submitters, speakers.

    :param code: A user's alphanumeric code is auto generated, may not be
        changed, and is the unique identifier of that user.
    :param name: A name fit for public display. Will be used in the user
        interface and for public display for all speakers in all of their
        events.
    :param password: The password is stored using Django's PasswordField. Use
        the ``set_password`` and ``check_password`` methods to interact with it.
    :param nick: The nickname field has been deprecated and is scheduled to be
        deleted. Use the email field instead.
    :param groups: Django internals, not used in pretalx.
    :param user_permissions: Django internals, not used in pretalx.
    """

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"

    objects = UserManager().from_queryset(UserQuerySet)()

    code = models.CharField(max_length=16, unique=True, null=True)
    nick = models.CharField(max_length=60, null=True, blank=True)
    name = models.CharField(
        max_length=120,
        verbose_name=_("Name"),
        help_text=_(
            "Please enter the name you wish to be displayed publicly. This name will be used for all events you are participating in on this server."
        ),
        validators=[validate_username],
    )
    email = models.EmailField(
        # We set unique=True to silence Django's warnings, as it does not recognise
        # UniqueConstraint(Lower(...)) as enforcing uniqueness.
        unique=True,
        verbose_name=_("Email"),
        help_text=_(
            "Your email address will be used for password resets and notification about your event/proposals."
        ),
    )
    created = models.DateTimeField(verbose_name=_("Created"), auto_now_add=True)
    is_active = models.BooleanField(
        default=True, help_text="Inactive users are not allowed to log in."
    )
    is_staff = models.BooleanField(
        default=False, help_text="A default Django flag. Not in use in pretalx."
    )
    is_administrator = models.BooleanField(
        default=False,
        help_text="Should only be ``True`` for people with administrative access to the server pretalx runs on.",
    )
    is_superuser = models.BooleanField(
        default=False,
        help_text="Never set this flag to ``True``, since it short-circuits all authorisation mechanisms.",
    )
    locale = models.CharField(
        max_length=32,
        default=settings.LANGUAGE_CODE,
        choices=settings.LANGUAGES,
        verbose_name=_("Preferred language"),
    )
    timezone = models.CharField(
        choices=[(tz, tz) for tz in TIMEZONE_CHOICES], max_length=32, default="UTC"
    )
    profile_picture = models.ForeignKey(
        "person.ProfilePicture",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )
    pw_reset_token = models.CharField(
        null=True, max_length=160, verbose_name="Password reset token"
    )
    pw_reset_time = models.DateTimeField(null=True, verbose_name="Password reset time")

    class Meta:
        rules_permissions = {"administrator": is_administrator}
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="person_user_email_unique_ci",
                violation_error_message=_("Please choose a different email address."),
            )
        ]

    def __str__(self) -> str:
        """For public consumption as it is used for Select widgets, e.g. on the
        feedback form."""
        return self.name or str(_("Unnamed user"))

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.email.lower().strip()
        validate_email_unique(
            self.email, exclude_user=None if self._state.adding else self
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.permission_cache = {}
        self.speaker_cache = {}
        self.event_permission_cache = {}
        self.event_preferences_cache = {}

    def has_perm(self, perm, obj, *args, **kwargs):
        cached_result = None
        if not getattr(obj, "pk", None):
            return super().has_perm(perm, obj, *args, **kwargs)
        with suppress(TypeError):
            cached_result = self.permission_cache.get((perm, obj))
        if cached_result is not None:
            return cached_result
        result = super().has_perm(perm, obj, *args, **kwargs)
        self.permission_cache[(perm, obj)] = result
        return result

    def get_display_name(self) -> str:
        """Returns a user's name or 'Unnamed user'."""
        return str(self)

    def get_speaker(self, event):
        """Retrieve (and/or create) the event.

        :class:`~pretalx.person.models.profile.SpeakerProfile` for this user.

        :type event: :class:`pretalx.event.models.event.Event`
        :retval: :class:`~pretalx.person.models.profile.EventProfile`
        """
        if speaker := self.speaker_cache.get(event.pk):
            return speaker

        if hasattr(self, "_speakers") and len(self._speakers) == 1:
            speaker = self._speakers[0]
            if speaker.event_id == event.pk:
                self.speaker_cache[event.pk] = speaker
                return speaker

        try:
            speaker = self.profiles.select_related("event", "profile_picture").get(
                event=event
            )
        except ObjectDoesNotExist:
            speaker = SpeakerProfile(event=event, user=self, name=self.name)
            speaker.save()

        self.speaker_cache[event.pk] = speaker
        return speaker

    def get_event_preferences(self, event):
        if preferences := self.event_preferences_cache.get(event.pk):
            return preferences

        preferences, _ = UserEventPreferences.objects.get_or_create(
            event=event, user=self
        )
        self.event_preferences_cache[event.pk] = preferences
        return preferences

    def get_locale_for_event(self, event):
        if self.locale in event.locales:
            return self.locale
        return event.locale

    def log_action(self, action, person=None, content_object=None, **kwargs):
        return super().log_action(
            action=action,
            person=person or self,
            content_object=content_object or self,
            **kwargs,
        )

    def delete_files(self):
        for picture in self.pictures.all():
            picture.delete()
        return super().delete_files()

    def get_events_with_any_permission(self):
        """Returns a queryset of events for which this user has any type of
        permission."""
        if self.is_administrator:
            return Event.objects.all()

        if "teams" in getattr(self, "_prefetched_objects_cache", {}):
            events = {}
            for team in self.teams.all():
                if team.all_events:
                    for event in team.organiser.events.all():
                        events[event.pk] = event
                else:
                    for event in team.limit_events.all():
                        events[event.pk] = event
            return events.values()

        return Event.objects.filter(
            models.Q(
                organiser_id__in=self.teams.filter(all_events=True).values_list(
                    "organiser", flat=True
                )
            )
            | models.Q(id__in=self.teams.values_list("limit_events__id", flat=True))
        )

    def get_events_for_permission(self, **kwargs):
        """Returns a queryset of events for which this user as all of the given
        permissions.

        Permissions are given as named arguments, e.g.
        ``get_events_for_permission(is_reviewer=True)``.
        """
        if self.is_administrator:
            return Event.objects.all()

        orga_teams = self.teams.filter(**kwargs)
        absolute = orga_teams.filter(all_events=True).values_list(
            "organiser", flat=True
        )
        relative = orga_teams.filter(all_events=False).values_list(
            "limit_events", flat=True
        )
        return Event.objects.filter(
            models.Q(organiser__in=absolute) | models.Q(pk__in=relative)
        ).distinct()

    def get_permissions_for_event(self, event) -> set:
        """Returns a set of all permission a user has for the given event.

        :type event: :class:`~pretalx.event.models.event.Event`
        """
        cached = self.event_permission_cache.get(event.pk)
        if cached and "permissions" in cached:
            return cached["permissions"]
        permissions = set()
        if self.is_administrator:
            permissions = {
                "can_create_events",
                "can_change_teams",
                "can_change_organiser_settings",
                "can_change_event_settings",
                "can_change_submissions",
                # No reviewer permissions; even admins should not be
                # able to review proposals without explicit perms.
            }
        teams = event.teams.filter(members__in=[self]).annotate(
            limit_track_count=models.Count("limit_tracks")
        )
        reviewer_team_pks = set()
        for team in teams:
            permissions |= team.permission_set
            if not team.is_reviewer or "__all__" in reviewer_team_pks:
                continue
            if team.limit_track_count == 0:
                # Blanket reviewer team: bypass any track restrictions.
                # Sentinel is resolved lazily in get_reviewer_tracks.
                reviewer_team_pks = {"__all__"}
            else:
                reviewer_team_pks.add(team.pk)
        self.event_permission_cache[event.pk] = {
            "permissions": permissions,
            "reviewer_team_pks": reviewer_team_pks,
        }
        return permissions

    def get_reviewer_tracks(self, event):
        """Return this user's reviewer track restriction for ``event``,
        as a frozenset of pks, or None if all tracks are accessible."""
        permissions = self.get_permissions_for_event(event)
        if "is_reviewer" not in permissions:
            raise ValueError(f"User {self.pk} is not a reviewer for event {event.pk}")
        cached = self.event_permission_cache[event.pk]
        if "reviewer_tracks" in cached:
            return cached["reviewer_tracks"]
        reviewer_team_pks = cached["reviewer_team_pks"]
        if "__all__" in reviewer_team_pks:
            reviewer_tracks = None
        else:
            reviewer_tracks = frozenset(
                event.tracks.filter(limit_teams__in=reviewer_team_pks).values_list(
                    "pk", flat=True
                )
            )
        cached["reviewer_tracks"] = reviewer_tracks
        return reviewer_tracks

    class orga_urls(EventUrls):
        admin = "/orga/admin/users/{self.code}/"
