# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: luto

from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import Storage
from django.db.models import Prefetch
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.views.generic import DetailView, ListView, TemplateView
from django_context_decorator import context

from pretalx.common.views.mixins import (
    EventPermissionRequired,
    PermissionRequired,
    SocialMediaCardMixin,
)
from pretalx.person.domain.queries.profile import speakers_for_event
from pretalx.person.models import SpeakerProfile
from pretalx.schedule.domain.ical import get_speaker_ical
from pretalx.schedule.interfaces.responses import CalendarResponse
from pretalx.submission.domain.queries.question import public_answers_for_speaker
from pretalx.submission.domain.queries.submission import (
    signed_up_submission_codes,
    talks_for_event,
)
from pretalx.submission.models import QuestionVariant


class SpeakerList(EventPermissionRequired, ListView):
    context_object_name = "speakers"
    template_name = "agenda/speakers.html"
    permission_required = "schedule.list_schedule"

    def get_queryset(self):
        event = self.request.event
        qs = (
            speakers_for_event(event)
            .order_by(Lower("effective_name"))
            .prefetch_related(
                Prefetch(
                    "submissions",
                    queryset=talks_for_event(event),
                    to_attr="visible_talks",
                )
            )
        )
        if query := self.request.GET.get("q"):
            qs = qs.filter(effective_name__icontains=query)
        return qs


class SpeakerView(PermissionRequired, TemplateView):
    template_name = "agenda/speaker.html"
    permission_required = "person.view_speakerprofile"
    slug_field = "code"

    @context
    @cached_property
    def speaker(self):
        return self.request.event.submitters.filter(
            code__iexact=self.kwargs["code"]
        ).first()

    def get_permission_object(self):
        return self.speaker

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        answers = public_answers_for_speaker(self.speaker)
        short_answers = []
        long_answers = []
        icon_answers = []
        for answer in answers:
            if answer.question.variant in QuestionVariant.short_answers:
                if answer.question.show_icon:
                    icon_answers.append(answer)
                else:
                    short_answers.append(answer)
            else:
                long_answers.append(answer)
        context["short_answers"] = short_answers
        context["long_answers"] = long_answers
        context["icon_answers"] = icon_answers
        context["show_avatar"] = (
            self.speaker.avatar_url and self.request.event.cfp.request_avatar
        )
        context["show_sidebar"] = (
            context["show_avatar"] or len(short_answers) or len(icon_answers)
        )
        context["signed_up_codes"] = signed_up_submission_codes(
            self.request.event, self.request.user
        )
        return context


class SpeakerRedirect(DetailView):
    model = SpeakerProfile

    def get_queryset(self):
        return SpeakerProfile.objects.select_related("event", "user")

    def dispatch(self, request, **kwargs):
        speaker = self.get_object()
        if speaker and self.request.user.has_perm(
            "person.view_speakerprofile", speaker
        ):
            return redirect(speaker.urls.public.full())
        raise Http404


class SpeakerTalksIcalView(PermissionRequired, DetailView):
    permission_required = "person.view_speakerprofile"
    slug_field = "code"

    def get_object(self, queryset=None):
        return self.request.event.submitters.filter(
            code__iexact=self.kwargs["code"]
        ).first()

    def get(self, request, event, *args, **kwargs):
        if not self.request.event.current_schedule:
            raise Http404
        speaker = self.get_object()
        cal = get_speaker_ical(request.event, speaker)
        try:
            speaker_name = Storage().get_valid_name(name=speaker.get_display_name())
        except SuspiciousFileOperation:
            speaker_name = Storage().get_valid_name(name=speaker.code)
        return CalendarResponse(cal, f"{request.event.slug}-{speaker_name}")


class SpeakerSocialMediaCard(SocialMediaCardMixin, SpeakerView):
    def get_image(self):
        if self.request.event.cfp.request_avatar:
            return self.speaker.avatar
