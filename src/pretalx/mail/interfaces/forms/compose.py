# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.renderers import TabularFormRenderer
from pretalx.common.forms.widgets import EnhancedSelectMultiple
from pretalx.common.text.phrases import phrases
from pretalx.event.domain.queries.team import event_reviewer_teams
from pretalx.mail.domain.compose import build_session_mail_task_data, send_team_mail
from pretalx.mail.domain.placeholders import get_available_placeholders
from pretalx.mail.interfaces.forms.template import MailTemplateForm
from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.interfaces.forms import SubmissionFilterForm


class WriteMailBaseForm(MailTemplateForm):
    skip_queue = forms.BooleanField(
        label=_("Send immediately"),
        required=False,
        help_text=_(
            "If you check this, the emails will be sent immediately, instead of being put in the outbox."
        ),
    )

    def __init__(self, *args, may_skip_queue=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not may_skip_queue:
            self.fields.pop("skip_queue", None)

    class Media:
        js = [forms.Script("orga/js/forms/placeholder.js", defer="")]
        css = {"all": ["orga/css/forms/email.css"]}


class WriteTeamsMailForm(WriteMailBaseForm):
    recipients = forms.MultipleChoiceField(
        label=_("Recipient groups"), required=False, widget=EnhancedSelectMultiple
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Placing reviewer emails in the outbox would lead to a **ton** of permission
        # issues: who is allowed to see them, who to edit/send them, etc.
        self.fields.pop("skip_queue")

        reviewer_teams = event_reviewer_teams(self.event)
        other_teams = self.event.teams.exclude(is_reviewer=True)
        if reviewer_teams and other_teams:
            self.fields["recipients"].choices = [
                (_("Reviewers"), [(team.pk, team.name) for team in reviewer_teams]),
                (_("Other teams"), [(team.pk, team.name) for team in other_teams]),
            ]
        else:
            self.fields["recipients"].choices = [
                (team.pk, team.name) for team in self.event.teams.all()
            ]

    def get_valid_placeholders(self, **kwargs):
        return get_available_placeholders(event=self.event, kwargs=["event", "user"])

    def get_recipients(self):
        recipients = self.cleaned_data.get("recipients")
        teams = self.event.teams.filter(pk__in=recipients)
        return User.objects.filter(is_active=True, teams__in=teams)

    @transaction.atomic
    def save(self):
        self.instance.is_auto_created = True
        template = super().save()
        return send_team_mail(
            template=template, event=self.event, users=self.get_recipients()
        )


class WriteSessionMailForm(SubmissionFilterForm, WriteMailBaseForm):
    default_renderer = TabularFormRenderer

    RECIPIENT_FILTER_FIELDS = (
        "state",
        "submission_type",
        "content_locale",
        "track",
        "tags",
        "question",
    )

    submissions = forms.MultipleChoiceField(
        required=False,
        label=_("Proposals"),
        help_text=_(
            "Select proposals that should receive the email regardless of the other filters."
        ),
        widget=EnhancedSelectMultiple(attrs={"placeholder": _("Proposals")}),
    )
    speakers = forms.ModelMultipleChoiceField(
        queryset=SpeakerProfile.objects.none(),
        required=False,
        label=phrases.schedule.speakers,
        help_text=_(
            "Select speakers that should receive the email regardless of the other filters."
        ),
        widget=EnhancedSelectMultiple(attrs={"placeholder": phrases.schedule.speakers}),
    )

    def __init__(self, *args, event, **kwargs):
        # SubmissionFilterForm consumes ``event`` from kwargs, but MailTemplateForm
        # also needs it. Pre-set self.event so MailTemplateForm's attribute
        # fallback can find it after the kwarg is consumed.
        self.event = event
        super().__init__(*args, event=event, **kwargs)
        initial = kwargs.get("initial", {})
        self.filter_search = initial.get("q")
        question = initial.get("question")
        if question:
            self.filter_question = self.event.questions.filter(pk=question).first()
            if self.filter_question:
                self.filter_option = self.filter_question.options.filter(
                    pk=initial.get("answer__options")
                ).first()
                self.filter_answer = initial.get("answer")
                self.filter_unanswered = initial.get("unanswered")
        self.fields["submissions"].choices = [
            (sub.code, sub.title) for sub in self.event.submissions.order_by("title")
        ]
        speakers_field = self.fields["speakers"]
        speakers_field.queryset = self.event.submitters.order_by("name")
        speakers_field.label_from_instance = lambda obj: obj.get_display_name()
        if len(self.event.locales) > 1:
            self.fields["subject"].help_text = _(
                "If you provide only one language, that language will be used for all emails. If you provide multiple languages, the best fit for each speaker will be used."
            )
        self.warnings = []

    @property
    def speaker_only_recipients(self):
        cleaned_data = getattr(self, "cleaned_data", None)
        if not cleaned_data or not cleaned_data.get("speakers"):
            return False
        has_submission_recipients = cleaned_data.get("submissions") or any(
            cleaned_data.get(key) for key in self.RECIPIENT_FILTER_FIELDS
        )
        return not has_submission_recipients

    def get_valid_placeholders(self, ignore_data=False):
        kwargs = ["event", "user", "submission", "slot"]
        if not self.event.current_schedule:
            kwargs.remove("slot")
        if not ignore_data and self.speaker_only_recipients:
            kwargs = [k for k in kwargs if k not in ("submission", "slot")]
        return get_available_placeholders(event=self.event, kwargs=kwargs)

    def clean(self):
        cleaned_data = super().clean()
        has_filters = any(cleaned_data.get(key) for key in self.RECIPIENT_FILTER_FIELDS)
        added_submissions = cleaned_data.get("submissions")
        added_speakers = cleaned_data.get("speakers")

        if not has_filters and not added_submissions and not added_speakers:
            raise forms.ValidationError(
                _(
                    "Please select at least one filter or specific proposals/speakers as recipients."
                )
            )

        if has_filters:
            submissions = (
                self.filter_queryset(self.event.submissions)
                .select_related("track", "submission_type", "event")
                .with_sorted_speakers()
            )
        else:
            submissions = self.event.submissions.none()

        if added_submissions:
            specific_submissions = (
                self.event.submissions.filter(code__in=added_submissions)
                .select_related("track", "submission_type", "event")
                .with_sorted_speakers()
            )
            submissions = submissions | specific_submissions

        result = []
        for submission in submissions:
            slots = submission.current_slots or []
            if slots:
                for slot in slots:
                    result.extend(
                        {"submission": submission, "slot": slot, "user": speaker.user}
                        for speaker in submission.sorted_speakers
                    )
            else:
                result.extend(
                    {"submission": submission, "user": speaker.user}
                    for speaker in submission.sorted_speakers
                )
        if added_speakers:
            result.extend({"user": speaker.user} for speaker in added_speakers)
        self._recipients = result
        return cleaned_data

    def get_recipients(self):
        return self._recipients

    def save_template_and_get_task_data(self):
        """Save the MailTemplate and return kwargs for task_create_mails_for_template."""
        self.instance.is_auto_created = True
        template = super().save()
        return build_session_mail_task_data(
            template=template,
            recipient_contexts=self.get_recipients(),
            skip_queue=self.cleaned_data.get("skip_queue", False),
        )

    def clean_question(self):
        return getattr(self, "filter_question", None)

    def clean_answer__options(self):
        return getattr(self, "filter_option", None)

    def clean_answer(self):
        return getattr(self, "filter_answer", None)

    def clean_unanswered(self):
        return getattr(self, "filter_unanswered", None)

    def clean_q(self):
        return getattr(self, "filter_search", None)
