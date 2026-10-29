# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import json
import zoneinfo

import pytest
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.utils.timezone import now

from pretalx.submission.interfaces.forms import (
    AnswerOptionForm,
    QuestionOrgaForm,
    QuestionReminderForm,
)
from pretalx.submission.interfaces.forms.question import (
    QuestionsForm,
    build_question_field,
)
from pretalx.submission.models import (
    Question,
    QuestionTarget,
    QuestionVariant,
    SubmissionStates,
    SubmissionType,
)
from pretalx.submission.models.question import QuestionRequired
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TrackFactory,
)
from tests.utils import refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _orga_data(**overrides):
    return {
        "target": "submission",
        "question_0": "Pick one",
        "variant": QuestionVariant.CHOICES,
        "question_required": QuestionRequired.OPTIONAL,
        "contains_personal_data": False,
        **overrides,
    }


def _orga_form(event, files=None, instance=None, **overrides):
    return QuestionOrgaForm(
        data=_orga_data(**overrides),
        files=files,
        instance=instance,
        event=event,
        locales=event.locales,
    )


def test_questions_form_init_loads_answers_defaults_and_scope():
    event = EventFactory()
    track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    q = QuestionFactory(event=event, default_answer="Default value")
    file_q = QuestionFactory(event=event, variant=QuestionVariant.FILE)
    track_q = QuestionFactory(event=event)
    track_q.tracks.add(track)
    other_q = QuestionFactory(event=event)
    other_q.tracks.add(TrackFactory(event=event))
    speaker_q = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    answer = AnswerFactory(question=q, submission=submission, answer="42")
    file_answer = AnswerFactory(
        question=file_q, submission=submission, answer="file://test.pdf"
    )
    file_answer.answer_file.name = "test.pdf"
    file_answer.save()

    form = QuestionsForm(event=event, submission=submission)

    assert set(form.fields) == {
        f"question_{q.pk}",
        f"question_{file_q.pk}",
        f"question_{track_q.pk}",
    }
    assert form.fields[f"question_{q.pk}"].initial == "42"
    assert form.fields[f"question_{q.pk}"].answer == answer
    assert form.fields[f"question_{file_q.pk}"].initial == file_answer.answer_file
    assert form.serialize_answers() == {
        f"question-{q.pk}": "42",
        f"question-{file_q.pk}": file_answer.answer_string,
        f"question-{track_q.pk}": None,
    }

    form = QuestionsForm(event=event, target=None, read_only=True)

    assert form.fields[f"question_{q.pk}"].initial == "Default value"
    assert all(field.disabled for field in form.fields.values())
    assert [f.name for f in form.speaker_fields] == [f"question_{speaker_q.pk}"]
    assert [f.name for f in form.submission_fields] == [
        f"question_{q.pk}",
        f"question_{file_q.pk}",
        f"question_{track_q.pk}",
        f"question_{other_q.pk}",
    ]


def test_questions_form_speaker_submissions_filters_restricted_questions():
    event = EventFactory()
    track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    unrestricted = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    matching = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    matching.tracks.add(track)
    other_track = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    other_track.tracks.add(TrackFactory(event=event))
    other_type = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    other_type.submission_types.add(SubmissionTypeFactory(event=event))

    form = QuestionsForm(
        event=event, target=QuestionTarget.SPEAKER, speaker_submissions=[submission]
    )

    assert set(form.fields) == {
        f"question_{unrestricted.pk}",
        f"question_{matching.pk}",
    }

    form = QuestionsForm(
        event=event, target=QuestionTarget.SPEAKER, speaker_submissions=[]
    )

    assert set(form.fields) == {f"question_{unrestricted.pk}"}


