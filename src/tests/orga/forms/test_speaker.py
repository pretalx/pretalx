import pytest
from django_scopes import scopes_disabled

from pretalx.orga.forms.speaker import SpeakerExportForm
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_speaker_export_form_target_choices():
    with scopes_disabled():
        event = EventFactory()
        form = SpeakerExportForm(event=event)

    target_values = [choice[0] for choice in form.fields["target"].choices]
    assert target_values == ["all", "accepted"]


@pytest.mark.django_db
def test_speaker_export_form_has_extra_fields():
    with scopes_disabled():
        event = EventFactory()
        form = SpeakerExportForm(event=event)

    for field_name in ("email", "submission_ids", "submission_titles", "avatar"):
        assert field_name in form.fields, f"Missing field: {field_name}"


@pytest.mark.django_db
def test_speaker_export_form_has_model_fields():
    with scopes_disabled():
        event = EventFactory()
        form = SpeakerExportForm(event=event)

    for field_name in SpeakerExportForm.Meta.model_fields:
        assert field_name in form.fields, f"Missing model field: {field_name}"


@pytest.mark.django_db
def test_speaker_export_form_questions_property():
    """Only active speaker-targeted questions are included."""
    with scopes_disabled():
        event = EventFactory()
        speaker_q = QuestionFactory(event=event, target="speaker", active=True)
        QuestionFactory(event=event, target="submission", active=True)
        QuestionFactory(event=event, target="speaker", active=False)
        form = SpeakerExportForm(event=event)

    assert list(form.questions) == [speaker_q]


@pytest.mark.django_db
def test_speaker_export_form_question_fields_added():
    with scopes_disabled():
        event = EventFactory()
        question = QuestionFactory(event=event, target="speaker", active=True)
        form = SpeakerExportForm(event=event)

    assert f"question_{question.pk}" in form.fields


@pytest.mark.django_db
def test_speaker_export_form_filename():
    with scopes_disabled():
        event = EventFactory()
        form = SpeakerExportForm(event=event)

    assert form.filename == f"{event.slug}_speakers"


@pytest.mark.django_db
def test_speaker_export_form_export_field_names():
    with scopes_disabled():
        event = EventFactory()
        form = SpeakerExportForm(event=event)

    names = form.export_field_names
    assert names == [
        "name",
        "biography",
        "email",
        "avatar",
        "submission_ids",
        "submission_titles",
    ]


@pytest.mark.django_db
def test_speaker_export_form_get_queryset_all():
    with scopes_disabled():
        event = EventFactory()
        speaker1 = SpeakerFactory(event=event)
        speaker2 = SpeakerFactory(event=event)
        sub1 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        sub1.speakers.add(speaker1)
        sub2 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        sub2.speakers.add(speaker2)
        form = SpeakerExportForm(
            data={"export_format": "json", "target": "all", "name": True}, event=event
        )
        form.is_valid()
        qs = list(form.get_queryset())

    assert set(qs) == {speaker1, speaker2}


@pytest.mark.django_db
def test_speaker_export_form_get_queryset_accepted_only():
    with scopes_disabled():
        event = EventFactory()
        accepted_speaker = SpeakerFactory(event=event)
        submitted_speaker = SpeakerFactory(event=event)
        sub_accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        sub_accepted.speakers.add(accepted_speaker)
        sub_submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        sub_submitted.speakers.add(submitted_speaker)
        form = SpeakerExportForm(
            data={"export_format": "json", "target": "accepted", "name": True},
            event=event,
        )
        form.is_valid()
        qs = list(form.get_queryset())

    assert qs == [accepted_speaker]


@pytest.mark.django_db
def test_speaker_export_form_get_queryset_includes_confirmed():
    with scopes_disabled():
        event = EventFactory()
        confirmed_speaker = SpeakerFactory(event=event)
        sub_confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub_confirmed.speakers.add(confirmed_speaker)
        form = SpeakerExportForm(
            data={"export_format": "json", "target": "accepted", "name": True},
            event=event,
        )
        form.is_valid()
        qs = list(form.get_queryset())

    assert qs == [confirmed_speaker]


@pytest.mark.django_db
def test_speaker_export_form_get_name_value():
    with scopes_disabled():
        event = EventFactory()
        speaker = SpeakerFactory(event=event)
        form = SpeakerExportForm(event=event)
        result = form._get_name_value(speaker)

    assert result == speaker.get_display_name()


@pytest.mark.django_db
def test_speaker_export_form_get_avatar_value_no_avatar():
    with scopes_disabled():
        event = EventFactory()
        speaker = SpeakerFactory(event=event)
        form = SpeakerExportForm(event=event)
        result = form._get_avatar_value(speaker)

    assert result is None


@pytest.mark.django_db
def test_speaker_export_form_get_email_value():
    with scopes_disabled():
        event = EventFactory()
        speaker = SpeakerFactory(event=event)
        form = SpeakerExportForm(event=event)
        result = form._get_email_value(speaker)

    assert result == speaker.user.email


@pytest.mark.django_db
def test_speaker_export_form_get_submission_ids_value():
    with scopes_disabled():
        event = EventFactory()
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        form = SpeakerExportForm(event=event)
        result = form._get_submission_ids_value(speaker)

    assert result == [sub.code]


@pytest.mark.django_db
def test_speaker_export_form_get_submission_titles_value():
    with scopes_disabled():
        event = EventFactory()
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        form = SpeakerExportForm(event=event)
        result = form._get_submission_titles_value(speaker)

    assert result == [sub.title]


@pytest.mark.django_db
def test_speaker_export_form_get_answer():
    with scopes_disabled():
        event = EventFactory()
        speaker = SpeakerFactory(event=event)
        question = QuestionFactory(event=event, target="speaker", active=True)
        answer = AnswerFactory(question=question, speaker=speaker)
        form = SpeakerExportForm(event=event)
        result = form.get_answer(question, speaker)

    assert result == answer


@pytest.mark.django_db
def test_speaker_export_form_get_answer_none():
    with scopes_disabled():
        event = EventFactory()
        speaker = SpeakerFactory(event=event)
        question = QuestionFactory(event=event, target="speaker", active=True)
        form = SpeakerExportForm(event=event)
        result = form.get_answer(question, speaker)

    assert result is None
