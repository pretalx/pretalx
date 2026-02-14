# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretalx.common.text.phrases import phrases
from pretalx.orga.forms.export import ExportForm
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import SubmissionStates


class SpeakerExportForm(ExportForm):
    target = forms.ChoiceField(
        required=True,
        label=_("Target group"),
        choices=(
            ("all", phrases.base.all_choices),
            ("accepted", _("Just speakers with accepted and confirmed proposals")),
        ),
        widget=forms.RadioSelect,
        initial="all",
    )

    class Meta:
        model = SpeakerProfile
        model_fields = ["name", "biography"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"] = forms.BooleanField(
            required=False,
            label=_("Email"),
        )
        self.fields["submission_ids"] = forms.BooleanField(
            required=False,
            label=_("Proposal IDs"),
            help_text=phrases.orga.proposal_id_help_text,
        )
        self.fields["submission_titles"] = forms.BooleanField(
            required=False,
            label=_("Proposal titles"),
        )
        self.fields["avatar"] = forms.BooleanField(
            required=False,
            label=_("Picture"),
            help_text=_("The link to the speaker’s profile picture"),
        )

    @cached_property
    def questions(self):
        return self.event.questions.filter(
            target="speaker", active=True
        ).prefetch_related("answers", "answers__speaker", "options")

    @cached_property
    def filename(self):
        return f"{self.event.slug}_speakers"

    @cached_property
    def export_field_names(self):
        return [
            *self.Meta.model_fields,
            "email",
            "avatar",
            "submission_ids",
            "submission_titles",
        ]

    def get_queryset(self):
        target = self.cleaned_data.get("target")
        queryset = self.event.submitters
        if target != "all":
            queryset = queryset.filter(
                submissions__in=self.event.submissions.filter(
                    state__in=[SubmissionStates.ACCEPTED, SubmissionStates.CONFIRMED]
                )
            ).distinct()
        return queryset.select_related("user", "profile_picture").order_by("code")

    def _get_name_value(self, obj):
        return obj.get_display_name()

    def _get_avatar_value(self, obj):
        return obj.avatar_url

    def _get_email_value(self, obj):
        return obj.user.email

    def _get_submission_ids_value(self, obj):
        return list(obj.submissions.values_list("code", flat=True))

    def _get_submission_titles_value(self, obj):
        return list(obj.submissions.values_list("title", flat=True))

    def get_answer(self, question, obj):
        return question.answers.filter(speaker=obj).first()