def test_questions_form_save_creates_updates_and_deletes_answers():
    event = EventFactory()
    q = QuestionFactory(event=event, variant=QuestionVariant.STRING)
    choice_q = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
    option = AnswerOptionFactory(question=choice_q)
    multiple_q = QuestionFactory(event=event, variant=QuestionVariant.MULTIPLE)
    opt1 = AnswerOptionFactory(question=multiple_q)
    opt2 = AnswerOptionFactory(question=multiple_q)
    boolean_q = QuestionFactory(event=event, variant=QuestionVariant.BOOLEAN)
    submission = SubmissionFactory(event=event)

    form = QuestionsForm(
        event=event,
        submission=submission,
        data={
            f"question_{q.pk}": "New answer",
            f"question_{choice_q.pk}": str(option.pk),
            f"question_{multiple_q.pk}": [str(opt1.pk), str(opt2.pk)],
            f"question_{boolean_q.pk}": "True",
        },
    )
    assert form.is_valid(), form.errors
    form.save()

    assert submission.answers.get(question=q).answer == "New answer"
    choice_answer = submission.answers.get(question=choice_q)
    assert choice_answer.answer == option.answer
    assert list(choice_answer.options.all()) == [option]
    assert set(submission.answers.get(question=multiple_q).options.all()) == {
        opt1,
        opt2,
    }
    assert submission.answers.get(question=boolean_q).answer == "True"

    form = QuestionsForm(
        event=event,
        submission=submission,
        data={f"question_{q.pk}": "Updated answer", f"question_{boolean_q.pk}": "True"},
    )
    assert form.is_valid(), form.errors
    form.save()

    assert submission.answers.get(question=q).answer == "Updated answer"
    assert not submission.answers.filter(question=choice_q).exists()
    assert not submission.answers.get(question=multiple_q).options.exists()

    form = QuestionsForm(event=event, submission=submission, data={})
    assert form.is_valid(), form.errors
    form.save()

    assert list(submission.answers.filter(question=q)) == []


def test_questions_form_save_resolves_target_per_question():
    event = EventFactory()
    speaker_q = QuestionFactory(
        event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.STRING
    )
    reviewer_q = QuestionFactory(
        event=event, target=QuestionTarget.REVIEWER, variant=QuestionVariant.STRING
    )
    speaker = SpeakerFactory(event=event)
    review = ReviewFactory(submission__event=event)

    form = QuestionsForm(
        event=event,
        target=QuestionTarget.SPEAKER,
        data={f"question_{speaker_q.pk}": "Speaker answer"},
    )
    assert form.is_valid(), form.errors
    with pytest.raises(ValueError, match="no speaker target object"):
        form.save()

    form = QuestionsForm(
        event=event,
        speaker=speaker,
        target=QuestionTarget.SPEAKER,
        data={f"question_{speaker_q.pk}": "Speaker answer"},
    )
    assert form.is_valid(), form.errors
    form.save()

    assert speaker.answers.get(question=speaker_q).answer == "Speaker answer"

    form = QuestionsForm(
        event=event,
        target=QuestionTarget.REVIEWER,
        data={f"question_{reviewer_q.pk}": "Late-bound review"},
    )
    assert form.is_valid(), form.errors
    form.save(review=review)

    assert review.answers.get(question=reviewer_q).answer == "Late-bound review"
    assert form.review is None

    form = QuestionsForm(
        event=event,
        review=review,
        target=QuestionTarget.REVIEWER,
        data={f"question_{reviewer_q.pk}": "Reviewer answer"},
    )
    assert form.is_valid(), form.errors
    form.save()

    assert review.answers.get(question=reviewer_q).answer == "Reviewer answer"


def test_build_question_field_boolean_number_url_file():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    boolean_q = QuestionFactory(
        event=event, variant=QuestionVariant.BOOLEAN, question_required="required"
    )
    number_q = QuestionFactory(
        event=event, variant=QuestionVariant.NUMBER, min_number=1, max_number=100
    )
    url_q = QuestionFactory(event=event, variant=QuestionVariant.URL)
    file_q = QuestionFactory(event=event, variant=QuestionVariant.FILE)
    AnswerFactory(question=boolean_q, submission=submission, answer="True")
    AnswerFactory(question=number_q, submission=submission, answer="42")
    AnswerFactory(question=url_q, submission=submission, answer="https://example.com")

    field = build_question_field(question=boolean_q)
    assert isinstance(field, forms.BooleanField)
    assert field.required is True
    assert field.initial is False

    field = build_question_field(question=boolean_q, target_object=submission)
    assert field.initial is True

    field = build_question_field(question=number_q, target_object=submission)
    assert isinstance(field, forms.DecimalField)
    assert (field.min_value, field.max_value, field.initial) == (1, 100, "42")

    field = build_question_field(question=url_q, target_object=submission)
    assert isinstance(field, forms.URLField)
    assert field.initial == "https://example.com"

    assert isinstance(build_question_field(question=file_q), forms.FileField)


