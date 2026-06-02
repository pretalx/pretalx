# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from collections import defaultdict
from contextlib import suppress

from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, F, Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from django.views.generic import FormView, ListView, TemplateView
from django_context_decorator import context

from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.common.text.phrases import phrases
from pretalx.common.ui import Button, api_buttons
from pretalx.common.views.generic import CreateOrUpdateView, OrgaTableMixin
from pretalx.common.views.helpers import is_htmx
from pretalx.common.views.mixins import (
    ActionConfirmMixin,
    EventPermissionRequired,
    PermissionRequired,
)
from pretalx.common.views.redirect import get_next_url
from pretalx.event.domain.queries.team import event_reviewer_teams
from pretalx.orga.forms.export import ReviewExportForm
from pretalx.orga.forms.review import (
    BulkTagForm,
    DirectionForm,
    ProposalForReviewerForm,
    ReviewAssignImportForm,
    ReviewerForProposalForm,
)
from pretalx.orga.forms.submission import SubmissionStateChangeForm
from pretalx.orga.tables.submission import ReviewTable
from pretalx.orga.views.submission import SubmissionListMixin
from pretalx.submission.domain.queries.question import questions_for_user
from pretalx.submission.domain.queries.review import (
    annotate_aggregate_scores,
    annotate_review_count,
    annotate_scored_review_count,
    annotate_state_rank,
    annotate_user_review_score,
    review_dashboard_prefetches,
    review_view_submissions,
)
from pretalx.submission.domain.queries.submission import (
    reviewable_submissions_for_user,
    unreviewed_submissions_for_user,
)
from pretalx.submission.domain.submission import (
    send_state_mail,
    set_pending_state,
    set_submission_state,
)
from pretalx.submission.interfaces.forms import (
    QuestionsForm,
    ReviewForm,
    SubmissionFilterForm,
    TagsForm,
)
from pretalx.submission.models import (
    QuestionTarget,
    QuestionVariant,
    Review,
    Submission,
    SubmissionStates,
)
from pretalx.submission.rules import is_speaker, reviews_are_open


