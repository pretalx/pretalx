# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json

from django import forms
from django.http import HttpResponse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext as _n
from django.utils.translation import pgettext_lazy
from i18nfield.utils import I18nJSONEncoder

from pretalx.common.exporter import render_csv
from pretalx.common.forms.widgets import EnhancedSelectMultiple
from pretalx.common.text.phrases import phrases
from pretalx.person.models import SpeakerProfile
from pretalx.schedule.models import TalkSlot
from pretalx.submission.domain.queries.question import questions_for_user
from pretalx.submission.domain.queries.submission import (
    annotate_confirmed_signup_count,
    annotate_requires_signup,
    submissions_for_user,
)
from pretalx.submission.models import (
    QuestionTarget,
    Review,
    Submission,
    SubmissionStates,
)


class ExportForm(forms.Form):
    export_format = forms.ChoiceField(
        required=True,
        label=_("Export format"),
        help_text=_(
            "A CSV export can be opened directly in Excel and similar applications."
        ),
        choices=(("csv", _("CSV export")), ("json", _("JSON export"))),
        widget=forms.RadioSelect,
    )
    data_delimiter = forms.ChoiceField(
        required=False,
        label=_("Data delimiter"),
        help_text=_(
            "How do you want to separate data within a single cell (for example, multiple speakers in one session/multiple sessions for one speaker)?"
        ),
        choices=(("newline", _("Newline")), ("comma", _("Comma"))),
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, event=None, user=None, **kwargs):
        self.event = event
        self.user = user
        super().__init__(*args, **kwargs)
        self._build_model_fields()
        self._build_question_fields()
        if "data_delimiter" in self.fields:
            self.fields["data_delimiter"].widget.attrs["class"] = "hide-optional"

    @property
    def questions(self):
        raise NotImplementedError

    @property
    def filename(self):
        raise NotImplementedError

    @cached_property
    def question_field_names(self):
        return [f"question_{question.pk}" for question in self.questions]

    @cached_property
    def export_fields(self):
        return [
            forms.BoundField(self, self.fields[field], field)
            for field in self.export_field_names + self.question_field_names
        ]

    def _build_model_fields(self):
        for field in self.Meta.model_fields:
            self.fields[field] = forms.BooleanField(
                required=False,
                label=self.Meta.model._meta.get_field(field).verbose_name,
            )

    def _build_question_fields(self):
        for question in self.questions:
            self.fields[f"question_{question.pk}"] = forms.BooleanField(
                required=False,
                label=f"{phrases.base.quotation_open}{question.question}{phrases.base.quotation_close}",
            )

    def clean(self):
        data = super().clean()
        if (
            data.get("export_format") == "csv"
            and "data_delimiter" in self.fields
            and not data.get("data_delimiter")
        ):
            self.add_error(
                "data_delimiter",
                forms.ValidationError(
                    _("Please select a delimiter for your CSV export.")
                ),
            )
        return data

    def get_object_attribute(self, obj, attribute):
        method = getattr(self, f"_get_{attribute}_value", None)
        if method:
            return method(obj)
        return getattr(obj, attribute, None)

    def get_data(self, queryset, fields, questions):
        data = []

        for obj in queryset:
            object_data = {}
            code = getattr(obj, "code", None)
            if code:
                object_data["ID"] = code
            prepare_method = getattr(self, "_prepare_object_data", None)
            if prepare_method:
                obj = prepare_method(obj)  # noqa: PLW2901 -- intentional reassignment of loop variable
            for field in fields:
                object_data[str(self.fields[field].label)] = self.get_object_attribute(
                    obj, field
                )

            for question in questions:
                answer = self.get_answer(question, obj)
                if answer:
                    object_data[str(question.question)] = answer.answer_string
                else:
                    object_data[str(question.question)] = None

            if hasattr(self, "get_additional_data"):
                object_data.update(**self.get_additional_data(obj))
            data.append(object_data)
        return data

    def export_data(self):
        fields = [
            field_name
            for field_name in self.export_field_names
            if self.cleaned_data.get(field_name)
        ]
        questions = [
            question
            for question in self.questions
            if self.cleaned_data.get(f"question_{question.pk}")
        ]
        data = self.get_data(self.get_queryset(), fields, questions)
        if not data:
            return
        if self.cleaned_data.get("export_format") == "csv":
            return self.csv_export(data)
        return self.json_export(data)

    def csv_export(self, data):
        delimiters = {"newline": "\n", "comma": ", "}
        delimiter = delimiters[self.cleaned_data.get("data_delimiter") or "newline"]

        for row in data:
            for key, value in row.items():
                if isinstance(value, list):
                    row[key] = delimiter.join(value)

        content = render_csv(fieldnames=data[0].keys(), rows=data)
        return HttpResponse(
            content,
            content_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{self.filename}.csv"',
                "Access-Control-Allow-Origin": "*",
            },
        )

    def json_export(self, data):
        content = json.dumps(data, cls=I18nJSONEncoder, indent=2)
        return HttpResponse(
            content,
            content_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{self.filename}.json"',
                "Access-Control-Allow-Origin": "*",
            },
        )

    class Media:
        js = [forms.Script("orga/js/forms/export.js", defer="")]