@pytest.mark.parametrize(
    ("variant", "widget"),
    ((QuestionVariant.STRING, forms.TextInput), (QuestionVariant.TEXT, forms.Textarea)),
    ids=("string", "text"),
)
@pytest.mark.parametrize(
    ("count_in", "min_length", "max_length", "attrs"),
    (
        (
            "chars",
            10,
            200,
            {"data-minlength": 10, "data-maxlength": 200, "data-count-in": "chars"},
        ),
        (
            "words",
            5,
            50,
            {"data-minlength": 5, "data-maxlength": 50, "data-count-in": "words"},
        ),
        ("chars", None, None, {}),
    ),
    ids=("chars", "words", "unconstrained"),
)
def test_build_question_field_text_length_attributes(
    variant, widget, count_in, min_length, max_length, attrs
):
    event = EventFactory(cfp__settings={"count_length_in": count_in})
    question = QuestionFactory(
        event=event, variant=variant, min_length=min_length, max_length=max_length
    )

    field = build_question_field(question=question)

    assert isinstance(field, forms.CharField)
    assert isinstance(field.widget, widget)
    assert {
        key: value
        for key, value in field.widget.attrs.items()
        if key.startswith("data-")
    } == attrs


def test_build_question_field_choices_radio_has_no_empty_option():
    question = QuestionFactory(
        variant=QuestionVariant.CHOICES, question_required=QuestionRequired.OPTIONAL
    )
    opt1 = AnswerOptionFactory(question=question, answer="Option A")
    opt2 = AnswerOptionFactory(question=question, answer="Option B")
    submission = SubmissionFactory(event=question.event)
    answer = AnswerFactory(question=question, submission=submission)
    answer.options.add(opt1)

    field = build_question_field(question=question)

    assert isinstance(field, forms.ModelChoiceField)
    assert set(field.queryset) == {opt1, opt2}
    assert isinstance(field.widget, forms.RadioSelect)
    assert [str(label) for _, label in field.choices] == ["Option A", "Option B"]
    assert field.initial is None

    field = build_question_field(question=question, target_object=submission)

    assert field.initial == opt1


@pytest.mark.parametrize(
    ("question_required", "default_answer"),
    (
        (QuestionRequired.OPTIONAL, None),
        (QuestionRequired.REQUIRED, None),
        (QuestionRequired.REQUIRED, ""),
        (QuestionRequired.REQUIRED, "does-not-match-any-option"),
    ),
    ids=("optional", "required", "empty_default_answer", "unmatched_default_answer"),
)
def test_build_question_field_choices_dropdown_preselects_nothing(
    question_required, default_answer
):
    event = EventFactory()
    question = QuestionFactory(
        event=event,
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.CHOICES,
        question_required=question_required,
        default_answer=default_answer,
    )
    options = [
        AnswerOptionFactory(question=question, answer=f"Option {index}")
        for index in range(4)
    ]

    form = QuestionsForm(event=event)
    field = form.fields[f"question_{question.pk}"]
    html = str(form[f"question_{question.pk}"])

    assert [str(label) for _, label in field.choices] == [
        "- Select an option -",
        "Option 0",
        "Option 1",
        "Option 2",
        "Option 3",
    ]
    assert '<option value="" selected>- Select an option -</option>' in html
    for option in options:
        assert f'<option value="{option.pk}">' in html


def test_build_question_field_choices_optional_dropdown_can_be_unset():
    question = QuestionFactory(
        variant=QuestionVariant.CHOICES, question_required=QuestionRequired.OPTIONAL
    )
    options = [
        AnswerOptionFactory(question=question, answer=f"Option {index}")
        for index in range(4)
    ]
    submission = SubmissionFactory(event=question.event)
    answer = AnswerFactory(question=question, submission=submission)
    answer.options.add(options[1])

    field = build_question_field(question=question, target_object=submission)

    assert field.initial == options[1]
    assert [str(label) for _, label in field.choices] == [
        "- Select an option -",
        "Option 0",
        "Option 1",
        "Option 2",
        "Option 3",
    ]