class ReviewDashboard(
    EventPermissionRequired, SubmissionListMixin, OrgaTableMixin, ListView
):
    template_name = "orga/review/dashboard.html"
    permission_required = "submission.list_review"
    table_class = ReviewTable
    paginate_by = 250
    usable_states = (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.REJECTED,
        SubmissionStates.CONFIRMED,
    )

    def filter_range(self, queryset):
        review_count = self.request.GET.get("review-count") or ","
        if "," not in review_count:
            return queryset
        min_reviews, max_reviews = review_count.split(",", maxsplit=1)
        if min_reviews:
            with suppress(Exception):
                min_reviews = int(min_reviews)
                if min_reviews > 0:
                    queryset = queryset.filter(review_count__gte=min_reviews)
        if max_reviews:
            with suppress(Exception):
                max_reviews = int(max_reviews)
                if max_reviews < self.max_review_count:
                    queryset = queryset.filter(review_count__lte=max_reviews)
        return queryset

    def get_queryset(self):
        queryset = self._get_base_queryset().filter(state__in=self.usable_states)
        queryset = annotate_review_count(queryset)
        queryset = annotate_scored_review_count(queryset)
        queryset = annotate_state_rank(queryset)
        queryset = annotate_user_review_score(queryset, self.request.user)
        queryset = self.filter_range(queryset)

        if self.can_see_all_reviews:
            queryset = annotate_aggregate_scores(queryset)

        queryset = review_dashboard_prefetches(queryset)

        if not self.request.GET.get("sort"):
            if self.can_see_all_reviews:
                aggregate_method = self.request.event.review_settings[
                    "aggregate_method"
                ]
                score_field = f"{aggregate_method}_score"
            else:
                score_field = "user_score"

            queryset = queryset.order_by(
                "state_rank", "state", F(score_field).desc(nulls_last=True), "code"
            )

        return queryset

    @context
    @cached_property
    def can_change_submissions(self):
        return self.request.user.has_perm(
            "submission.orga_update_submission", self.request.event
        )

    @context
    @cached_property
    def can_accept_submissions(self):
        return self.request.event.submissions.filter(
            state=SubmissionStates.SUBMITTED
        ).exists() and self.request.user.has_perm(
            "submission.accept_or_reject_submission", self.request.event
        )

    @context
    @cached_property
    def can_see_all_reviews(self):
        return self.request.user.has_perm(
            "submission.list_all_review", self.request.event
        )

    @context
    @cached_property
    def max_review_count(self):
        return (
            self.request.event.submissions.all()
            .annotate(review_count=Count("reviews", distinct=True))
            .aggregate(Max("review_count"))
            .get("review_count__max")
        )

    @context
    @cached_property
    def submissions_reviewed(self):
        return Review.objects.filter(
            user=self.request.user, submission__event=self.request.event
        ).values_list("submission_id", flat=True)

    @context
    @cached_property
    def show_submission_types(self):
        return self.request.event.submission_types.count() > 1

    @context
    @cached_property
    def short_questions(self):
        return questions_for_user(self.request.event, self.request.user).filter(
            target=QuestionTarget.SUBMISSION, variant__in=QuestionVariant.short_answers
        )

    @context
    @cached_property
    def independent_categories(self):
        return self.request.event.score_categories.filter(
            is_independent=True, active=True
        )

    @context
    @cached_property
    def show_tracks(self):
        return self.request.event.has_active_tracks

    @context
    @cached_property
    def reviews_open(self):
        return reviews_are_open(None, self.request.event)

    def get_table_kwargs(self):
        """Pass additional kwargs to the ReviewTable."""
        kwargs = super().get_table_kwargs()

        # Build exclude list for columns that shouldn't be shown
        exclude = []
        if not self.show_tracks:
            exclude.append("track")
        if not (
            bool(self.filter_form.cleaned_data.get("tags"))
            if hasattr(self.filter_form, "cleaned_data")
            else False
        ):
            exclude.append("tags")
        if not self.show_submission_types:
            exclude.append("submission_type")

        kwargs.update(
            {
                "can_see_all_reviews": self.can_see_all_reviews,
                "is_reviewer": self.request.user.has_perm(
                    "submission.create_review", self.request.event
                )
                or self.submissions_reviewed,
                "can_view_speakers": self.request.user.has_perm(
                    "person.reviewer_list_speakerprofile", self.request.event
                ),
                "can_accept_submissions": self.can_accept_submissions,
                "independent_categories": self.independent_categories,
                "short_questions": list(self.short_questions),
                "aggregate_method": self.request.event.review_settings[
                    "aggregate_method"
                ],
                "request_user": self.request.user,
                "exclude": exclude,
            }
        )
        return kwargs

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        missing_reviews = unreviewed_submissions_for_user(
            self.request.event, self.request.user
        )
        # Do NOT use len() here! It yields a different result.
        result["missing_reviews"] = missing_reviews.count()
        result["next_submission"] = missing_reviews[0] if missing_reviews else None
        return result

    def get_pending(self, request):
        form = SubmissionStateChangeForm(request.POST)
        form.is_valid()
        return form.cleaned_data.get("pending")

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        total = {"accept": 0, "reject": 0, "error": 0}
        pending = self.get_pending(request)
        target_states = {
            "accept": SubmissionStates.ACCEPTED,
            "reject": SubmissionStates.REJECTED,
        }
        for key, value in request.POST.items():
            if not key.startswith("s-") or value not in target_states:
                continue
            code = key.strip("s-")
            try:
                submission = request.event.submissions.filter(
                    state=SubmissionStates.SUBMITTED
                ).get(code=code)
            except (Submission.DoesNotExist, ValueError):
                total["error"] += 1
                continue
            if not request.user.has_perm(
                "submission.accept_or_reject_submission", submission
            ):
                total["error"] += 1
                continue
            if pending:
                set_pending_state(submission, target_states[value])
            else:
                set_submission_state(
                    submission, target_states[value], person=request.user, orga=True
                )
            total[value] += 1
        if total["accept"] or total["reject"]:
            msg = str(
                _(
                    "Success! {accepted} proposals were accepted, {rejected} proposals were rejected."
                )
            ).format(accepted=total["accept"], rejected=total["reject"])
            if total["error"]:
                msg += " " + str(
                    _("We were unable to change the state of {count} proposals.")
                ).format(count=total["error"])
            messages.success(request, msg)
        else:
            messages.error(
                request,
                str(
                    _("We were unable to change the state of all {count} proposals.")
                ).format(count=total["error"]),
            )
        return super().get(request, *args, **kwargs)


