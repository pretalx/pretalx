# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import html
import random
import uuid
from contextlib import suppress

from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import OuterRef, Subquery
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override
from django_scopes import scopes_disabled
from rest_framework.authtoken.models import Token
from rules.contrib.models import RulesModelBase, RulesModelMixin

from pretalx.common.exceptions import UserDeletionError
from pretalx.common.models import TIMEZONE_CHOICES
from pretalx.common.models.mixins import FileCleanupMixin, GenerateCode, LogMixin
from pretalx.common.urls import EventUrls, build_absolute_uri
from pretalx.person.rules import is_administrator
from pretalx.person.signals import delete_user as delete_user_signal


class UserQuerySet(models.QuerySet):
    def with_profiles(self, event):
        from pretalx.person.models.profile import SpeakerProfile  # noqa: PLC0415

        return self.prefetch_related(
            models.Prefetch(
                "profiles",
                queryset=SpeakerProfile.objects.filter(event=event).select_related(
                    "event"
                ),
                to_attr="_speakers",
            ),
        ).distinct()

    def with_speaker_code(self, event):
        from pretalx.person.models.profile import SpeakerProfile  # noqa: PLC0415

        return self.annotate(
            speaker_code=Subquery(
                SpeakerProfile.objects.filter(
                    user_id=OuterRef("pk"),
                    event=event,
                    submissions__isnull=False,
                ).values("code")[:1]
            )
        )


class UserManager(BaseUserManager):
    """The user manager class."""

    def create_user(self, password=None, **kwargs):
        user = self.model(**kwargs)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, password: str, **kwargs):
        user = self.create_user(password=password, **kwargs)
        user.is_staff = True
        user.is_administrator = True
        user.is_superuser = False
        user.save(update_fields=["is_staff", "is_administrator", "is_superuser"])
        return user


def validate_username(value):
    from pretalx.common.templatetags.rich_text import render_markdown  # noqa: PLC0415

    result = render_markdown(value)[3:-4]  # strip <p> tags
    result = html.unescape(result)  # permit single <, > etc
    if result != value:
        raise ValidationError(_("Your username must not contain HTML or other markup."))


