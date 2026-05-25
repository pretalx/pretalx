# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: s-light


from django.contrib import messages
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView, View
from django_context_decorator import context

from pretalx.agenda.recording import get_recording
from pretalx.cfp.views.event import EventPageMixin
from pretalx.common.exceptions import SubmissionError
from pretalx.common.text.phrases import phrases
from pretalx.common.views.mixins import PermissionRequired, SocialMediaCardMixin
from pretalx.common.views.redirect import build_login_redirect_url
from pretalx.schedule.domain.ical import get_submission_ical
from pretalx.submission.domain.queries.feedback import feedback_for_speaker
from pretalx.submission.domain.queries.submission import (
    annotate_submission_signup_status,
    submissions_for_user,
)
from pretalx.submission.domain.signup import (
    can_user_signup,
    cancel_signup,
    create_signup,
    get_confirmed_signup_for_user,
)
from pretalx.submission.interfaces.forms import FeedbackForm
from pretalx.submission.models import Submission, SubmissionStates
from pretalx.submission.rules import is_speaker


class TalkMixin(PermissionRequired):
    permission_required = "submission.view_public_submission"
    prefetches = ("slots", "resources")

    def get_queryset(self):
        queryset = (
            self.request.event.submissions.prefetch_related(*self.prefetches)
            .with_sorted_speakers()
            .select_related("submission_type", "track", "event")
        )
        if self.request.event.get_feature_flag("attendee_signup"):
            queryset = annotate_submission_signup_status(
                queryset, self.request.event.current_schedule
            )
        return queryset

    @cached_property
    def object(self):
        return get_object_or_404(self.get_queryset(), code__iexact=self.kwargs["slug"])

    @context
    @cached_property
    def submission(self):
        return self.object

    def get_permission_object(self):
        return self.submission

    @context
    @cached_property
    def scheduling_information_visible(self):
        return self.request.user.has_perm(
            "submission.view_scheduling_details_submission", self.submission
        )

    @context
    @cached_property
    def hide_speaker_links(self):
        return not self.scheduling_information_visible


class TalkView(TalkMixin, TemplateView):
    template_name = "agenda/talk.html"

    @context
    @cached_property
    def show_fav_button(self):
        return self.request.user.has_perm("schedule.list_schedule", self.request.event)

    @cached_property
    def recording(self):
        return get_recording(self.submission)

    @context
    def is_speaker(self):
        return is_speaker(self.request.user, self.submission)

    @context
    def recording_iframe(self):
        return self.recording.get("iframe")

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        csp_update = {"frame-src": self.recording.get("csp_header")}
        response._csp_update = csp_update  # noqa: SLF001 -- django-csp convention
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        schedule = (
            self.request.event.current_schedule or self.request.event.wip_schedule
        )
        if not self.request.user.has_perm("schedule.view_schedule", schedule):
            ctx["speakers"] = self.submission.sorted_speakers
            return ctx
        ctx["talk_slots"] = (
            schedule.talks.filter(submission=self.submission, room__isnull=False)
            .select_related("room")
            .order_by("start")
        )
        ctx["speakers"] = list(
            self.submission.sorted_speakers.prefetch_related(
                Prefetch(
                    "submissions",
                    queryset=schedule.slots.exclude(pk=self.submission.pk),
                    to_attr="other_submissions",
                )
            )
        )
        return ctx

    @context
    @cached_property
    def signup_status(self):
        if not self.request.event.get_feature_flag("attendee_signup"):
            return None
        return self.submission.signup_status

    @context
    @cached_property
    def user_signup(self):
        if not self.signup_status:
            return None
        return get_confirmed_signup_for_user(self.submission, self.request.user)

    @context
    @cached_property
    def signup_allowed_for_user(self):
        if not self.signup_status:
            return False
        return can_user_signup(self.submission, self.request.user)

    @context
    @cached_property
    def signup_login_url(self):
        return build_login_redirect_url(
            self.request.event, self.submission.urls.public, fragment="signup"
        )

    @context
    @cached_property
    def submission_description(self):
        return (
            self.submission.abstract
            or self.submission.description
            or _("The session “{title}” at {event}").format(
                title=self.submission.title, event=self.request.event.name
            )
        )

    @cached_property
    def _split_answers(self):
        regular, icon = [], []
        for answer in self.submission.public_answers:
            (icon if answer.question.show_icon else regular).append(answer)
        return regular, icon

    @context
    @cached_property
    def answers(self):
        return self._split_answers[0]

    @context
    @cached_property
    def icon_answers(self):
        return self._split_answers[1]


class TalkReviewView(TalkView):
    template_name = "agenda/talk.html"

    @context
    @cached_property
    def show_fav_button(self):
        return False

    def has_permission(self):
        return self.request.event.get_feature_flag("submission_public_review")

    @cached_property
    def object(self):
        return get_object_or_404(
            Submission.all_objects.filter(event=self.request.event),
            review_code=self.kwargs["slug"],
            state__in=SubmissionStates.public_review_states,
        )

    @context
    def hide_visibility_warning(self):
        return True

    @context
    def hide_speaker_links(self):
        return True


class SingleICalView(EventPageMixin, TalkMixin, View):
    prefetches = ("slots",)

    def get(self, request, event, **kwargs):
        code = self.submission.code
        slots = self.submission.slots.filter(
            schedule=self.request.event.current_schedule, is_visible=True
        )
        return HttpResponse(
            get_submission_ical(self.submission, slots).serialize(),
            content_type="text/calendar",
            headers={
                "Content-Disposition": f'attachment; filename="{request.event.slug}-{code}.ics"'
            },
        )


class FeedbackView(TalkMixin, FormView):
    form_class = FeedbackForm
    permission_required = "submission.view_feedback_page_submission"

    @context
    @cached_property
    def talk(self):
        return self.submission

    @context
    @cached_property
    def can_give_feedback(self):
        return self.request.user.has_perm(
            "submission.give_feedback_submission", self.talk
        )

    @context
    @cached_property
    def speakers(self):
        return self.talk.sorted_speakers

    @cached_property
    def is_speaker(self):
        return any(s.user_id == self.request.user.id for s in self.speakers)

    @cached_property
    def template_name(self):
        if self.is_speaker:
            return "agenda/feedback.html"
        return "agenda/feedback_form.html"

    @context
    @cached_property
    def feedback(self):
        if not self.is_speaker:
            return None
        return feedback_for_speaker(self.talk, self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["talk"] = self.talk
        return kwargs

    def form_valid(self, form):
        if not self.can_give_feedback:
            return super().form_invalid(form)
        result = super().form_valid(form)
        form.save()
        messages.success(self.request, phrases.agenda.feedback_success)
        return result

    def get_success_url(self):
        return self.submission.urls.public


class TalkSocialMediaCard(SocialMediaCardMixin, TalkView):
    def get_image(self):
        return self.submission.image


class SignupMixin(TalkMixin):
    def get_queryset(self):
        return submissions_for_user(self.request.event, self.request.user)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(
                build_login_redirect_url(
                    request.event, self.submission.urls.public, fragment="signup"
                )
            )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return redirect(f"{self.submission.urls.public}#signup")


class SignupView(SignupMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            create_signup(self.submission, user=request.user)
        except SubmissionError as exc:
            messages.error(request, str(exc))
            return redirect(f"{self.submission.urls.public}#signup")
        return redirect(f"{self.submission.urls.public}#signup-success")


class SignupCancelView(SignupMixin, View):
    def post(self, request, *args, **kwargs):
        cancel_signup(self.submission, user=request.user)
        messages.success(request, _("Your signup has been cancelled."))
        return redirect(self.submission.urls.public)
