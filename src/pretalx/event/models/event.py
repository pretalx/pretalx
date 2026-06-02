# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import copy
import datetime as dt
import zoneinfo

from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned, ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils.functional import cached_property
from django.utils.timezone import make_aware
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager
from i18nfield.fields import I18nCharField, I18nTextField

from pretalx.common.cache import ObjectRelatedCache
from pretalx.common.language import LANGUAGE_NAMES
from pretalx.common.models import TIMEZONE_CHOICES
from pretalx.common.models.fields import DateField
from pretalx.common.models.mixins import OrderedModel, PretalxModel
from pretalx.common.models.settings import hierarkey
from pretalx.common.plugins import get_all_plugins
from pretalx.common.signals import register_locales
from pretalx.common.text.daterange import daterange
from pretalx.common.text.path import hashed_path
from pretalx.common.text.phrases import phrases
from pretalx.common.ui import has_good_contrast
from pretalx.common.urls import EventUrls
from pretalx.event.rules import (
    can_change_event_settings,
    can_create_events,
    has_any_permission,
    is_event_visible,
)
from pretalx.event.validators.event import (
    validate_attendee_signup_settings,
    validate_event_slug_unique,
    validate_feature_flags,
)
from pretalx.mail.enums import QueuedMailStates
from pretalx.schedule.models import TalkSlot
from pretalx.submission.models import Review

# Slugs need to start and end with an alphanumeric character,
# but may contain dashes and dots in between.
SLUG_CHARS = "a-zA-Z0-9.-"
SLUG_REGEX = rf"[a-zA-Z0-9]([{SLUG_CHARS}]*[a-zA-Z0-9])?"
FULL_SLUG_REGEX = rf"^{SLUG_REGEX}$"


def validate_event_slug_permitted(value):
    forbidden = [
        "_global",
        "__debug__",
        "api",
        "csp_report",
        "events",
        "download",
        "healthcheck",
        "jsi18n",
        "locale",
        "metrics",
        "orga",
        "redirect",
        "relay",
        "widget",
        "400",
        "403",
        "404",
        "500",
        "p",
    ]
    if value.lower() in forbidden:
        raise ValidationError(
            _("Invalid event slug – this slug is reserved: {value}.").format(
                value=value
            ),
            code="invalid",
            params={"value": value},
        )


def event_css_path(instance, filename):
    return hashed_path(
        filename, target_name="custom", upload_dir=f"{instance.slug}/css/"
    )


def event_logo_path(instance, filename):
    return hashed_path(filename, target_name="logo", upload_dir=f"{instance.slug}/img/")


def event_header_path(instance, filename):
    return hashed_path(
        filename, target_name="header", upload_dir=f"{instance.slug}/img/"
    )


def event_og_path(instance, filename):
    return hashed_path(filename, target_name="og", upload_dir=f"{instance.slug}/img/")


def default_feature_flags():
    return {
        "show_schedule": True,
        "show_featured": "pre_schedule",  # or always, or never
        "show_widget_if_not_public": False,
        "use_tracks": True,
        "use_feedback": True,
        "use_submission_comments": True,
        "present_multiple_times": False,
        "submission_public_review": True,
        "speakers_can_edit_submissions": True,
        "attendee_signup": False,
    }


def default_display_settings():
    return {
        "schedule": "grid",  # or list
        "imprint_url": None,
        "header_pattern": "",
        "html_export_url": "",
        "meta_noindex": False,
        "heading_font": "",
        "text_font": "",
        "texts": {"agenda_session_above": "", "agenda_session_below": ""},
    }


def default_review_settings():
    return {
        "score_mandatory": False,
        "text_mandatory": False,
        "aggregate_method": "median",  # or mean
        "score_format": "words_numbers",
    }


def default_mail_settings():
    return {
        "mail_from": "",
        "reply_to": "",
        "signature": "",
        "subject_prefix": "",
        "smtp_use_custom": "",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_username": "",
        "smtp_password": "",
        "smtp_use_tls": "",
        "smtp_use_ssl": "",
        "mail_on_new_submission": False,
    }