class BulkReview(EventPermissionRequired, TemplateView):
    template_name = "orga/review/bulk.html"
    permission_required = "submission.create_review"
    paginate_by = None

    @context
    @cached_property
    def can_view_speakers(self):
        return self.request.user.has_perm(
            "person.reviewer_list_speakerprofile", self.request.event
        )

    @context
    @cached_property
    def filter_form(self):
        return SubmissionFilterForm(
            data=self.request.GET,
            event=self.request.event,
            prefix="filter",
            can_view_speakers=self.can_view_speakers,
        )

    @context
    @cached_property
    def submissions(self):
        submissions = reviewable_submissions_for_user(
            event=self.request.event, user=self.request.user
        ).with_sorted_speakers()
        if self.filter_form.is_valid():
            submissions = self.filter_form.filter_queryset(submissions)
        return submissions

    @context
    @cached_property
    def show_tracks(self):
        return self.request.event.has_active_tracks

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        missing_reviews = unreviewed_submissions_for_user(
            self.request.event, self.request.user
        )
        # Do NOT use len() here! It yields a different result.
        result["missing_reviews"] = missing_reviews.count()
        result["next_submission"] = missing_reviews[0] if missing_reviews else None
        return result

    @context
    @cached_property
    def categories(self):
        return (
            self.request.event.score_categories.all()
            .filter(active=True)
            .prefetch_related("limit_tracks", "scores")
        )

    @cached_property
    def _categories_by_track(self):
        result = defaultdict(list)
        for category in self.categories:
            for track in category.limit_tracks.all():
                result[track.pk].append(category)
            result[None].append(category)
        return result

    def _categories_for_submission(self, submission):
        return (
            self._categories_by_track[submission.track_id]
            if submission.track_id
            else []
        ) + self._categories_by_track[None]

    def _build_form(self, submission, instance=None, bind_data=False):
        form = ReviewForm(
            event=self.request.event,
            user=self.request.user,
            submission=submission,
            read_only=False,
            instance=instance,
            prefix=submission.code,
            categories=self._categories_for_submission(submission),
            data=(self.request.POST if bind_data else None),
            default_renderer=InlineFormRenderer,
        )
        # The default widget is the full MarkdownWidget with preview, editor row etc,
        # which is a lot of clutter when you can see hundreds of these fields on a
        # single page, so we are using a standard textarea here instead.
        form.fields["text"].widget = forms.Textarea(attrs={"rows": 2})
        return form

    def _build_row(self, submission, form, state="initial"):
        return {
            "submission": submission,
            "form": form,
            "score_fields": [
                form.get_score_field(category) for category in self.categories
            ],
            "state": state,
        }

    @context
    @cached_property
    def forms(self):
        own_reviews = {
            review.submission_id: review
            for review in self.request.event.reviews.filter(
                user=self.request.user, submission__in=self.submissions
            )
            .select_related("submission")
            .prefetch_related("scores", "scores__category")
        }
        categories = defaultdict(list)
        for category in self.categories:
            for track in category.limit_tracks.all():
                categories[track.pk].append(category)
            categories[None].append(category)
        return {
            submission.code: self._build_form(
                submission, instance=own_reviews.get(submission.pk)
            )
            for submission in self.submissions
        }

    @context
    @cached_property
    def table(self):
        return [
            self._build_row(submission, self.forms[submission.code])
            for submission in self.submissions
        ]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        submission_code = request.POST.get("_submission", "")
        submission = self.submissions.filter(code=submission_code).first()
        if not submission:
            if is_htmx(request):
                return HttpResponse(status=404)
            messages.error(request, phrases.base.error_saving_changes)
            return redirect(request.path)

        instance = (
            request.event.reviews.filter(user=request.user, submission=submission)
            .prefetch_related("scores", "scores__category")
            .first()
        )
        form = self._build_form(submission, instance=instance, bind_data=True)

        if form.is_valid():
            if form.has_changed():
                form.save()
            if not is_htmx(request):
                messages.success(request, phrases.base.saved)
                return redirect(request.path)
            row = self._build_row(submission, form, state="saved")
        else:
            if not is_htmx(request):
                messages.error(request, phrases.base.error_saving_changes)
                return redirect(request.path)
            row = self._build_row(submission, form, state="error")

        return render(
            request,
            "orga/review/bulk.html#bulk-review-row",
            {"row": row, "can_view_speakers": self.can_view_speakers},
        )