def test_build_question_field_multiple_ignores_default_answer_and_loads_initial():
    event = EventFactory()
    question = QuestionFactory(
        event=event,
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.MULTIPLE,
        min_options=1,
        max_options=2,
        help_text="Pick some",
    )
    options = [
        AnswerOptionFactory(question=question, answer=f"Option {index}")
        for index in range(2)
    ]
    question.default_answer = str(options[0].pk)
    question.save()
    submission = SubmissionFactory(event=event)
    answer = AnswerFactory(question=question, submission=submission)
    answer.options.add(*options)

    form = QuestionsForm(event=event)
    field = form.fields[f"question_{question.pk}"]
    html = str(form[f"question_{question.pk}"])

    assert isinstance(field, forms.ModelMultipleChoiceField)
    assert set(field.queryset) == set(options)
    assert field.help_text == "<p>Pick some</p> Please select between 1 and 2 options."
    assert "checked" not in html
    for option in options:
        assert f'value="{option.pk}"' in html

    field = build_question_field(question=question, target_object=submission)

    assert set(field.initial) == set(options)

    question.min_options = question.max_options = None
    assert build_question_field(question=question).help_text == "<p>Pick some</p>"


@pytest.mark.parametrize(
    ("min_options", "max_options", "selected", "expected_error"),
    (
        (2, None, [0], "Please select at least 2 options. You selected 1 options."),
        (None, 1, [0, 1], "Please select at most 1 options. You selected 2 options."),
        (2, 2, [0, 0], "Please select exactly 2 options. You selected 1 options."),
    ),
    ids=("too_few", "too_many", "repeated_counts_once"),
)
def test_questions_form_rejects_option_count_outside_limits(
    min_options, max_options, selected, expected_error
):
    event = EventFactory()
    question = QuestionFactory(
        event=event,
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.MULTIPLE,
        min_options=min_options,
        max_options=max_options,
    )
    options = [AnswerOptionFactory(question=question) for _ in range(3)]
    submission = SubmissionFactory(event=event)

    form = QuestionsForm(
        event=event,
        submission=submission,
        data={
            f"question_{question.pk}": [str(options[index].pk) for index in selected]
        },
    )

    assert not form.is_valid()
    assert form.errors[f"question_{question.pk}"] == [expected_error]


def test_questions_form_accepts_option_counts_within_limits():
    event = EventFactory()
    bounded = QuestionFactory(
        event=event,
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.MULTIPLE,
        min_options=1,
        max_options=2,
    )
    opt1 = AnswerOptionFactory(question=bounded)
    opt2 = AnswerOptionFactory(question=bounded)
    capped = QuestionFactory(
        event=event,
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.MULTIPLE,
        max_options=1,
    )
    single = AnswerOptionFactory(question=capped)
    optional = QuestionFactory(
        event=event,
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.MULTIPLE,
        question_required=QuestionRequired.OPTIONAL,
        min_options=2,
    )
    AnswerOptionFactory(question=optional)
    AnswerOptionFactory(question=optional)
    submission = SubmissionFactory(event=event)

    form = QuestionsForm(
        event=event,
        submission=submission,
        data={
            f"question_{bounded.pk}": [str(opt1.pk), str(opt2.pk)],
            f"question_{capped.pk}": [str(single.pk), str(single.pk)],
        },
    )
    assert form.is_valid(), form.errors
    form.save()

    assert set(submission.answers.get(question=bounded).options.all()) == {opt1, opt2}
    assert list(submission.answers.get(question=capped).options.all()) == [single]
    assert not submission.answers.get(question=optional).options.exists()


