# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from django_scopes import ScopedManager
from i18nfield.fields import I18nCharField

from pretalx.common.models.fields import DateTimeField, MarkdownField
from pretalx.common.models.mixins import PretalxModel
from pretalx.common.urls import EventUrls
from pretalx.person.rules import is_administrator, is_reviewer
from pretalx.submission.rules import (
    can_be_reviewed,
    can_view_all_reviews,
    can_view_reviewer_names,
    can_view_reviews,
    has_reviewer_access,
    is_review_author,
    orga_can_change_submissions,
    reviews_are_open,
)
from pretalx.submission.validators.review import (
    validate_non_independent_category_remains,
)


class ReviewScoreCategory(PretalxModel):
    event = models.ForeignKey(
        to="event.Event", related_name="score_categories", on_delete=models.CASCADE
    )
    name = I18nCharField()
    weight = models.DecimalField(max_digits=4, decimal_places=1, default=1)
    required = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    limit_tracks = models.ManyToManyField(
        to="submission.Track",
        verbose_name=_("Limit to tracks"),
        blank=True,
        help_text=_("Leave empty to use this category for all tracks."),
    )
    is_independent = models.BooleanField(
        default=False,
        verbose_name=_("Independent score"),
        help_text=_(
            "Independent scores are not part of the total score. Instead they are shown in a separate column in the review dashboard."
        ),
    )

    class urls(EventUrls):
        base = "{self.event.orga_urls.review_settings}category/{self.pk}/"
        delete = "{base}delete"

    def clean(self):
        super().clean()
        if self.is_independent and not self._state.adding:
            # The remaining-non-independent check only matters when an existing
            # category is being flipped to independent.
            validate_non_independent_category_remains(self)

    def save(self, *args, **kwargs):
        if self.is_independent:
            self.weight = 0
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        validate_non_independent_category_remains(self)
        return super().delete(*args, **kwargs)


class ReviewScore(PretalxModel):
    category = models.ForeignKey(
        to=ReviewScoreCategory, related_name="scores", on_delete=models.CASCADE
    )
    value = models.DecimalField(max_digits=7, decimal_places=2)
    label = models.CharField(null=True, blank=True, max_length=200)

    objects = ScopedManager(event="category__event")

    def __str__(self):
        return self.format("words_numbers")

    def format(self, fmt):
        if fmt == "words":
            return self.label
        value = int(self.value) if int(self.value) == self.value else self.value
        if fmt == "numbers" or self.label == str(value):
            return str(value)
        if fmt == "numbers_words":
            return f"{value} ({self.label})"
        return f"{self.label} ({value})"

    class Meta:
        ordering = ("value",)


class Review(PretalxModel):
    """Reviews model the opinion of reviewers of a.

    :class:`~pretalx.submission.models.submission.Submission`.

    They can, but don't have to, include a score and a text.

    :param text: The review itself. May be empty.
    :param score: This score is calculated from all the related ``scores``
        and their weights. Do not set it directly; call
        ``pretalx.submission.domain.review.update_review_score`` after
        modifying the m2m scores.
    """

    submission = models.ForeignKey(
        to="submission.Submission", related_name="reviews", on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        to="person.User", related_name="reviews", on_delete=models.CASCADE
    )
    text = MarkdownField(verbose_name=_("Review"), null=True, blank=True)
    score = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=pgettext_lazy("review score/rating", "Score"),
        null=True,
        blank=True,
    )
    scores = models.ManyToManyField(to=ReviewScore, related_name="reviews")

    objects = ScopedManager(event="submission__event")

    log_prefix = "pretalx.submission.review"

    class Meta:
        unique_together = (("user", "submission"),)
        rules_permissions = {
            "list": orga_can_change_submissions | is_reviewer,
            "list_all": orga_can_change_submissions
            | (is_reviewer & can_view_all_reviews),
            "list_reviewers": orga_can_change_submissions
            | (is_reviewer & can_view_reviewer_names),
            "view": is_review_author
            | (is_reviewer & can_view_reviews)
            | orga_can_change_submissions,
            # Needs to be coupled with a check on has_reviewer_access & can_be_reviewed
            # on the proposal – but we don’t have that at create time yet.
            "create": is_reviewer & reviews_are_open,
            "update": has_reviewer_access & is_review_author & can_be_reviewed,
            "delete": is_administrator | (is_review_author & can_be_reviewed),
        }

    def __str__(self):
        return f"Review(event={self.submission.event.slug}, submission={self.submission.title}, user={self.user.get_display_name}, score={self.score})"

    @property
    def log_parent(self):
        return self.submission

    @cached_property
    def event(self):
        return self.submission.event

    @cached_property
    def display_score(self) -> str:
        """Helper method to get a display string of the review's score."""
        if self.score is None:
            return "×"
        if int(self.score) == self.score:
            return str(int(self.score))
        return str(self.score)

    class urls(EventUrls):
        base = "{self.submission.orga_urls.reviews}"
        delete = "{base}{self.pk}/delete"