class BulkTagging(EventPermissionRequired, SubmissionListMixin, TemplateView):
    template_name = "orga/review/bulk_tag.html"
    permission_required = "submission.orga_update_submission"
    paginate_by = None
    usable_states = (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.REJECTED,
        SubmissionStates.CONFIRMED,
    )

    @context
    @cached_property
    def tag_form(self):
        return BulkTagForm(
            event=self.request.event,
            data=self.request.POST if self.request.method == "POST" else None,
        )

    @context
    @cached_property
    def submissions(self):
        return (
            self._get_base_queryset()
            .select_related("submission_type", "track")
            .prefetch_related("tags")
        )

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if not self.tag_form.is_valid():
            messages.error(request, phrases.base.error_saving_changes)
            return self.get(request, *args, **kwargs)

        tags = self.tag_form.cleaned_data["tags"]
        action = self.tag_form.cleaned_data["action"]
        submission_codes = [
            key.strip("s-")
            for key, value in request.POST.items()
            if key.startswith("s-") and value == "on"
        ]

        if not submission_codes:
            messages.warning(request, _("No proposals were selected."))
            return self.get(request, *args, **kwargs)

        submissions = self.submissions.filter(code__in=submission_codes)
        count = 0
        for submission in submissions:
            if action == "add":
                submission.tags.add(*tags)
            else:
                submission.tags.remove(*tags)
            count += 1

        if count:
            if action == "add":
                messages.success(
                    request, _("Added tags to {count} proposals.").format(count=count)
                )
            else:
                messages.success(
                    request,
                    _("Removed tags from {count} proposals.").format(count=count),
                )

        # Redirect to next_url if available, otherwise stay on page
        next_url = get_next_url(request)
        if next_url:
            return redirect(next_url)
        return self.get(request, *args, **kwargs)


class ReviewViewMixin:
    @context
    @cached_property
    def submission(self):
        return get_object_or_404(
            review_view_submissions(self.request.event),
            code__iexact=self.kwargs["code"],
        )

    @cached_property
    def object(self):
        return (
            self.submission.reviews.select_related("user")
            .filter(user=self.request.user)
            .first()
        )

    def get_object(self):
        return self.object

    def get_permission_object(self):
        return self.submission

    @context
    @cached_property
    def read_only(self):
        if self.submission.speakers.filter(user=self.request.user).exists():
            return True
        if self.object and not self.object._state.adding:
            return not self.request.user.has_perm(
                "submission.update_review", self.get_object()
            )
        return not self.request.user.has_perm(
            "submission.review_submission", self.get_object() or self.submission
        )