def test_build_question_field_date_and_datetime():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    date_q = QuestionFactory(
        event=event,
        variant=QuestionVariant.DATE,
        min_date=dt.date(2025, 1, 1),
        max_date=dt.date(2025, 12, 31),
    )
    plain_date_q = QuestionFactory(event=event, variant=QuestionVariant.DATE)
    min_dt = dt.datetime(2025, 1, 1, 0, 0, tzinfo=dt.UTC)
    max_dt = dt.datetime(2025, 12, 31, 23, 59, tzinfo=dt.UTC)
    datetime_q = QuestionFactory(
        event=event,
        variant=QuestionVariant.DATETIME,
        min_datetime=min_dt,
        max_datetime=max_dt,
    )
    plain_datetime_q = QuestionFactory(event=event, variant=QuestionVariant.DATETIME)
    AnswerFactory(question=date_q, submission=submission, answer="2025-06-15")
    AnswerFactory(
        question=datetime_q, submission=submission, answer="2025-06-15T10:30:00+00:00"
    )

    field = build_question_field(question=date_q, target_object=submission)
    assert isinstance(field, forms.DateField)
    assert field.widget.attrs["data-date-start-date"] == "2025-01-01"
    assert field.widget.attrs["data-date-end-date"] == "2025-12-31"
    assert len(field.validators) == 2
    assert field.initial == dt.date(2025, 6, 15)

    field = build_question_field(question=plain_date_q)
    assert isinstance(field, forms.DateField)
    assert "data-date-start-date" not in field.widget.attrs
    assert "data-date-end-date" not in field.widget.attrs
    assert field.initial is None

    field = build_question_field(question=datetime_q, target_object=submission)
    assert isinstance(field, forms.DateTimeField)
    assert field.widget.attrs["min"] == min_dt.isoformat()
    assert field.widget.attrs["max"] == max_dt.isoformat()
    assert len(field.validators) == 2
    assert field.initial == dt.datetime(2025, 6, 15, 10, 30, tzinfo=dt.UTC).astimezone(
        event.tz
    )

    field = build_question_field(question=plain_datetime_q)
    assert isinstance(field, forms.DateTimeField)
    assert "min" not in field.widget.attrs
    assert "max" not in field.widget.attrs
    with (
        timezone.override(zoneinfo.ZoneInfo("Europe/Berlin")),
        pytest.raises(forms.ValidationError) as excinfo,
    ):
        field.clean("0001-01-01T00:00")
    assert excinfo.value.code == "invalid"


def test_build_question_field_read_only_via_freeze_or_parameter():
    frozen = QuestionFactory(
        variant=QuestionVariant.STRING,
        freeze_after=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
    )
    open_question = QuestionFactory(event=frozen.event, variant=QuestionVariant.STRING)

    assert build_question_field(question=frozen).disabled is True
    assert not build_question_field(question=open_question).disabled
    assert build_question_field(question=open_question, read_only=True).disabled


@pytest.mark.parametrize(
    ("target", "reviewer_visibility", "limits"),
    (
        (QuestionTarget.SUBMISSION, True, True),
        (QuestionTarget.SPEAKER, True, False),
        (QuestionTarget.REVIEWER, False, False),
    ),
)
def test_question_orga_form_fields_by_target(target, reviewer_visibility, limits):
    event = EventFactory(feature_flags={"use_tracks": True})
    TrackFactory(event=event)
    instance = Question(event=event, target=target)

    form = QuestionOrgaForm(event=event, locales=event.locales, instance=instance)

    assert ("is_visible_to_reviewers" in form.fields) is reviewer_visibility
    assert ("tracks" in form.fields) is limits
    assert ("submission_types" in form.fields) is limits


