# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: luto

import io
from collections import defaultdict

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import Storage
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.views.decorators.cache import cache_page
from django.views.generic import DetailView, ListView, TemplateView
from django_context_decorator import context

from pretalx.common.text.path import safe_filename
from pretalx.common.views.mixins import (
    EventPermissionRequired,
    Filterable,
    PermissionRequired,
    SocialMediaCardMixin,
)
from pretalx.person.models import SpeakerProfile
from pretalx.schedule.ical import get_speaker_ical
from pretalx.submission.models import QuestionTarget, QuestionVariant


class SpeakerList(EventPermissionRequired, Filterable, ListView):
    context_object_name = "speakers"
    template_name = "agenda/speakers.html"
    permission_required = "schedule.list_schedule"
    default_filters = ("user__name__icontains",)

    def get_queryset(self):
        qs = self.request.event.speakers.select_related(
            "user", "event", "profile_picture"
        ).order_by("user__name")
        qs = self.filter_queryset(qs)

        speaker_mapping = defaultdict(list)
        for talk in self.request.event.talks.all():
            for speaker in talk.sorted_speakers:
                speaker_mapping[speaker.pk].append(talk)

        for speaker in qs:
            speaker.visible_talks = speaker_mapping[speaker.pk]
        return qs


class SpeakerView(PermissionRequired, TemplateView):
    template_name = "agenda/speaker.html"
    permission_required = "person.view_speakerprofile"
    slug_field = "code"

    @context
    @cached_property
    def speaker(self):
        return (
            SpeakerProfile.objects.filter(
                event=self.request.event, code__iexact=self.kwargs["code"]
            )
            .select_related("user", "event", "profile_picture")
            .first()
        )

    def get_permission_object(self):
        return self.speaker

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        answers = (
            self.speaker.answers.filter(
                question__is_public=True,
                question__event=self.request.event,
                question__target=QuestionTarget.SPEAKER,
            )
            .select_related("question")
            .order_by("question__position")
        )
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
        return context


class SpeakerRedirect(DetailView):
    model = SpeakerProfile

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
        return (
            SpeakerProfile.objects.filter(
                event=self.request.event, code__iexact=self.kwargs["code"]
            )
            .select_related("user", "event")
            .first()
        )

    def get(self, request, event, *args, **kwargs):
        if not self.request.event.current_schedule:
            raise Http404
        speaker = self.get_object()
        cal = get_speaker_ical(request.event, speaker)
        try:
            speaker_name = Storage().get_valid_name(name=speaker.get_display_name())
        except SuspiciousFileOperation:
            speaker_name = Storage().get_valid_name(name=speaker.code)
        return HttpResponse(
            cal.serialize(),
            content_type="text/calendar",
            headers={
                "Content-Disposition": f'attachment; filename="{request.event.slug}-{safe_filename(speaker_name)}.ics"'
            },
        )


class SpeakerSocialMediaCard(SocialMediaCardMixin, SpeakerView):
    def get_image(self):
        if self.request.event.cfp.request_avatar:
            return self.speaker.avatar


@cache_page(60 * 60)
def empty_avatar_view(request, event):
    # cached for an hour
    color = request.event.primary_color or settings.DEFAULT_EVENT_PRIMARY_COLOR
    avatar_template = f"""<svg
   xmlns="http://www.w3.org/2000/svg"
   viewBox="0 0 100 100">
  <g>
    <path
       id="body"
       d="m 2,98 h 96 0 c 0,0 6,-65 -48,-52 c 0,0 -54,-10 -48,52"
       style="fill:none;stroke:{color};stroke-width:1.6;stroke-linecap:butt;stroke-linejoin:round;stroke-miterlimit:4;stroke-dasharray:2.1, 2.1;stroke-dashoffset:0;stroke-opacity:0.87" />
    <ellipse
       ry="27"
       rx="27"
       cy="28"
       cx="50"
       id="heady"
       style="fill:#ffffff;stroke:{color};stroke-width:1.3;stroke-linecap:butt;stroke-linejoin:round;stroke-miterlimit:4;stroke-dasharray:6.5, 8;stroke-dashoffset:4;stroke-opacity:0.87" />
  </g>
</svg>"""
    return FileResponse(
        io.BytesIO(avatar_template.encode()),
        as_attachment=True,
        content_type="image/svg+xml",
    )