class User(
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
        unique=True,
        verbose_name=_("Email"),
        help_text=_(
            "Your email address will be used for password resets and notification about your event/proposals."
        ),
    )
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
        choices=[(tz, tz) for tz in TIMEZONE_CHOICES],
        max_length=32,
        default="UTC",
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
        rules_permissions = {
            "administrator": is_administrator,
        }

    def __str__(self) -> str:
        """For public consumption as it is used for Select widgets, e.g. on the
        feedback form."""
        return self.name or str(_("Unnamed user"))

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

    def save(self, *args, **kwargs):
        self.email = self.email.lower().strip()
        return super().save(*args, **kwargs)

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
        except Exception:
            from pretalx.person.models.profile import SpeakerProfile  # noqa: PLC0415

            speaker = SpeakerProfile(event=event, user=self)
            if self.pk:
                speaker.save()

        self.speaker_cache[event.pk] = speaker
        return speaker

    def get_event_preferences(self, event):
        if preferences := self.event_preferences_cache.get(event.pk):
            return preferences

        from pretalx.person.models.preferences import UserEventPreferences  # noqa: PLC0415

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

    def own_actions(self):
        """Returns all log entries that were made by this user.
        To get actions concerning this user, use logged_actions()."""
        from pretalx.common.models import ActivityLog  # noqa: PLC0415

        return ActivityLog.objects.filter(person=self)

    def _delete_files(self):
        for picture in self.pictures.all():
            picture.delete()
        return super()._delete_files()

    @transaction.atomic
    def deactivate(self):
        """Delete the user by unsetting all of their information."""
        from pretalx.submission.models import Answer  # noqa: PLC0415

        self.email = f"deleted_user_{random.randint(0, 999)}@localhost"
        while self.__class__.objects.filter(
            email__iexact=self.email
        ).exists():  # pragma: no cover
            self.email = f"deleted_user_{random.randint(0, 99999)}"
        self.name = "Deleted User"
        self.is_active = False
        self.is_superuser = False
        self.is_administrator = False
        self.locale = "en"
        self.timezone = "UTC"
        self.pw_reset_token = None
        self.pw_reset_time = None
        self.set_unusable_password()
        self._delete_files()
        self.save()
        self.profiles.all().update(biography="")
        for answer in Answer.objects.filter(
            models.Q(speaker__user=self) | models.Q(submission__speakers__user=self),
            question__contains_personal_data=True,
        ).distinct():
            answer.delete()  # Iterate to delete answer files, too
        for team in self.teams.all():
            team.members.remove(self)
        delete_user_signal.send(None, user=self, db_delete=True)

    deactivate.alters_data = True

    @transaction.atomic
    def shred(self):
        """Actually remove the user account."""
        from pretalx.submission.models import Answer, Submission  # noqa: PLC0415

        with scopes_disabled():
            if (
                Submission.all_objects.filter(speakers__user=self).count()
                or self.teams.count()
                or Answer.objects.filter(
                    models.Q(speaker__user=self)
                    | models.Q(submission__speakers__user=self)
                )
                .distinct()
                .count()
            ):
                raise UserDeletionError(
                    f"Cannot delete user <{self.email}> because they have submissions, answers, or teams. Please deactivate this user instead."
                )
            self.logged_actions().delete()
            self.own_actions().update(person=None)
            self._delete_files()
            delete_user_signal.send(None, user=self, db_delete=True)
            self.delete()

    shred.alters_data = True

    @cached_property
    def guid(self) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"acct:{self.email.strip()}"))

    def get_events_with_any_permission(self):
        """Returns a queryset of events for which this user has any type of
        permission."""
        from pretalx.event.models import Event  # noqa: PLC0415

        if self.is_administrator:
            return Event.objects.all()

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
        from pretalx.event.models import Event  # noqa: PLC0415

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
        if self.is_administrator:
            self.event_permission_cache[event.pk] = {
                "permissions": {
                    "can_create_events",
                    "can_change_teams",
                    "can_change_organiser_settings",
                    "can_change_event_settings",
                    "can_change_submissions",
                    "is_reviewer",
                },
                "reviewer_tracks": None,
                "reviewer_team_pks": [],
            }
            return self.event_permission_cache[event.pk]["permissions"]
        permissions = set()
        teams = event.teams.filter(members__in=[self])
        reviewer_team_pks = []
        for team in teams:
            permissions |= team.permission_set
            if team.is_reviewer:
                reviewer_team_pks.append(team.pk)
        entry = {"permissions": permissions, "reviewer_team_pks": reviewer_team_pks}
        if cached is not None:
            cached.update(entry)
        else:
            self.event_permission_cache[event.pk] = entry
        return permissions

    def get_reviewer_tracks(self, event):
        """Returns None for unrestricted reviewer access, or a frozenset of
        Track objects. Lazily computed on first access and cached in
        event_permission_cache."""
        cached = self.event_permission_cache.get(event.pk)
        if cached and "reviewer_tracks" in cached:
            return cached["reviewer_tracks"]
        self.get_permissions_for_event(event)
        cached = self.event_permission_cache[event.pk]
        reviewer_team_pks = cached["reviewer_team_pks"]
        if not reviewer_team_pks:
            cached["reviewer_tracks"] = frozenset()
            return cached["reviewer_tracks"]
        tracks = frozenset(
            event.tracks.filter(limit_teams__in=reviewer_team_pks).distinct()
        )
        cached["reviewer_tracks"] = tracks or None
        return cached["reviewer_tracks"]

    def regenerate_token(self) -> Token:
        """Generates a new API access token, deleting the old one."""
        self.log_action(action="pretalx.user.token.reset")
        Token.objects.filter(user=self).delete()
        return Token.objects.create(user=self)

    regenerate_token.alters_data = True

    def get_password_reset_url(self, event=None, orga=False):
        if event:
            path = "orga:event.auth.recover" if orga else "cfp:event.recover"
            kwargs = {"token": self.pw_reset_token, "event": event.slug}
        else:
            path = "orga:auth.recover"
            kwargs = {"token": self.pw_reset_token}
        return build_absolute_uri(path, kwargs=kwargs)

    @transaction.atomic
    def reset_password(self, event, user=None, mail_text=None, orga=False):
        from pretalx.mail.models import QueuedMail  # noqa: PLC0415

        self.pw_reset_token = get_random_string(32)
        self.pw_reset_time = now()
        self.save()

        context = {
            "name": self.name or "",
            "url": self.get_password_reset_url(event=event, orga=orga),
        }
        if not mail_text:
            mail_text = _("""Hi {name},

you have requested a new password for your pretalx account.
To reset your password, click on the following link:

  {url}

If this wasn’t you, you can just ignore this email.

All the best,
the pretalx robot""")

        with override(self.locale):
            QueuedMail(
                subject=_("Password recovery"),
                text=str(mail_text).format(**context),
                locale=self.locale,
                to=self.email,
            ).send()
        self.log_action(
            action="pretalx.user.password.reset", person=user, orga=bool(user)
        )

    reset_password.alters_data = True

    class orga_urls(EventUrls):
        admin = "/orga/admin/users/{self.code}/"

    @transaction.atomic
    def change_password(self, new_password):
        from pretalx.mail.models import QueuedMail  # noqa: PLC0415

        self.set_password(new_password)
        self.pw_reset_token = None
        self.pw_reset_time = None
        self.save()

        context = {
            "name": self.name or "",
        }
        mail_text = _("""Hi {name},

Your pretalx account password was just changed.

If you did not change your password, please contact the site administration immediately.

All the best,
the pretalx team""")

        with override(self.locale):
            QueuedMail(
                subject=_("[pretalx] Password changed"),
                text=str(mail_text).format(**context),
                locale=self.locale,
                to=self.email,
            ).send()

        self.log_action(action="pretalx.user.password.changed", person=self)

    change_password.alters_data = True

    @transaction.atomic
    def change_email(self, new_email):
        from pretalx.mail.models import QueuedMail  # noqa: PLC0415

        old_email = self.email
        self.email = new_email.lower().strip()
        self.save(update_fields=["email"])

        context = {
            "name": self.name or "",
            "old_email": old_email,
            "new_email": self.email,
        }
        mail_text = _("""Hi {name},

This is a confirmation that the email address for your pretalx account has been changed from {old_email} to {new_email}.

If you did not perform this change, please contact an administrator immediately.

All the best,
the pretalx team""")

        with override(self.locale):
            QueuedMail(
                subject=_("[pretalx] Email address changed"),
                text=str(mail_text).format(**context),
                to=old_email,
                locale=self.locale,
            ).send()

        self.log_action(
            action="pretalx.user.email.update",
            person=self,
            orga=False,
            data={"old_email": old_email, "new_email": self.email},
        )

    change_email.alters_data = True