class ReviewPhase(PretalxModel):
    """ReviewPhases determine reviewer access rights during a (potentially
    open) time frame.

    Phases are ordered by ``(start, end)``, with null-start phases first.

    :param is_active: Is this phase currently active? There can be only one
        active phase per event. Use
        ``pretalx.submission.domain.review.activate_review_phase`` to
        activate a phase, since it enforces that invariant.
    """

    log_prefix = "pretalx.review_phase"

    event = models.ForeignKey(
        to="event.Event", related_name="review_phases", on_delete=models.CASCADE
    )
    name = models.CharField(verbose_name=_("Name"), max_length=100)
    start = DateTimeField(verbose_name=_("Phase start"), null=True, blank=True)
    end = DateTimeField(verbose_name=_("Phase end"), null=True, blank=True)
    is_active = models.BooleanField(default=False)

    can_review = models.BooleanField(
        verbose_name=_("Reviewers can write and edit reviews"), default=True
    )
    proposal_visibility = models.CharField(
        verbose_name=_("Reviewers may see these proposals"),
        choices=(("all", _("All")), ("assigned", _("Only assigned proposals"))),
        max_length=8,
        default="all",
        help_text=_(
            "If you select “all”, reviewers can review all proposals that their teams have access to (so either all, or specific tracks). "
            "In this mode, assigned proposals will be highlighted and will be shown first in the review workflow. "
        ),
    )
    can_see_other_reviews = models.CharField(
        verbose_name=_("Reviewers can see other reviews"),
        max_length=12,
        choices=(
            ("always", _("Always")),
            ("never", _("Never")),
            ("after_review", _("After reviewing the proposal")),
        ),
        default="after_review",
    )
    can_see_speaker_names = models.BooleanField(
        verbose_name=_("Reviewers can see speaker names"), default=True
    )
    can_see_reviewer_names = models.BooleanField(
        verbose_name=_("Reviewers can see the names of other reviewers"), default=True
    )
    can_change_submission_state = models.BooleanField(
        verbose_name=_("Reviewers can accept and reject proposals"), default=False
    )
    can_tag_submissions = models.CharField(
        verbose_name=_("Reviewers can tag proposals"),
        max_length=12,
        choices=(
            ("never", _("Never")),
            ("use_tags", _("Add and remove existing tags")),
            ("create_tags", _("Add, remove and create tags")),
        ),
        default="never",
    )
    speakers_can_change_submissions = models.BooleanField(
        verbose_name=_("Speakers can modify their proposals before acceptance"),
        help_text=_(
            "By default, modification of proposals is locked after the CfP ends, and is re-enabled once the proposal was accepted."
        ),
        default=False,
    )

    class Meta:
        ordering = (
            models.F("start").asc(nulls_first=True),
            models.F("end").asc(nulls_first=True),
        )

    class urls(EventUrls):
        base = "{self.event.orga_urls.review_settings}phase/{self.pk}/"
        delete = "{base}delete"
        activate = "{base}activate"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.start and self.end and self.start > self.end:
            raise ValidationError(
                {"end": _("The end of a phase has to be after its start.")}
            )

    @property
    def log_parent(self):
        return self.event