class ReviewExportForm(ExportForm):
    data_delimiter = None
    target = forms.ChoiceField(
        required=True,
        label=_n("Proposal", "Proposals", 1),
        choices=(
            ("all", phrases.base.all_choices),
            ("accepted", SubmissionStates.ACCEPTED.label),
            ("confirmed", SubmissionStates.CONFIRMED.label),
            ("rejected", SubmissionStates.REJECTED.label),
        ),
        widget=forms.RadioSelect,
        initial="all",
    )
    submission_id = forms.BooleanField(
        required=False,
        label=_("Proposal ID"),
        help_text=phrases.orga.proposal_id_help_text,
    )
    submission_title = forms.BooleanField(
        required=False, label=Submission._meta.get_field("title").verbose_name
    )
    user_name = forms.BooleanField(required=False, label=_("Reviewer name"))
    user_email = forms.BooleanField(
        required=False,
        label=pgettext_lazy("field: reviewer's email address", "Reviewer email"),
    )

    class Meta:
        model = Review
        model_fields = ["score", "text", "created", "updated"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["text"].label = phrases.base.text_body
        self._build_score_fields()

    @cached_property
    def questions(self):
        return questions_for_user(self.event, self.user).filter(
            target=QuestionTarget.REVIEWER
        )

    @cached_property
    def score_categories(self):
        sc = self.event.score_categories.filter(active=True)
        if len(sc) == 1:
            return []
        return sc

    @cached_property
    def score_field_names(self):
        return [f"score_{sc.pk}" for sc in self.score_categories]

    @cached_property
    def filename(self):
        return f"{self.event.slug}_reviews"

    @cached_property
    def export_field_names(self):
        return [
            "score",
            "text",
            *self.score_field_names,
            "submission_id",
            "submission_title",
            "created",
            "updated",
            "user_name",
            "user_email",
        ]

    def _build_score_fields(self):
        for score_category in self.score_categories:
            self.fields[f"score_{score_category.pk}"] = forms.BooleanField(
                required=False,
                label=str(_("Score in “{score_category}”")).format(
                    score_category=score_category.name
                ),
            )

    def get_additional_data(self, obj):
        return {
            str(sc.name): getattr(obj.scores.filter(category=sc).first(), "value", None)
            for sc in self.score_categories
        }

    def get_queryset(self):
        target = self.cleaned_data.get("target")
        queryset = self.event.reviews.all()
        if target != "all":
            queryset = queryset.filter(
                submission__in=self.event.submissions.filter(state=target)
            ).distinct()
        queryset = queryset.exclude(submission__speakers__user=self.user).distinct()
        return queryset.select_related("submission", "user").prefetch_related(
            "answers", "answers__question", "scores", "scores__category"
        )

    def _get_submission_id_value(self, obj):
        return obj.submission.code

    def _get_submission_title_value(self, obj):
        return obj.submission.title

    def _get_user_name_value(self, obj):
        return obj.user.name

    def _get_user_email_value(self, obj):
        return obj.user.email

    def get_answer(self, question, obj):
        return question.answers.filter(review=obj).first()


class ScheduleExportForm(ExportForm):
    target = forms.MultipleChoiceField(
        required=True,
        label=_("Target group"),
        choices=[("all", phrases.base.all_choices)]
        + [
            (state, name)
            for (state, name) in SubmissionStates.choices
            if state != SubmissionStates.DRAFT
        ],
        widget=EnhancedSelectMultiple(color_field=SubmissionStates.get_color),
        initial=["all"],
    )

    class Meta:
        model = Submission
        model_fields = [
            "title",
            "state",
            "pending_state",
            "submission_type",
            "track",
            "created",
            "tags",
            "abstract",
            "description",
            "notes",
            "internal_notes",
            "duration",
            "slot_count",
            "content_locale",
            "is_featured",
            "do_not_record",
            "image",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["speaker_ids"] = forms.BooleanField(
            required=False,
            label=_("Speaker IDs"),
            help_text=_(
                "The unique ID of a speaker is used in the speaker URL and in exports"
            ),
        )
        self.fields["speaker_names"] = forms.BooleanField(
            required=False, label=_("Speaker names")
        )
        self.fields["room"] = forms.BooleanField(
            required=False,
            label=TalkSlot._meta.get_field("room").verbose_name,
            help_text=TalkSlot._meta.get_field("room").help_text,
        )
        self.fields["start"] = forms.BooleanField(
            required=False,
            label=TalkSlot._meta.get_field("start").verbose_name,
            help_text=TalkSlot._meta.get_field("start").help_text,
        )
        self.fields["start_date"] = forms.BooleanField(
            required=False,
            label=TalkSlot._meta.get_field("start").verbose_name
            + " ("
            + pgettext_lazy("date as in calendar date", "date")
            + ")",
            help_text=TalkSlot._meta.get_field("start").help_text,
        )
        self.fields["start_time"] = forms.BooleanField(
            required=False,
            label=TalkSlot._meta.get_field("start").verbose_name
            + " ("
            + _("time")
            + ")",
            help_text=TalkSlot._meta.get_field("start").help_text,
        )
        self.fields["end"] = forms.BooleanField(
            required=False,
            label=TalkSlot._meta.get_field("end").verbose_name,
            help_text=TalkSlot._meta.get_field("end").help_text,
        )
        self.fields["end_date"] = forms.BooleanField(
            required=False,
            label=TalkSlot._meta.get_field("end").verbose_name
            + " ("
            + pgettext_lazy("date as in calendar date", "date")
            + ")",
            help_text=TalkSlot._meta.get_field("end").help_text,
        )
        self.fields["end_time"] = forms.BooleanField(
            required=False,
            label=TalkSlot._meta.get_field("end").verbose_name + " (" + _("time") + ")",
            help_text=TalkSlot._meta.get_field("end").help_text,
        )
        self.fields["median_score"] = forms.BooleanField(
            required=False,
            label=_("Median score"),
            help_text=_("Median review score, if there have been reviews yet"),
        )
        self.fields["mean_score"] = forms.BooleanField(
            required=False,
            label=_("Average (mean) score"),
            help_text=_("Average review score, if there have been reviews yet"),
        )
        self.fields["resources"] = forms.BooleanField(
            required=False,
            label=_("Resources"),
            help_text=_(
                "Resources provided by the speaker, either as links or as uploaded files"
            ),
        )
        if self.event and self.event.get_feature_flag("attendee_signup"):
            self.fields["requires_signup"] = forms.BooleanField(
                required=False, label=_("Requires signup")
            )
            self.fields["attendee_signup_count"] = forms.BooleanField(
                required=False, label=_("Number of attendees")
            )

    @cached_property
    def questions(self):
        return (
            questions_for_user(self.event, self.user)
            .filter(target=QuestionTarget.SUBMISSION)
            .prefetch_related(
                "answers", "answers__submission", "options", "answers__options"
            )
        )

    @cached_property
    def filename(self):
        return f"{self.event.slug}_sessions"

    @cached_property
    def export_field_names(self):
        names = [
            *self.Meta.model_fields,
            "speaker_ids",
            "speaker_names",
            "room",
            "start",
            "start_date",
            "start_time",
            "end",
            "end_date",
            "end_time",
            "median_score",
            "mean_score",
            "resources",
        ]
        if self.event and self.event.get_feature_flag("attendee_signup"):
            names.append("requires_signup")
            names.append("attendee_signup_count")
        return names

    def get_queryset(self):
        target = self.cleaned_data.get("target")
        queryset = submissions_for_user(self.event, self.user)
        if "all" not in target:
            queryset = queryset.filter(state__in=target)
        queryset = (
            queryset.prefetch_related("tags")
            .select_related("submission_type", "track")
            .prefetch_related("resources")
            .order_by("code")
        )
        if self.event and self.event.get_feature_flag("attendee_signup"):
            queryset = annotate_confirmed_signup_count(
                annotate_requires_signup(queryset)
            )
        return queryset

    def get_answer(self, question, obj):
        return question.answers.filter(submission=obj).first()

    def _get_speaker_ids_value(self, obj):
        return list(obj.sorted_speakers.values_list("code", flat=True))

    def _get_speaker_names_value(self, obj):
        return [s.get_display_name() for s in obj.sorted_speakers]

    def _get_room_value(self, obj):
        slot = obj.slot
        if slot and slot.room:
            return slot.room.name

    def _get_start(self, obj):
        slot = obj.slot
        if slot and slot.start:
            return slot.local_start

    def _get_end(self, obj):
        slot = obj.slot
        if slot and slot.real_end:
            return slot.local_end

    def _get_start_date_value(self, obj):
        start = self._get_start(obj)
        return start.date().isoformat() if start else None

    def _get_start_time_value(self, obj):
        start = self._get_start(obj)
        return start.time().isoformat() if start else None

    def _get_end_date_value(self, obj):
        end = self._get_end(obj)
        return end.date().isoformat() if end else None

    def _get_end_time_value(self, obj):
        end = self._get_end(obj)
        return end.time().isoformat() if end else None

    def _get_start_value(self, obj):
        start = self._get_start(obj)
        return start.isoformat() if start else None

    def _get_end_value(self, obj):
        end = self._get_end(obj)
        return end.isoformat() if end else None

    def _get_duration_value(self, obj):
        return obj.get_duration()

    def _get_image_value(self, obj):
        return obj.image_url

    def _get_created_value(self, obj):
        return obj.created.isoformat() if obj.created else None

    def _get_submission_type_value(self, obj):
        return obj.submission_type.name if obj.submission_type else None

    def _get_track_value(self, obj):
        return obj.track.name if obj.track else None

    def _get_tags_value(self, obj):
        return [tag.tag for tag in obj.tags.all()] or None

    def _get_resources_value(self, obj):
        return [resource.url for resource in obj.public_resources if resource.url]

    def _get_attendee_signup_count_value(self, obj):
        return obj.confirmed_signup_count


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
        self.fields["email"] = forms.BooleanField(required=False, label=_("Email"))
        self.fields["submission_ids"] = forms.BooleanField(
            required=False,
            label=_("Proposal IDs"),
            help_text=phrases.orga.proposal_id_help_text,
        )
        self.fields["submission_titles"] = forms.BooleanField(
            required=False, label=_("Proposal titles")
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
        return obj.get_avatar_url() or None

    def _get_email_value(self, obj):
        return obj.user.email

    def _get_submission_ids_value(self, obj):
        return list(obj.submissions.values_list("code", flat=True))

    def _get_submission_titles_value(self, obj):
        return list(obj.submissions.values_list("title", flat=True))

    def get_answer(self, question, obj):
        return question.answers.filter(speaker=obj).first()
