# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Florian Moesch
# SPDX-FileContributor: Raphael Michel
# SPDX-FileContributor: luto

import statistics

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager

from pretalx.agenda import rules as agenda_rules
from pretalx.common.models.fields import MarkdownField
from pretalx.common.models.mixins import GenerateCode, PretalxModel
from pretalx.common.text.path import hashed_path
from pretalx.common.text.phrases import phrases
from pretalx.common.text.serialize import serialize_duration
from pretalx.common.urls import EventUrls
from pretalx.person.rules import is_reviewer
from pretalx.schedule.models.availability import Availability
from pretalx.submission import rules
from pretalx.submission.enums import (
    AttendeeSignupStates,
    SignupStatus,
    SubmissionStates,
)
from pretalx.submission.validators.submission import validate_signup_required


def generate_invite_code(length=32):
    return get_random_string(length=length, allowed_chars=Submission.code_charset)


def submission_image_path(instance, filename):
    return hashed_path(
        filename,
        target_name="image",
        upload_dir=f"{instance.event.slug}/submissions/{instance.code}/",
    )


class SubmissionQuerySet(models.QuerySet):
    def with_sorted_speakers(self):
        from pretalx.submission.domain.queries.submission import (  # noqa: PLC0415 -- thin method
            sorted_speakers_prefetch,
        )

        return self.prefetch_related(sorted_speakers_prefetch())


class SubmissionManager(models.Manager.from_queryset(SubmissionQuerySet)):
    def get_queryset(self):
        return super().get_queryset().exclude(state=SubmissionStates.DRAFT)


class AllSubmissionManager(models.Manager.from_queryset(SubmissionQuerySet)):
    pass


class SpeakerRole(models.Model):
    """Through model connecting speaker and submission."""

    submission = models.ForeignKey(
        to="submission.Submission",
        on_delete=models.CASCADE,
        related_name="speaker_roles",
    )
    speaker = models.ForeignKey(
        to="person.SpeakerProfile",
        on_delete=models.CASCADE,
        related_name="speaker_roles",
    )
    position = models.PositiveIntegerField(default=0)

    objects = ScopedManager(event="submission__event")

    class Meta:
        ordering = ("position",)
        unique_together = (("submission", "speaker"),)

    def __str__(self):
        return f"SpeakerRole(submission={self.submission.code}, speaker={self.speaker})"


