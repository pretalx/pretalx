# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: s-light


from django.contrib import messages
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView, View
from django_context_decorator import context

from pretalx.agenda.signals import register_recording_provider
from pretalx.cfp.views.event import EventPageMixin
from pretalx.common.text.phrases import phrases
from pretalx.common.views.mixins import PermissionRequired, SocialMediaCardMixin
from pretalx.schedule.ical import get_submission_ical
from pretalx.schedule.models import TalkSlot
from pretalx.submission.forms import FeedbackForm
from pretalx.submission.models import Submission, SubmissionStates


class TalkMixin(PermissionRequired):
    permission_required = "submission.view_public_submission"
    prefetches = ("slots", "resources", "speakers")

    def get_queryset(self):
        return self.request.event.submissions.prefetch_related(
            *self.prefetches
        ).select_related("submission_type", "track", "event")

    @cached_property
    def object(self):
        return get_object_or_404(
            self.get_queryset(),
            code__iexact=self.kwargs["slug"],
        )

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

    @cached_property
    def recording(self):
        for __, response in register_recording_provider.send_robust(self.request.event):
            if (
                response
                and not isinstance(response, Exception)
                and getattr(response, "get_recording", None)
            ):
                recording = response.get_recording(self.submission)
                if recording and recording["iframe"]:
                    return recording
        return {}

    @context
    def recording_iframe(self):
        return self.recording.get("iframe")

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        csp_update = {"frame-src": self.recording.get("csp_header")}
        response._csp_update = csp_update
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        schedule = (
            self.request.event.current_schedule or self.request.event.wip_schedule
        )
        if not self.request.user.has_perm("schedule.view_schedule", schedule):
            return ctx
        qs = (
            schedule.talks.filter(room__isnull=False).select_related("room")
            if schedule
            else TalkSlot.objects.none()
        )
        ctx["talk_slots"] = (
            qs.filter(submission=self.submission)
            .order_by("start")
            .select_related("room")
        )
        result = []
        other_slots = (
            schedule.talks.exclude(submission_id=self.submission.pk).filter(
                is_visible=True
            )
            if schedule
            else TalkSlot.objects.none()
        )

        other_submissions = self.request.event.submissions.filter(
            slots__in=other_slots
        ).select_related("event")
        speakers = (
            self.submission.speakers.all()
            .with_profiles(self.request.event)
            .prefetch_related(
                Prefetch(
                    "submissions",
                    queryset=other_submissions,
                    to_attr="other_submissions",
                )
            )
        )
        for speaker in speakers:
            speaker.talk_profile = speaker.event_profile(event=self.request.event)
            result.append(speaker)
        ctx["speakers"] = result
        return ctx

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

    @context
    @cached_property
    def answers(self):
        all_answers = self.submission.public_answers
        regular_answers = []
        icon_answers = []

        for answer in all_answers:
            if answer.question.show_icon:
                icon_answers.append(answer)
            else:
                regular_answers.append(answer)

        return regular_answers

    @context
    @cached_property
    def icon_answers(self):
        all_answers = self.submission.public_answers
        icon_answers = []

        for answer in all_answers:
            if answer.question.show_icon:
                icon_answers.append(answer)

        return icon_answers


class TalkReviewView(TalkView):
    template_name = "agenda/talk.html"

    def has_permission(self):
        return self.request.event.get_feature_flag("submission_public_review")

    @cached_property
    def object(self):
        return get_object_or_404(
            Submission.all_objects.filter(event=self.request.event),
            review_code=self.kwargs["slug"],
            state__in=[
                SubmissionStates.SUBMITTED,
                SubmissionStates.DRAFT,
                SubmissionStates.ACCEPTED,
                SubmissionStates.CONFIRMED,
            ],
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
        return self.talk.speakers.all()

    @cached_property
    def is_speaker(self):
        return self.request.user in self.speakers

    @cached_property
    def template_name(self):
        if self.is_speaker:
            return "agenda/feedback.html"
        return "agenda/feedback_form.html"

    @context
    @cached_property
    def feedback(self):
        if not self.is_speaker:
            return
        return self.talk.feedback.filter(
            Q(speaker=self.request.user) | Q(speaker__isnull=True)
        ).select_related("speaker")

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