def default_attendee_signup_settings():
    return {"signup_domains": []}


@hierarkey.add()
class Event(PretalxModel):
    """The Event class has direct or indirect relations to all other models.

    Since most models depend on the Event model in some way, they should
    preferably be accessed via the reverse relation on the event model to
    prevent data leaks.

    :param is_public: Is this event public yet? Should only be set via the
        ``pretalx.orga.views.EventLive`` view or in another way that processes
        the ``pretalx.orga.signals.activate_event`` signal.
    :param locale_array: Contains the event’s active locales as a comma
        separated string. Please use the ``locales`` property to interact
        with this information.
    :param content_locale_array: Contains the event’s active locales available
        for proposals as a comma separated string. Please use the
        ``content_locales`` property to interact with this information.
    :param primary_color: Main event colour. Accepts hex values like
        ``#00ff00``.
    :param custom_css: Custom event CSS. Has to pass fairly restrictive
        validation for security considerations.
    :param custom_domain: Custom event domain, starting with ``https://``.
    :param plugins: A list of active plugins as a comma-separated string.
        Please use the ``plugin_list`` property for interaction.
    :param feature_flags: A JSON field containing feature flags for this event.
        Please use the ``get_feature_flag`` method to check for features,
        so that new feature flags can be added without breaking existing events.
    """

    name = I18nCharField(max_length=200, verbose_name=_("Name"))
    # ``unique=True`` duplicates our ``UniqueConstraint(Lower("slug"))``,
    # but Django produces a noisy warning when unique=True is not set,
    # so we leave it in.
    slug = models.SlugField(
        max_length=50,
        db_index=True,
        unique=True,
        validators=[
            RegexValidator(
                regex=FULL_SLUG_REGEX, message=phrases.base.slug_validator_message
            ),
            validate_event_slug_permitted,
        ],
        verbose_name=_("Short form"),
        help_text=phrases.base.slug_validator_message,
    )
    organiser = models.ForeignKey(
        to="Organiser",
        null=True,  # backwards compatibility, won’t ever be empty
        related_name="events",
        on_delete=models.PROTECT,
    )
    is_public = models.BooleanField(default=False, verbose_name=_("Event is public"))
    date_from = DateField(verbose_name=_("Event start date"))
    date_to = DateField(verbose_name=_("Event end date"))
    timezone = models.CharField(
        choices=[(tz, tz) for tz in TIMEZONE_CHOICES],
        max_length=32,
        default="UTC",
        help_text=_(
            "All event dates will be localised and interpreted to be in this timezone."
        ),
    )
    email = models.EmailField(
        verbose_name=_("Organiser email address"),
        help_text=_("Will be used as Reply-To in emails."),
    )
    custom_domain = models.URLField(
        verbose_name=_("Custom domain"),
        help_text=_("Enter a custom domain, such as https://my.event.example.org"),
        null=True,
        blank=True,
    )
    feature_flags = models.JSONField(
        default=default_feature_flags, validators=[validate_feature_flags]
    )
    display_settings = models.JSONField(default=default_display_settings)
    review_settings = models.JSONField(default=default_review_settings)
    mail_settings = models.JSONField(default=default_mail_settings)
    attendee_signup_settings = models.JSONField(
        default=default_attendee_signup_settings,
        validators=[validate_attendee_signup_settings],
    )
    primary_color = models.CharField(
        max_length=7,
        null=True,
        blank=True,
        validators=[RegexValidator("#([0-9A-Fa-f]{3}){1,2}")],
        verbose_name=_("Main event colour"),
        help_text=_(
            "Provide a hex value like #00ff00 if you want to style pretalx in your event’s colour scheme."
        ),
    )
    custom_css = models.FileField(
        upload_to=event_css_path,
        null=True,
        blank=True,
        verbose_name=_("Custom Event CSS"),
        help_text=_(
            "Upload a custom CSS file if changing the primary colour is not sufficient for you."
        ),
    )
    logo = models.ImageField(
        upload_to=event_logo_path,
        null=True,
        blank=True,
        verbose_name=_("Logo"),
        help_text=_(
            "If you provide a logo image, your event’s name will not be shown in the event header. "
            "The logo will be scaled down to a height of 140px."
        ),
    )
    header_image = models.ImageField(
        upload_to=event_header_path,
        null=True,
        blank=True,
        verbose_name=_("Header image"),
        help_text=_(
            "If you provide a header image, it will be displayed instead of your event’s color and/or header pattern "
            "at the top of all event pages. It will be center-aligned, so when the window shrinks, the center parts will "
            "continue to be displayed, and not stretched."
        ),
    )
    og_image = models.ImageField(
        upload_to=event_og_path,
        null=True,
        blank=True,
        verbose_name=_("Preview image"),
        help_text=_(
            "This image will be shown as a preview when links to your event are shared on "
            "social media or messaging apps. For best results, use an image at least 1200x630 pixels. "
            "If not set, the logo or header image will be used instead."
        ),
    )
    locale_array = models.TextField(default=settings.LANGUAGE_CODE)
    content_locale_array = models.TextField(default=settings.LANGUAGE_CODE)
    locale = models.CharField(
        max_length=32,
        default=settings.LANGUAGE_CODE,
        choices=settings.LANGUAGES,
        verbose_name=_("Default language"),
    )
    landing_page_text = I18nTextField(
        verbose_name=_("Landing page text"),
        help_text=_(
            "This text will be shown on the landing page, alongside with links to the CfP and schedule, if appropriate."
        )
        + " "
        + phrases.base.use_markdown,
        null=True,
        blank=True,
    )
    featured_sessions_text = I18nTextField(
        verbose_name=_("Featured sessions text"),
        help_text=_(
            "This text will be shown at the top of the featured sessions page instead of the default text."
        )
        + " "
        + phrases.base.use_markdown,
        null=True,
        blank=True,
    )
    plugins = models.TextField(null=True, blank=True, verbose_name=_("Plugins"))

    HEADER_PATTERN_CHOICES = (
        ("plain", _("Plain")),
        ("pcb", _("Circuits")),
        ("bubbles", _("Circles")),
        ("signal", _("Signal")),
        ("topo", _("Topography")),
        ("graph", _("Graph Paper")),
    )

    objects = models.Manager()

    class urls(EventUrls):
        base = "/{self.slug}/"
        login = "{base}login/"
        logout = "{base}logout"
        auth = "{base}auth/"
        logo = "{self.logo.url}"
        social_image = "{base}og-image"
        reset = "{base}reset"
        submit = "{base}submit/"
        user = "{base}me/"
        user_delete = "{base}me/delete"
        user_submissions = "{user}submissions/"
        user_mails = "{user}mails/"
        schedule = "{base}schedule/"
        schedule_nojs = "{schedule}nojs"
        featured = "{base}featured/"
        talks = "{base}talk/"
        speakers = "{base}speaker/"
        changelog = "{schedule}changelog/"
        feed = "{schedule}feed.xml"
        export = "{schedule}export/"
        frab_xml = "{export}schedule.xml"
        frab_json = "{export}schedule.json"
        frab_xcal = "{export}schedule.xcal"
        ical = "{export}schedule.ics"
        schedule_widget_data = "{schedule}widgets/schedule.json"
        schedule_widget_script = "{base}widgets/schedule.js"
        settings_css = "{base}static/event.css"

    class orga_urls(EventUrls):
        base = "/orga/event/{self.slug}/"
        login = "{base}login/"
        live = "{base}live"
        delete = "{base}delete"
        cfp = "{base}cfp/"
        history = "{base}history/"
        users = "{base}api/users"
        mail = "{base}mails/"
        compose_mails = "{mail}compose"
        compose_mails_sessions = "{compose_mails}/sessions/"
        compose_mails_teams = "{compose_mails}/teams/"
        send_drafts_reminder = "{compose_mails}/reminders"
        mail_templates = "{mail}templates/"
        new_template = "{mail_templates}new/"
        outbox = "{mail}outbox/"
        sent_mails = "{mail}sent"
        send_outbox = "{outbox}send"
        purge_outbox = "{outbox}purge"
        submissions = "{base}submissions/"
        tags = "{submissions}tags/"
        new_tag = "{tags}new/"
        submission_cards = "{base}submissions/cards/"
        stats = "{base}submissions/statistics/"
        new_submission = "{submissions}new"
        feedback = "{submissions}feedback/"
        apply_pending = "{submissions}apply-pending/"
        speakers = "{base}speakers/"
        settings = edit_settings = "{base}settings/"
        review_settings = "{settings}review/"
        mail_settings = edit_mail_settings = "{settings}mail"
        widget_settings = "{settings}widget"
        team_settings = "{settings}team/"
        new_team = "{settings}team/new"
        room_settings = "{schedule}rooms/"
        new_room = "{room_settings}new/"
        schedule = "{base}schedule/"
        schedule_export = "{schedule}export/"
        schedule_export_trigger = "{schedule_export}trigger"
        schedule_export_download = "{schedule_export}download"
        release_schedule = "{schedule}release"
        toggle_schedule = "{schedule}toggle"
        reviews = "{base}reviews/"
        review_assignments = "{reviews}assign/"
        schedule_api = "{base}schedule/api/"
        talks_api = "{schedule_api}talks/"
        plugins = "{settings}plugins"
        information = "{base}info/"
        new_information = "{base}info/new/"

    class api_urls(EventUrls):
        base = "/api/events/{self.slug}/"
        submissions = "{base}submissions/"
        slots = "{base}slots/"
        talks = "{base}talks/"
        schedules = "{base}schedules/"
        speakers = "{base}speakers/"
        reviews = "{base}reviews/"
        feedback = "{base}feedback/"
        rooms = "{base}rooms/"
        questions = "{base}questions/"
        question_options = "{base}question-options/"
        answers = "{base}answers/"
        tags = "{base}tags/"
        tracks = "{base}tracks/"
        submission_types = "{base}submission-types/"
        mail_templates = "{base}mail-templates/"
        access_codes = "{base}access-codes/"
        speaker_information = "{base}speaker-information/"

    class Meta:
        ordering = ("date_from",)
        constraints = [
            models.UniqueConstraint(Lower("slug"), name="event_slug_lower_unique")
        ]
        rules_permissions = {
            "orga_access": has_any_permission,
            "view": is_event_visible | has_any_permission,
            "update": can_change_event_settings,
            "create": can_create_events,
        }

    def __str__(self) -> str:
        return str(self.name)

    def clean(self):
        super().clean()
        if self.slug:
            self.slug = self.slug.lower()
        validate_event_slug_unique(
            self.slug, exclude_event=None if self._state.adding else self
        )
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError({"date_from": phrases.orga.event_date_start_invalid})
        if self.locale and self.locale_array:
            active_locales = self.locale_array.split(",")
            if self.locale not in active_locales:
                raise ValidationError(
                    {
                        "locale": _(
                            "Your default language needs to be one of your active languages."
                        )
                    }
                )

    @cached_property
    def locales(self) -> list[str]:
        """Is a list of active event locales."""
        return self.locale_array.split(",")

    @cached_property
    def content_locales(self) -> list[str]:
        """Is a list of active content locales."""
        return self.content_locale_array.split(",")

    @cached_property
    def is_multilingual(self) -> bool:
        """Is ``True`` if the event supports more than one locale."""
        return len(self.content_locales) > 1

    @cached_property
    def has_active_tracks(self) -> bool:
        """Is ``True`` if tracks are enabled and at least one track exists."""
        return bool(self.get_feature_flag("use_tracks") and self.tracks.exists())

    @cached_property
    def named_locales(self) -> list:
        """Is a list of tuples of locale codes and natural names for this
        event."""
        return [
            (language["code"], language["natural_name"])
            for language in settings.LANGUAGES_INFORMATION.values()
            if language["code"] in self.locales
        ]

    @cached_property
    def available_content_locales(self) -> list:
        # Content locales can be anything pretalx knows as a language, merged with
        # this event's plugin locales.

        locale_names = copy.copy(LANGUAGE_NAMES)
        locale_names.update(self.named_plugin_locales)
        return sorted([(key, value) for key, value in locale_names.items()])

    @cached_property
    def named_content_locales(self) -> list:
        locale_names = dict(self.available_content_locales)
        return [(code, locale_names[code]) for code in self.content_locales]

    @cached_property
    def named_plugin_locales(self) -> list:
        locale_names = copy.copy(LANGUAGE_NAMES)
        locale_names.update(self.named_locales)
        result = {}
        for _receiver, locales in register_locales.send(sender=self):
            for locale in locales:
                if isinstance(locale, tuple):
                    result[locale[0]] = locale[1]
                else:
                    result[locale] = locale_names.get(locale, locale)
        return result

    @cached_property
    def plugin_locales(self) -> list:
        return sorted(self.named_plugin_locales.keys())

    @cached_property
    def cache(self):
        """Returns an :py:class:`ObjectRelatedCache` object.

        This behaves equivalent to Django's built-in cache backends, but
        puts you into an isolated environment for this event, so you
        don't have to prefix your cache keys.
        """
        return ObjectRelatedCache(self, field="slug")

    @property
    def plugin_list(self) -> list:
        if not self.plugins:
            return []
        return self.plugins.split(",")

    @cached_property
    def available_plugins(self):
        return {
            plugin.module: plugin
            for plugin in get_all_plugins(self)
            if not plugin.name.startswith(".") and getattr(plugin, "visible", True)
        }

    @cached_property
    def visible_primary_color(self):
        return self.primary_color or settings.DEFAULT_EVENT_PRIMARY_COLOR

    @cached_property
    def primary_color_needs_dark_text(self):
        # If this property changes, the colourpicker.js preview for text
        # on primary colour buttons also needs to change.
        if not self.primary_color:
            return False

        return self.cache.get_or_set(
            f"dark_text_{self.primary_color.lstrip('#')}",
            lambda: not has_good_contrast(self.primary_color, threshold=3),
            timeout=86400 * 365,
        )

    @cached_property
    def has_custom_styles(self):
        return bool(
            self.primary_color
            or self.display_settings.get("heading_font")
            or self.display_settings.get("text_font")
        )

    @cached_property
    def pending_mails(self) -> int:
        """The amount of currently unsent.

        :class:`~pretalx.mail.models.QueuedMail` objects.
        """
        return self.queued_mails.filter(state=QueuedMailStates.DRAFT).count()

    @cached_property
    def has_unreleased_schedule_changes(self) -> bool:
        """True iff the WIP schedule differs from the latest released schedule."""
        from pretalx.schedule.domain.changes import (  # noqa: PLC0415 -- thin method
            has_unreleased_schedule_changes,
        )

        return has_unreleased_schedule_changes(self)

    @cached_property
    def wip_schedule(self):
        """Returns the latest unreleased.

        :class:`~pretalx.schedule.models.schedule.Schedule`.

        :retval: :class:`~pretalx.schedule.models.schedule.Schedule`
        """
        try:
            schedule, _ = self.schedules.get_or_create(version__isnull=True)
        except MultipleObjectsReturned:
            # No idea how this happens – a race condition due to transaction weirdness?
            schedules = list(self.schedules.filter(version__isnull=True))
            schedule = schedules[0]
            # It's only ever been two so far, but while we're being resilient …
            for dupe in schedules[1:]:
                TalkSlot.objects.filter(schedule=dupe).delete()
                dupe.delete()
        return schedule

    @cached_property
    def current_schedule(self):
        if pk := getattr(self, "_current_schedule_pk", None):
            # The event middleware prefetches the current schedule
            return self.schedules.get(pk=pk)
        return (
            self.schedules.order_by("-published")
            .filter(published__isnull=False)
            .first()
        )

    @cached_property
    def duration(self):
        return (self.date_to - self.date_from).days + 1

    @cached_property
    def event(self):
        return self

    @property
    def valid_availabilities(self):
        return self.availabilities.filter(
            start__lte=self.datetime_to, end__gte=self.datetime_from
        )

    @cached_property
    def teams(self):
        """Returns all :class:`~pretalx.event.models.organiser.Team` objects
        that concern this event."""

        return self.organiser.teams.filter(
            models.Q(all_events=True)
            | models.Q(models.Q(all_events=False) & models.Q(limit_events__in=[self]))
        )

    @cached_property
    def reviewers(self):
        from pretalx.person.models import User  # noqa: PLC0415 -- circular import

        return User.objects.filter(
            teams__in=self.teams.filter(is_reviewer=True)
        ).distinct()

    @cached_property
    def datetime_from(self) -> dt.datetime:
        """The localised datetime of the event start date.

        :rtype: datetime
        """
        return make_aware(
            dt.datetime.combine(self.date_from, dt.time(hour=0, minute=0, second=0)),
            self.tz,
        )

    @cached_property
    def datetime_to(self) -> dt.datetime:
        """The localised datetime of the event end date.

        :rtype: datetime
        """
        return make_aware(
            dt.datetime.combine(self.date_to, dt.time(hour=23, minute=59, second=59)),
            self.tz,
        )

    @cached_property
    def tz(self):
        return zoneinfo.ZoneInfo(self.timezone)

    @cached_property
    def reviews(self):
        return Review.objects.filter(submission__event=self)

    @cached_property
    def active_review_phase(self):
        return self.review_phases.filter(is_active=True).first()

    @cached_property
    def talks(self):
        """Returns a queryset of all.

        :class:`~pretalx.submission.models.submission.Submission` object in the
        current released schedule.
        """
        from pretalx.submission.domain.queries.submission import (  # noqa: PLC0415 -- thin method
            talks_for_event,
        )

        return talks_for_event(self)

    @cached_property
    def speakers(self):
        """Returns a queryset of all speakers (of type.

        :class:`~pretalx.person.models.profile.SpeakerProfile`) visible in the
        current released schedule.
        """
        from pretalx.person.domain.queries.profile import (  # noqa: PLC0415 -- thin method
            speakers_for_event,
        )

        return speakers_for_event(self)

    @cached_property
    def submitters(self):
        """Returns a queryset of all
        :class:`~pretalx.person.models.profile.SpeakerProfile` objects who have
        submitted to this event.

        Ignores speakers who have deleted all of their submissions.
        """
        from pretalx.person.domain.queries.profile import (  # noqa: PLC0415 -- thin method
            submitters_for_event,
        )

        return submitters_for_event(self)

    @cached_property
    def cfp_flow(self):
        from pretalx.cfp.flow import CfPFlow  # noqa: PLC0415 -- circular import

        return CfPFlow(self)

    def get_date_range_display(self) -> str:
        """Returns the localised, prettily formatted date range for this event.

        E.g. as long as the event takes place within the same month, the
        month is only named once.
        """
        return daterange(self.date_from, self.date_to)

    def get_feature_flag(self, feature):
        if feature in self.feature_flags:
            return self.feature_flags[feature]
        return default_feature_flags().get(feature, False)


class EventExtraLink(OrderedModel, PretalxModel):
    event = models.ForeignKey(
        to="Event", on_delete=models.CASCADE, related_name="extra_links"
    )
    label = I18nCharField(max_length=200, verbose_name=_("Link text"))
    url = models.URLField(verbose_name=_("Link URL"))
    role = models.CharField(
        max_length=6,
        choices=(("footer", "Footer"), ("header", "Header")),
        default="footer",
    )

    objects = ScopedManager(event="event")