class ReviewSubmission(ReviewViewMixin, PermissionRequired, CreateOrUpdateView):
    form_class = ReviewForm
    model = Review
    template_name = "orga/submission/review.html"
    permission_required = "submission.view_reviews_submission"
    write_permission_required = "submission.review_submission"
    extra_forms_signal = "pretalx.orga.signals.review_form"

    @context
    @cached_property
    def is_speaker(self):
        return is_speaker(self.request.user, self.submission)

    @cached_property
    def review_questions(self):
        return list(self.qform.queryset)

    @context
    @cached_property
    def review_display(self):
        if self.object and not self.is_speaker:
            review = self.object
            return {
                "score": review.display_score,
                "scores": self.get_scores_for_review(review),
                "text": review.text,
                "user": self.request.user,
                "answers": [
                    review.answers.filter(question=question).first()
                    for question in self.review_questions
                ],
            }

    @context
    @cached_property
    def has_anonymised_review(self):
        return (
            self.request.event.review_phases.filter(
                can_see_speaker_names=False
            ).exists()
            or self.request.event.teams.filter(force_hide_speaker_names=True).exists()
        )

    @context
    @cached_property
    def score_categories(self):
        return self.submission.score_categories

    def get_scores_for_review(self, review):
        scores = []
        score_format = self.request.event.review_settings.get(
            "score_format", "words_numbers"
        )
        review_scores = {score.category: score for score in review.scores.all()}
        for category in self.score_categories:
            score = review_scores.get(category)
            if score:
                scores.append(score.format(score_format))
            else:
                scores.append("×")
        return scores

    @context
    @cached_property
    def reviews(self):
        if self.is_speaker:
            return []
        return [
            {
                "score": review.display_score,
                "scores": self.get_scores_for_review(review),
                "text": review.text,
                "user": review.user,
                "delete_url": review.urls.delete,
                "answers": [
                    review.answers.filter(question=question).first()
                    for question in self.review_questions
                ],
            }
            for review in self.submission.reviews.exclude(
                pk=(self.object.pk if self.object else None)
            ).prefetch_related("scores", "scores__category")
        ]

    @context
    @cached_property
    def qform(self):
        return QuestionsForm(
            target="reviewer",
            event=self.request.event,
            data=(self.request.POST if self.request.method == "POST" else None),
            files=(self.request.FILES if self.request.method == "POST" else None),
            speaker=self.request.user,
            review=self.object,
            read_only=self.read_only,
        )

    @context
    @cached_property
    def tags_form(self):
        if not self.request.event.tags.exists():
            return
        if not self.request.user.has_perm(
            "submission.orga_update_submission", self.request.event
        ):
            phase = self.request.event.active_review_phase
            if not phase or phase.can_tag_submissions == "never":
                return
        return TagsForm(
            event=self.request.event,
            instance=self.submission,
            data=(self.request.POST if self.request.method == "POST" else None),
            read_only=self.read_only,
        )

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["done"] = self.request.user.reviews.filter(
            submission__event=self.request.event
        ).count()
        result["total_reviews"] = (
            unreviewed_submissions_for_user(
                self.request.event, self.request.user
            ).count()
            + result["done"]
        )
        if result["total_reviews"]:
            result["percentage"] = int(result["done"] * 100 / result["total_reviews"])

        result["filtered_reviewer_answers"] = self.submission.reviewer_answers.filter(
            question__in=questions_for_user(self.submission.event, self.request.user)
        )
        return result

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        kwargs["user"] = self.request.user
        kwargs["submission"] = self.submission
        kwargs["read_only"] = self.read_only
        kwargs["categories"] = self.score_categories
        return kwargs

    def form_valid(self, form):
        if not self.qform.is_valid():
            messages.error(self.request, phrases.base.error_saving_changes)
            return super().form_invalid(form)
        if self.tags_form and not self.tags_form.is_valid():
            messages.error(self.request, phrases.base.error_saving_changes)
            return super().form_invalid(form)
        result = super().form_valid(form)
        self.qform.review = form.instance
        self.qform.save()
        if self.tags_form:
            self.tags_form.save()
        return result

    def post(self, request, *args, **kwargs):
        action = self.request.POST.get("review_submit") or "save"
        if action == "abstain":
            Review.objects.get_or_create(
                user=self.request.user, submission=self.submission
            )
            return redirect(self.get_success_url())
        if action == "skip_for_now":
            key = f"{self.request.event.slug}_ignored_reviews"
            ignored_submissions = self.request.session.get(key) or []
            ignored_submissions.append(self.submission.pk)
            self.request.session[key] = ignored_submissions
            return redirect(self.get_success_url())
        return super().post(request, *args, **kwargs)

    def get_success_url(self) -> str:
        action = self.request.POST.get("review_submit")
        if action == "save":
            return self.submission.orga_urls.reviews
            # save, skip_for_now, save_and_next

        key = f"{self.request.event.slug}_ignored_reviews"
        ignored_submissions = self.request.session.get(key) or []
        unreviewed = unreviewed_submissions_for_user(
            self.request.event, self.request.user
        )
        next_submission = unreviewed.exclude(pk__in=ignored_submissions).first()
        if not next_submission:
            # Nothing left under the current ignore list. Reset it (keep only
            # the just-skipped submission so we don't bounce straight back to
            # it) and retry — but only if the reset actually changes the
            # exclusion set, otherwise the second query would be identical.
            new_ignored = [self.submission.pk] if action == "skip_for_now" else []
            if set(new_ignored) != set(ignored_submissions):
                next_submission = unreviewed.exclude(pk__in=new_ignored).first()
            ignored_submissions = new_ignored
        self.request.session[key] = ignored_submissions
        if next_submission:
            return next_submission.orga_urls.reviews
        messages.success(self.request, _("You have no proposals left to review!"))
        return self.request.event.orga_urls.reviews