class Submission(GenerateCode, PretalxModel):
    """Submissions are, next to :class:`~pretalx.event.models.event.Event`, the
    central model in pretalx.

    State changes must go through :func:`pretalx.submission.domain.submission.set_submission_state`,
    which is called by the ``accept()``, ``reject()`` etc model methods.
    """

    code = models.CharField(max_length=16, unique=True)
    speakers = models.ManyToManyField(
        to="person.SpeakerProfile",
        related_name="submissions",
        through=SpeakerRole,
        blank=True,
        verbose_name=_("Speakers"),
    )
    event = models.ForeignKey(
        to="event.Event", on_delete=models.PROTECT, related_name="submissions"
    )
    title = models.CharField(max_length=200, verbose_name=_("Proposal title"))
    submission_type = models.ForeignKey(  # Reasonable default must be set in form/view
        to="submission.SubmissionType",
        related_name="submissions",
        on_delete=models.PROTECT,
        verbose_name=_("Session type"),
    )
    track = models.ForeignKey(
        to="submission.Track",
        related_name="submissions",
        on_delete=models.PROTECT,
        verbose_name=_("Track"),
        null=True,
        blank=True,
    )
    tags = models.ManyToManyField(
        to="submission.Tag", related_name="submissions", verbose_name=_("Tags")
    )
    state = models.CharField(
        max_length=SubmissionStates.get_max_length(),
        choices=SubmissionStates.choices,
        default=SubmissionStates.SUBMITTED,
        verbose_name=_("Proposal state"),
    )
    pending_state = models.CharField(
        null=True,
        blank=True,
        max_length=SubmissionStates.get_max_length(),
        choices=SubmissionStates.choices,
        default=None,
        verbose_name=_("Pending proposal state"),
    )
    abstract = MarkdownField(null=True, blank=True, verbose_name=_("Abstract"))
    description = MarkdownField(null=True, blank=True, verbose_name=_("Description"))
    notes = MarkdownField(
        null=True,
        blank=True,
        verbose_name=_("Notes"),
        help_text=_(
            "These notes are meant for the organisers and won’t be made public."
        ),
    )
    internal_notes = models.TextField(
        null=True,
        blank=True,
        verbose_name=phrases.base.internal_notes,
        help_text=phrases.base.internal_notes_help,
    )
    duration = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Duration"),
        help_text=_("Duration in minutes"),
    )
    slot_count = models.IntegerField(
        default=1,
        verbose_name=_("Slot count"),
        help_text=_("How often this session takes place."),
        validators=[MinValueValidator(1)],
    )
    attendee_signup_required = models.BooleanField(
        null=True,  # None means that the track and submission_type settings are used
        blank=True,
        verbose_name=_("Requires signup"),
        help_text=_("Override whether attendees must sign up to attend this session."),
    )
    attendee_signup_capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Attendee capacity"),
        help_text=_("Override the room capacity for this session."),
        validators=[MinValueValidator(1)],
    )
    content_locale = models.CharField(
        max_length=32, default=settings.LANGUAGE_CODE, verbose_name=_("Language")
    )
    is_featured = models.BooleanField(
        default=False,
        verbose_name=_("Show this session in public list of featured sessions."),
    )
    do_not_record = models.BooleanField(
        default=False, verbose_name=_("Don’t record this session.")
    )
    image = models.ImageField(
        null=True,
        blank=True,
        upload_to=submission_image_path,
        verbose_name=_("Session image"),
        help_text=phrases.base.image_help,
    )
    invitation_token = models.CharField(max_length=32, default=generate_invite_code)
    access_code = models.ForeignKey(
        to="submission.SubmitterAccessCode",
        related_name="submissions",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    review_code = models.CharField(
        max_length=32, unique=True, null=True, blank=True, default=generate_invite_code
    )
    anonymised = models.JSONField(null=True, blank=True)
    # Emails the speaker entered into the wizard's "additional_speaker" field
    # while the proposal is still a DRAFT. Promoted to real
    # ``SubmissionInvitation`` rows when the proposal is submitted; not
    # exposed outside the draft → submit transition.
    draft_additional_speakers = models.JSONField(default=list, blank=True)
    assigned_reviewers = models.ManyToManyField(
        verbose_name=_("Assigned reviewers"),
        to="person.User",
        related_name="assigned_reviews",
        blank=True,
    )

    objects = ScopedManager(event="event", _manager_class=SubmissionManager)
    all_objects = ScopedManager(event="event", _manager_class=AllSubmissionManager)

    log_prefix = "pretalx.submission"

    @property
    def log_parent(self):
        return self.event

    class Meta:
        rules_permissions = {
            "list": agenda_rules.is_agenda_visible
            | rules.orga_can_change_submissions
            | is_reviewer,
            "list_featured": agenda_rules.are_featured_submissions_visible
            | rules.orga_can_change_submissions,
            "view": agenda_rules.is_agenda_submission_visible
            | rules.is_speaker
            | rules.orga_can_change_submissions
            | rules.has_reviewer_access,
            "view_public": agenda_rules.is_agenda_submission_visible
            | rules.orga_can_change_submissions,
            "orga_list": rules.orga_can_change_submissions | is_reviewer,
            "orga_update": rules.orga_can_change_submissions,
            "review": rules.has_reviewer_access & rules.can_be_reviewed,
            "view_reviews": rules.has_reviewer_access
            | rules.orga_can_change_submissions,
            "view_all_reviews": (rules.has_reviewer_access & rules.can_view_reviews)
            | rules.orga_can_change_submissions,
            "create": rules.orga_can_change_submissions,
            "update": (rules.can_be_edited & rules.is_speaker)
            | rules.orga_can_change_submissions,
            "delete": rules.orga_can_change_submissions,
            "state_change": rules.orga_or_reviewer_can_change_submission,
            "accept_or_reject": rules.orga_or_reviewer_can_change_submission,
            "withdraw": rules.can_be_withdrawn & rules.is_speaker,
            "confirm": rules.can_be_confirmed
            & (rules.is_speaker | rules.orga_can_change_submissions),
            "remove": rules.can_be_removed & rules.orga_can_change_submissions,
            "view_feedback_page": agenda_rules.event_uses_feedback
            & agenda_rules.is_agenda_submission_visible,
            "view_scheduling_details": agenda_rules.is_submission_visible_via_schedule,
            "view_feedback": rules.is_speaker
            | rules.has_reviewer_access
            | rules.orga_can_change_submissions,
            "give_feedback": agenda_rules.is_agenda_submission_visible
            & rules.is_feedback_ready,
            "is_speaker": rules.is_speaker,
            "add_speaker": rules.can_be_edited & rules.can_request_speakers,
        }

    class urls(EventUrls):
        user_base = "{self.event.urls.user_submissions}{self.code}/"
        withdraw = "{user_base}withdraw"
        discard = "{user_base}discard"
        confirm = "{user_base}confirm"
        public_base = "{self.event.urls.base}talk/{self.code}"
        public = "{public_base}/"
        feedback = "{public}feedback/"
        signup = "{public}signup/"
        signup_cancel = "{public}signup/cancel/"
        social_image = "{public}og-image"
        ical = "{public_base}.ics"
        image = "{self.image_url}"
        invite = "{user_base}invite"
        retract_invitation = "{user_base}retract-invitation"
        accept_invitation = (
            "{self.event.urls.base}invitation/{self.code}/{self.invitation_token}"
        )
        review = "{self.event.urls.base}talk/review/{self.review_code}"

    class orga_urls(EventUrls):
        base = edit = "{self.event.orga_urls.submissions}{self.code}/"
        make_submitted = "{base}submit"
        accept = "{base}accept"
        reject = "{base}reject"
        confirm = "{base}confirm"
        delete = "{base}delete"
        withdraw = "{base}withdraw"
        cancel = "{base}cancel"
        speakers = "{base}speakers/"
        delete_speaker = "{speakers}delete"
        reorder_speakers = "{speakers}reorder"
        retract_invitation = "{speakers}invitation/retract"
        reviews = "{base}reviews/"
        feedback = "{base}feedback/"
        toggle_featured = "{base}toggle_featured"
        apply_pending = "{base}apply_pending"
        anonymise = "{base}anonymise/"
        comments = "{base}comments/"
        quick_schedule = "{self.event.orga_urls.schedule}quick/{self.code}/"
        history = "{base}history/"
        signup = "{base}signup/"

    @property
    def image_url(self):
        return self.image.url if self.image else ""

    @cached_property
    def editable(self) -> bool:
        """
        Checks if the speaker is currently allowed to edit the submission.
        """
        try:
            event = self.event
        except ObjectDoesNotExist:
            # Unsaved submissions can always be edited
            return True
        deadline = self.submission_type.deadline or event.cfp.deadline
        deadline_open = (not deadline) or now() <= deadline

        if self.state == SubmissionStates.DRAFT:
            # We have to check if we comply with the standard submission requirements if
            # we are in a draft state, as drafts should only be editable when they could
            # also be submitted.
            # For existing drafts with access codes, we ignore the redemption count
            # since the code was already redeemed when creating the draft.
            access_code = (
                self.access_code
                if (self.access_code and self.access_code.time_valid)
                else None
            )
            if (self.track and self.track.requires_access_code) and not access_code:
                return False
            if self.submission_type.requires_access_code and not access_code:
                return False

            # We are not missing an access code, so we can just check if we hit the
            # deadline or can ignore it safely
            return bool(deadline_open or access_code)

        if not event.get_feature_flag("speakers_can_edit_submissions"):
            return False

        if self.state == SubmissionStates.SUBMITTED:
            return deadline_open or (
                event.active_review_phase
                and event.active_review_phase.speakers_can_change_submissions
            )
        return self.state in SubmissionStates.accepted_states

    @cached_property
    def public_review_link_active(self) -> bool:
        return (
            bool(self.review_code)
            and self.state in SubmissionStates.public_review_states
            and self.event.get_feature_flag("submission_public_review")
        )

    @property
    def is_anonymised(self) -> bool:
        if self.anonymised:
            return bool(self.anonymised.get("_anonymised", False))
        return False

    def get_anonymised(self, attribute):
        if self.is_anonymised and attribute in self.anonymised:
            return self.anonymised[attribute]
        return getattr(self, attribute, None)

    @cached_property
    def reviewer_answers(self):
        return self.answers.filter(question__is_visible_to_reviewers=True).order_by(
            "question__position"
        )

    @cached_property
    def public_answers(self):
        from pretalx.submission.domain.queries.question import (  # noqa: PLC0415 -- thin method
            public_answers_for_submission,
        )

        return public_answers_for_submission(self)

    def get_duration(self) -> int:
        if self.duration is None:  # We permit zero-length duration
            return self.submission_type.default_duration
        return self.duration

    def clean(self):
        super().clean()
        # The model field default is settings.LANGUAGE_CODE, which can disagree
        # with the event's locale (e.g. a German event on a server defaulting to
        # English). Forms/serializers may not surface the field at all when the
        # event has a single content locale, so the fallback lives on the model.
        if self.event_id and self.content_locale not in self.event.content_locales:
            self.content_locale = self.event.locale
        validate_signup_required(self, self.attendee_signup_required)

    def get_instance_data(self):
        data = super().get_instance_data()

        if not self._state.adding:
            lines = [line for r in self.resources.all() if (line := r.as_markdown)]
            if lines:
                data["resources"] = "\n".join(f"- {line}" for line in lines)
            tags = list(self.tags.values_list("tag", flat=True)) or []
            data["tags"] = "\n".join(f"- {tag}" for tag in tags)

        return data

    def confirm(self, person=None, orga: bool = False):
        from pretalx.submission.domain.submission import (  # noqa: PLC0415 -- thin method
            set_submission_state,
        )

        set_submission_state(self, SubmissionStates.CONFIRMED, person=person, orga=orga)

    confirm.alters_data = True

    def accept(self, person=None, orga: bool = True):
        from pretalx.submission.domain.submission import (  # noqa: PLC0415 -- thin method
            set_submission_state,
        )

        set_submission_state(self, SubmissionStates.ACCEPTED, person=person, orga=orga)

    accept.alters_data = True

    def reject(self, person=None, orga: bool = True):
        from pretalx.submission.domain.submission import (  # noqa: PLC0415 -- thin method
            set_submission_state,
        )

        set_submission_state(self, SubmissionStates.REJECTED, person=person, orga=orga)

    reject.alters_data = True

    def get_email_locale(self, fallback=None):
        if self.content_locale in self.event.locales:
            return self.content_locale
        if fallback and fallback in self.event.locales:
            return fallback
        return self.event.locale

    def get_content_locale_display(self):
        locale_names = dict(self.event.named_content_locales)
        if self.content_locale not in locale_names:
            locale_names = dict(self.event.available_content_locales)
        return str(locale_names.get(self.content_locale, self.content_locale))

    def cancel(self, person=None, orga: bool = True):
        from pretalx.submission.domain.submission import (  # noqa: PLC0415 -- thin method
            set_submission_state,
        )

        set_submission_state(self, SubmissionStates.CANCELED, person=person, orga=orga)

    cancel.alters_data = True

    def withdraw(self, person=None, orga: bool = False):
        from pretalx.submission.domain.submission import (  # noqa: PLC0415 -- thin method
            set_submission_state,
        )

        set_submission_state(self, SubmissionStates.WITHDRAWN, person=person, orga=orga)

    withdraw.alters_data = True

    @cached_property
    def integer_uuid(self):
        # For import into Engelsystem, we need to somehow convert our submission code into an unique integer. Luckily,
        # codes can contain 34 different characters (including compatibility with frab imported data) and normally have
        # 6 charactes. Since log2(34 **6) == 30.52, that just fits in to a positive 32-bit signed integer (that
        # Engelsystem expects), if we do it correctly.
        charset = [
            *self.code_charset,
            "1",
            "2",
            "4",
            "5",
            "6",
            "0",
        ]  # compatibility with imported frab data
        base = len(charset)
        table = {char: cp for cp, char in enumerate(charset)}

        intval = 0
        for char in self.code:
            intval *= base
            intval += table[char]
        return intval

    @cached_property
    def slot(self):
        """The first scheduled :class:`~pretalx.schedule.models.slot.TalkSlot`
        of this submission in the current.

        :class:`~pretalx.schedule.models.schedule.Schedule`.

        Note that this slot is not guaranteed to be visible.
        """
        return (
            self.event.current_schedule.talks.filter(submission=self)
            .select_related("room", "submission", "submission__event")
            .first()
            if self.event.current_schedule
            else None
        )

    @cached_property
    def current_slots(self):
        if not self.event.current_schedule:
            return None
        return self.event.current_schedule.talks.filter(
            submission=self, is_visible=True
        ).select_related("room")

    @cached_property
    def public_slots(self):
        """All publicly visible :class:`~pretalx.schedule.models.slot.TalkSlot`
        objects of this submission in the current.

        :class:`~pretalx.schedule.models.schedule.Schedule`.
        """
        if not agenda_rules.is_agenda_visible(None, self.event):
            return []
        return self.current_slots

    @cached_property
    def sorted_speakers(self):
        if "speakers" in getattr(self, "_prefetched_objects_cache", {}):
            return self.speakers.all()
        return self.speakers.order_by("speaker_roles__position")

    @cached_property
    def display_speaker_names(self):
        """Helper method for a consistent speaker name display."""
        return ", ".join(s.get_display_name() for s in self.sorted_speakers)

    @cached_property
    def display_title_with_speakers(self):
        title = (
            f"{phrases.base.quotation_open}{self.title}{phrases.base.quotation_close}"
        )
        if not self.sorted_speakers:
            return title
        return _("{title_in_quotes} by {list_of_speakers}").format(
            title_in_quotes=title, list_of_speakers=self.display_speaker_names
        )

    @cached_property
    def does_accept_feedback(self):
        slot = self.slot
        if slot and slot.start:
            return slot.start < now()
        return False

    @cached_property
    def median_score(self) -> float | None:
        scores = [
            review.score for review in self.reviews.all() if review.score is not None
        ]
        return statistics.median(scores) if scores else None

    @cached_property
    def mean_score(self) -> float | None:
        scores = [
            review.score for review in self.reviews.all() if review.score is not None
        ]
        return round(statistics.fmean(scores), 1) if scores else None

    @cached_property
    def score_categories(self):
        track = self.track
        track_filter = models.Q(limit_tracks__isnull=True)
        if track:
            track_filter |= models.Q(limit_tracks__in=[track])
        return self.event.score_categories.filter(track_filter, active=True).order_by(
            "id"
        )

    @cached_property
    def active_resources(self):
        return self.resources.filter(
            models.Q(  # either the resource exists
                ~models.Q(resource="")
                & models.Q(resource__isnull=False)
                & ~models.Q(resource="None")
            )
            | models.Q(  # or the link exists
                models.Q(link__isnull=False) & ~models.Q(link="")
            )
        ).order_by("link")

    @cached_property
    def private_resources(self):
        return self.active_resources.filter(is_public=False)

    @cached_property
    def public_resources(self):
        return self.active_resources.filter(is_public=True)

    @property
    def user_state(self):
        deadline = self.submission_type.deadline or self.event.cfp.deadline
        cfp_open = (not deadline) or now() <= deadline
        if self.state == SubmissionStates.SUBMITTED and not cfp_open:
            return "review"
        return self.state

    def __str__(self):
        if not self._state.adding:
            return f"Submission(event={self.event.slug}, code={self.code}, title={self.title}, state={self.state})"
        return f"Submission(code={self.code}, title={self.title}, state={self.state})"

    @cached_property
    def export_duration(self):
        return serialize_duration(minutes=self.get_duration())

    @cached_property
    def requires_signup(self) -> bool:
        annotated = getattr(self, "_annotated_requires_signup", None)
        if annotated is not None:
            return annotated
        if self.attendee_signup_required is not None:
            return self.attendee_signup_required
        track_requires = bool(self.track_id and self.track.attendee_signup_required)
        if not self.submission_type_id:
            # Unsaved instance may not have a submission type yet
            return track_requires
        return track_requires or self.submission_type.attendee_signup_required

    @cached_property
    def confirmed_signup_count(self) -> int:
        annotated = getattr(self, "_annotated_confirmed_signup_count", None)
        if annotated is not None:
            return annotated
        return self.attendee_signups.filter(
            state=AttendeeSignupStates.CONFIRMED
        ).count()

    @cached_property
    def effective_signup_capacity(self) -> int | None:
        if self.attendee_signup_capacity is not None:
            return self.attendee_signup_capacity
        slot = self.slot
        if slot and slot.room:
            return slot.room.capacity
        return None

    @cached_property
    def signup_capacity_percent(self) -> int | None:
        capacity = self.effective_signup_capacity
        if not capacity:
            return None
        return min(100, round(self.confirmed_signup_count * 100 / capacity))

    @cached_property
    def signup_status(self) -> str | None:
        if hasattr(self, "_annotated_signup_status"):
            return self._annotated_signup_status
        if not self.event.get_feature_flag("attendee_signup"):
            return None
        if not self.requires_signup:
            return None
        capacity = self.effective_signup_capacity
        if capacity is not None and self.confirmed_signup_count >= capacity:
            return SignupStatus.FULL
        return SignupStatus.OPEN

    @property
    def availabilities(self):
        """The intersection of all.

        :class:`~pretalx.schedule.models.availability.Availability` objects of
        all speakers of this submission.
        """
        all_availabilities = self.event.valid_availabilities.filter(
            person__in=self.speakers.all()
        )
        return Availability.intersection(all_availabilities)

    def add_favourite(self, user):
        SubmissionFavourite.objects.get_or_create(user=user, submission=self)

    def remove_favourite(self, user):
        SubmissionFavourite.objects.filter(user=user, submission=self).delete()

    def log_action(self, action, data=None, **kwargs):
        if self.state != SubmissionStates.DRAFT:
            return super().log_action(action=action, data=data, **kwargs)


class SubmissionFavourite(PretalxModel):
    user = models.ForeignKey(
        to="person.User", on_delete=models.CASCADE, related_name="submission_favourites"
    )
    submission = models.ForeignKey(
        to="submission.Submission", on_delete=models.CASCADE, related_name="favourites"
    )
    objects = ScopedManager(event="submission__event")

    class Meta:
        unique_together = (("user", "submission"),)


class SubmissionInvitation(PretalxModel):
    """Track pending speaker invitations for submissions.

    When a speaker is invited to a submission, a SubmissionInvitation is created
    with a unique token. The invitation is deleted when the invited person accepts
    it, or can be retracted by organisers or the submitter.
    """

    submission = models.ForeignKey(
        to="submission.Submission", related_name="invitations", on_delete=models.CASCADE
    )
    email = models.EmailField(verbose_name=_("Email"))
    token = models.CharField(default=generate_invite_code, max_length=64, unique=True)

    objects = ScopedManager(event="submission__event")

    class Meta:
        unique_together = (("submission", "email"),)

    class urls(EventUrls):
        base = "{self.submission.event.urls.base}invitation/{self.submission.code}/{self.token}"

    @property
    def event(self):
        return self.submission.event

    def __str__(self):
        return _("Invite to {submission} for {email}").format(
            submission=self.submission.title, email=self.email
        )