def test_question_orga_form_init_limits_follow_event_configuration():
    event = EventFactory(feature_flags={"use_tracks": False})
    extra_type = SubmissionTypeFactory(event=event)

    form = QuestionOrgaForm(event=event, locales=event.locales)

    assert "tracks" not in form.fields
    assert set(form.fields["submission_types"].queryset) == {
        event.cfp.default_type,
        extra_type,
    }

    event.feature_flags["use_tracks"] = True
    event.save()
    form = QuestionOrgaForm(event=event, locales=event.locales)

    assert "tracks" not in form.fields

    track = TrackFactory(event=event)
    event = refresh(event)
    form = QuestionOrgaForm(event=event, locales=event.locales)

    assert list(form.fields["tracks"].queryset) == [track]

    SubmissionType.objects.filter(event=event).update(event=EventFactory())
    form = QuestionOrgaForm(event=event, locales=event.locales)

    assert "submission_types" not in form.fields


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    (
        (
            "options.txt",
            b"Option A\nOption B\nOption C\n",
            ["Option A", "Option B", "Option C"],
        ),
        (
            "opts.json",
            json.dumps(
                [{"en": "English", "de": "Deutsch"}, {"en": "Yes", "de": "Ja"}]
            ).encode(),
            [{"en": "English", "de": "Deutsch"}, {"en": "Yes", "de": "Ja"}],
        ),
        ("bad.json", json.dumps({"key": "value"}).encode(), ['{"key": "value"}']),
        (
            "opts.json",
            json.dumps(["Option A", "Option B"]).encode(),
            ['["Option A", "Option B"]'],
        ),
        ("bad.bin", b"\x80\x81\x82", None),
    ),
    ids=(
        "plain_text",
        "json",
        "json_not_list",
        "json_list_of_non_dicts",
        "undecodable",
    ),
)
def test_question_orga_form_clean_options(filename, content, expected):
    event = EventFactory()
    upload = SimpleUploadedFile(filename, content)

    form = _orga_form(event, files={"options": upload})
    form.is_valid()

    if expected is None:
        assert form.errors == {"options": ["Could not read file."]}
        return
    assert [
        option.data if hasattr(option, "data") else option
        for option in form.cleaned_data["options"]
    ] == expected


def test_question_orga_form_clean_rules():
    event = EventFactory()
    QuestionFactory(event=event, identifier="MY-ID")

    form = _orga_form(event)
    form.is_valid()
    assert form.cleaned_data.get("options") is None

    form = _orga_form(
        event,
        variant=QuestionVariant.STRING,
        question_required=QuestionRequired.AFTER_DEADLINE,
        deadline="",
    )
    assert not form.is_valid()
    assert "deadline" in form.errors

    for question_required in (QuestionRequired.REQUIRED, QuestionRequired.OPTIONAL):
        form = _orga_form(
            event,
            variant=QuestionVariant.STRING,
            question_required=question_required,
            deadline=now().isoformat(),
        )
        form.is_valid()
        assert form.cleaned_data["deadline"] is None

    form = _orga_form(event, options_replace=True)
    assert form.errors == {
        "options_replace": ["You cannot replace options without uploading new ones."]
    }

    form = _orga_form(event, variant=QuestionVariant.STRING, is_public=True)
    form.is_valid()
    assert "limit_teams" not in form.cleaned_data

    form = _orga_form(event, variant=QuestionVariant.STRING, identifier="MY-ID")
    assert not form.is_valid()
    assert list(form.errors) == ["identifier"]


def test_question_orga_form_save_keeps_identifier_and_replaces_options():
    event = EventFactory()
    question = QuestionFactory(
        event=event, variant=QuestionVariant.CHOICES, identifier="MY-ID"
    )
    old_option = AnswerOptionFactory(question=question, answer="Old")
    AnswerFactory(question=question, answer="Old")

    form = _orga_form(
        event, instance=question, question_0="Updated text", identifier="MY-ID"
    )
    assert form.is_valid(), form.errors
    result = form.save()

    assert result.pk == question.pk
    assert result.identifier == "MY-ID"
    assert str(result.question) == "Updated text"
    assert list(question.options.all()) == [old_option]

    form = _orga_form(
        event,
        files={"options": SimpleUploadedFile("options.txt", b"New A\nNew B\n")},
        instance=question,
        question_0="Updated text",
        options_replace=True,
    )
    assert form.is_valid(), form.errors
    form.save()

    options = list(
        question.options.order_by("position").values_list("answer", flat=True)
    )
    assert options == ["New A", "New B"]
    assert question.answers.count() == 0
    assert not question.options.filter(pk=old_option.pk).exists()


def test_question_orga_form_saves_option_limits():
    event = EventFactory()

    form = _orga_form(
        event, variant=QuestionVariant.MULTIPLE, min_options="1", max_options="3"
    )
    assert form.is_valid(), form.errors
    question = form.save()

    assert (question.min_options, question.max_options) == (1, 3)