class ReviewSubmissionDelete(
    PermissionRequired, ReviewViewMixin, ActionConfirmMixin, TemplateView
):
    template_name = "orga/submission/review_delete.html"
    permission_required = "submission.delete_review"

    @cached_property
    def object(self):
        return self.submission.reviews.filter(pk=self.kwargs["pk"]).first()

    def get_object(self):
        return self.object

    def get_permission_object(self):
        return self.object

    def action_object_name(self):
        if self.object and self.object.user != self.request.user:
            return _("{name}'s review").format(name=self.object.user.get_display_name())
        return _("Your review")

    @property
    def action_back_url(self):
        return self.submission.orga_urls.reviews

    def post(self, request, *args, **kwargs):
        self.object.answers.all().delete()
        self.object.delete(log_kwargs={"person": self.request.user, "orga": True})
        messages.success(request, _("The review has been deleted."))
        return redirect(self.submission.orga_urls.reviews)


class RegenerateDecisionMails(
    EventPermissionRequired, ActionConfirmMixin, TemplateView
):
    permission_required = "submission.orga_update_submission"
    action_title = _("Regenerate decision emails")
    action_confirm_label = _("Regenerate decision emails")
    action_confirm_color = "success"
    action_confirm_icon = "envelope"
    action_object_name = ""

    def get_queryset(self):
        return (
            self.request.event.submissions.filter(
                state__in=[SubmissionStates.ACCEPTED, SubmissionStates.REJECTED],
                speakers__isnull=False,
            )
            .with_sorted_speakers()
            .distinct()
        )

    @context
    @cached_property
    def count(self):
        return self.get_queryset().aggregate(total=Count("speakers"))["total"] or 0

    def action_text(self):
        return _(
            "Do you really want to regenerate %(count)s acceptance and rejection emails? "
            "They will be placed in the outbox and not sent out directly."
        ) % {"count": self.count}

    @property
    def action_back_url(self):
        return self.request.event.orga_urls.reviews

    def post(self, request, **kwargs):
        for submission in self.get_queryset():
            send_state_mail(submission)
        messages.success(
            request,
            _("{count} emails were generated and placed in the outbox.").format(
                count=self.count
            ),
        )
        return redirect(self.request.event.orga_urls.reviews)