@pytest.mark.parametrize(
    ("overrides", "errors"),
    (
        (
            {"min_options": "3", "max_options": "2"},
            {
                "min_options": [
                    "Minimum number of options cannot be greater than maximum number of options."
                ]
            },
        ),
        (
            {"min_options": "0"},
            {"min_options": ["Ensure this value is greater than or equal to 1."]},
        ),
        (
            {"max_options": "0"},
            {"max_options": ["Ensure this value is greater than or equal to 1."]},
        ),
    ),
    ids=("min_above_max", "zero_min", "zero_max"),
)
def test_question_orga_form_rejects_invalid_option_limits(overrides, errors):
    event = EventFactory()

    form = _orga_form(event, variant=QuestionVariant.MULTIPLE, **overrides)

    assert not form.is_valid()
    assert form.errors == errors


@pytest.mark.parametrize(
    ("existing", "variant", "upload", "replace", "error_count", "final_count"),
    (
        (2, QuestionVariant.MULTIPLE, None, False, 2, 2),
        (2, QuestionVariant.CHOICES, None, False, None, 2),
        (1, QuestionVariant.MULTIPLE, b"New A\nNew B\nNew C\n", True, None, 3),
        (3, QuestionVariant.MULTIPLE, b"Only one\n", True, 1, 3),
        (1, QuestionVariant.MULTIPLE, b"New A\nNew B\n", False, None, 3),
    ),
    ids=(
        "above_option_count",
        "ignored_for_other_variants",
        "matches_uploaded_replacement",
        "above_uploaded_replacement",
        "counts_merged_upload",
    ),
)
def test_question_orga_form_validates_min_options_against_pending_options(
    existing, variant, upload, replace, error_count, final_count
):
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.MULTIPLE)
    for index in range(existing):
        AnswerOptionFactory(question=question, answer=f"Existing {index}")
    files = {"options": SimpleUploadedFile("options.txt", upload)} if upload else None

    form = _orga_form(
        event,
        files=files,
        instance=question,
        question_0=str(question.question),
        variant=variant,
        options_replace=replace,
        min_options="3",
    )

    if error_count is not None:
        assert form.errors == {
            "min_options": [
                (
                    f"This custom field only has {error_count} options, so it cannot "
                    "require 3 of them."
                )
            ]
        }
    else:
        assert form.is_valid(), form.errors
        assert form.save().variant == variant
    assert question.options.count() == final_count


def test_answer_option_form_valid_with_answer():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    form = AnswerOptionForm(
        data={"answer_0": "My option"}, locales=question.event.locales
    )

    assert form.is_valid(), form.errors


def test_question_reminder_form_fields_and_scope():
    event = EventFactory(feature_flags={"use_tracks": False})
    sub_q = QuestionFactory(event=event, target="submission", freeze_after=None)
    spk_q = QuestionFactory(event=event, target="speaker")
    QuestionFactory(event=event, target="reviewer")
    QuestionFactory(
        event=event, target="submission", freeze_after=now() - dt.timedelta(days=1)
    )
    confirmed_speaker = SpeakerFactory(event=event)
    confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    confirmed.speakers.add(confirmed_speaker)
    submitter = SpeakerFactory(event=event)
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    submitted.speakers.add(submitter)
    standalone = SpeakerFactory(event=event, user=None, origin="orga")

    form = QuestionReminderForm(event=event)

    assert "track" not in form.fields
    assert set(form.fields["questions"].queryset) == {sub_q, spk_q}
    assert list(form.fields["submission_type"].queryset) == [event.cfp.default_type]

    form = QuestionReminderForm(
        data={"role": "confirmed", "submission_type": ""}, event=event
    )
    assert form.is_valid(), form.errors
    submissions = form.get_submissions()

    assert list(submissions) == [confirmed]
    assert list(form.get_speakers(submissions=submissions)) == [confirmed_speaker]
    assert list(form.get_speakers()) == [confirmed_speaker]

    form = QuestionReminderForm(data={"role": "", "submission_type": ""}, event=event)
    assert form.is_valid(), form.errors

    assert set(form.get_submissions()) == {confirmed, submitted}
    assert set(form.get_speakers()) == {confirmed_speaker, submitter, standalone}

    event = EventFactory(feature_flags={"use_tracks": True})
    track = TrackFactory(event=event)
    form = QuestionReminderForm(event=event)

    assert list(form.fields["track"].queryset) == [track]