class ReviewAssignment(EventPermissionRequired, FormView):
    template_name = "orga/review/assignment.html"
    permission_required = "event.update_event"

    @cached_property
    def form_type(self):
        direction = self.request.GET.get("direction")
        if not direction or direction not in ("reviewer", "submission"):
            return "reviewer"
        return direction

    @context
    def direction(self):
        return self.form_type

    @context
    @cached_property
    def direction_form(self):
        return DirectionForm(self.request.GET)

    @context
    @cached_property
    def review_teams(self):
        return event_reviewer_teams(self.request.event)

    @context
    def tablist(self):
        return {
            "group": _("Assign reviewer teams"),
            "individual": _("Assign reviewers individually"),
        }

    @context
    @cached_property
    def review_mapping(self):
        reviews = Review.objects.filter(
            submission__event=self.request.event
        ).values_list("user_id", "submission_id")
        assignments = Submission.assigned_reviewers.through.objects.filter(
            submission__event=self.request.event
        ).values_list("submission_id", "user_id")

        reviewer_to_submissions = defaultdict(list)
        submission_to_reviewers = defaultdict(list)
        reviewer_to_assigned_submissions = defaultdict(list)
        submission_to_assigned_reviewers = defaultdict(list)

        for user_id, submission_id in reviews:
            reviewer_to_submissions[user_id].append(submission_id)
            submission_to_reviewers[submission_id].append(user_id)

        for submission_id, reviewer_id in assignments:
            submission_to_assigned_reviewers[submission_id].append(reviewer_id)
            reviewer_to_assigned_submissions[reviewer_id].append(submission_id)

        submission_code_to_id = dict(
            self.request.event.submissions.values_list("code", "id")
        )

        reviewer_code_to_id = dict(
            self.request.event.reviewers.values_list("code", "id")
        )

        return {
            "reviewer_to_submissions": reviewer_to_submissions,
            "submission_to_reviewers": submission_to_reviewers,
            "reviewer_to_assigned_submissions": reviewer_to_assigned_submissions,
            "submission_to_assigned_reviewers": submission_to_assigned_reviewers,
            "submission_code_to_id": submission_code_to_id,
            "reviewer_code_to_id": reviewer_code_to_id,
        }

    def get_form(self):
        if self.form_type == "submission":
            form_class = ReviewerForProposalForm
        else:
            form_class = ProposalForReviewerForm
        kwargs = {}
        if is_htmx(self.request):
            field_code = self.request.POST.get("_field", "")
            if self.form_type == "submission":
                kwargs["submissions"] = self.request.event.submissions.filter(
                    code=field_code
                )
            else:
                kwargs["reviewers"] = self.request.event.reviewers.filter(
                    code=field_code
                )
        return form_class(
            self.request.POST if self.request.method == "POST" else None,
            files=self.request.FILES if self.request.method == "POST" else None,
            event=self.request.event,
            prefix=self.form_type,
            review_mapping=self.review_mapping,
            **kwargs,
        )

    def form_valid(self, form):
        form.save()
        if is_htmx(self.request):
            return HttpResponse(status=204)
        messages.success(self.request, phrases.base.saved)
        return redirect(self.request.event.orga_urls.review_assignments)

    def form_invalid(self, form):
        if is_htmx(self.request):
            field_code = self.request.POST.get("_field", "")
            return render(
                self.request,
                "orga/review/assignment.html#assignment-field",
                {
                    "form_field": form[field_code],
                    "field_code": field_code,
                    "direction": self.form_type,
                },
            )
        return super().form_invalid(form)


class ReviewAssignmentImport(EventPermissionRequired, FormView):
    template_name = "orga/review/assignment-import.html"
    permission_required = "event.update_event"
    form_class = ReviewAssignImportForm

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["event"] = self.request.event
        return result

    @context
    def submit_buttons(self):
        return [Button(label=pgettext_lazy("action: import data", "Import"))]

    @transaction.atomic
    def form_valid(self, form):
        form.save()
        messages.success(self.request, _("The reviewers were assigned successfully."))
        return redirect(self.request.event.orga_urls.review_assignments)


class ReviewExport(EventPermissionRequired, FormView):
    permission_required = "event.update_event"
    template_name = "orga/review/export.html"
    form_class = ReviewExportForm

    @context
    def tablist(self):
        return {"custom": _("CSV/JSON exports"), "api": _("API")}

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["event"] = self.request.event
        result["user"] = self.request.user
        return result

    def form_valid(self, form):
        result = form.export_data()
        if not result:
            messages.success(self.request, phrases.orga.no_data_to_export)
            return redirect(self.request.path)
        return result

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["api_buttons"] = api_buttons(self.request.event)
        return context
