# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import mail as djmail
from django.http import QueryDict
from django_scopes import scopes_disabled

from pretalx.common.tables.filters import FilterContext, TableFilterSet
from pretalx.mail.domain.placeholders import TrustedPlainMailTextPlaceholder
from pretalx.mail.interfaces.forms.compose import (
    WriteMailBaseForm,
    WriteSessionMailForm,
    WriteTeamsMailForm,
)
from pretalx.mail.models import QueuedMail
from pretalx.mail.signals import register_mail_placeholders
from pretalx.mail.tasks import task_create_mails_for_template
from pretalx.submission.enums import QuestionTarget, SubmissionStates
from pretalx.submission.interfaces.filters import submission_list_filters
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def recipients_by(event, query, user=None):
    context = FilterContext(event=event, user=user, can_view_speakers=True)
    filterset = TableFilterSet(
        submission_list_filters(context), data=QueryDict(query), context=context
    )
    return {
        "filtered_submissions": filterset.filter(event.submissions.all()),
        "has_filters": filterset.is_active,
    }


@pytest.mark.parametrize(
    ("may_skip_queue", "expected"),
    (
        pytest.param(True, True, id="allowed"),
        pytest.param(False, False, id="not_allowed"),
    ),
)
def test_write_mail_base_form_skip_queue_field(may_skip_queue, expected):
    event = EventFactory()
    form = WriteMailBaseForm(event=event, may_skip_queue=may_skip_queue)
    assert ("skip_queue" in form.fields) is expected


def test_write_teams_mail_form_init_groups_teams_and_drops_skip_queue():
    event = EventFactory()
    reviewer_team = TeamFactory(
        organiser=event.organiser, is_reviewer=True, name="Reviewers"
    )
    reviewer_team.limit_events.add(event)
    orga_team = TeamFactory(
        organiser=event.organiser, is_reviewer=False, name="Organizers"
    )
    orga_team.limit_events.add(event)

    form = WriteTeamsMailForm(event=event, may_skip_queue=True)

    assert form.fields["recipients"].choices == [
        ("Reviewers", [(reviewer_team.pk, "Reviewers")]),
        ("Other teams", [(orga_team.pk, "Organizers")]),
    ]
    assert "skip_queue" not in form.fields
    placeholders = form.get_valid_placeholders()
    assert "event_name" in placeholders
    assert "name" in placeholders


def test_write_teams_mail_form_sends_transient_mails_to_active_members():
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser)
    team.limit_events.add(event)
    user = UserFactory()
    inactive_user = UserFactory(is_active=False)
    team.members.add(user, inactive_user)
    SpeakerFactory(event=event, user=user, email="contact-override@example.com")
    form = WriteTeamsMailForm(
        event=event,
        may_skip_queue=True,
        data={
            "recipients": [str(team.pk)],
            "subject_0": "Hello {name}",
            "text_0": "Dear {name}",
        },
    )
    assert form.fields["recipients"].choices == [(team.pk, team.name)]
    assert form.is_valid(), form.errors
    assert list(form.get_recipients()) == [user]
    djmail.outbox = []

    result = form.save()

    assert len(result) == 1
    assert result[0].pk is None
    assert result[0].to == user.email
    assert result[0].subject == f"Hello {user.name}"
    assert result[0].text == f"Dear {user.name}"
    with scopes_disabled():
        assert QueuedMail.objects.filter(event=event).count() == 0
    assert [sent.to for sent in djmail.outbox] == [[user.email]]


def test_write_session_mail_form_clean_requires_recipients():
    event = EventFactory()
    form = WriteSessionMailForm(
        event=event, data={"subject_0": "Test", "text_0": "Body"}
    )

    assert not form.is_valid()
    assert form.errors == {
        "__all__": [
            "Please select at least one filter or specific proposals/speakers as recipients."
        ]
    }


def test_write_session_mail_form_resolves_recipients_from_filters_codes_and_speakers():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED).speakers.add(
        SpeakerFactory(event=event)
    )
    text = {"subject_0": "Test", "text_0": "Body"}

    by_filter = WriteSessionMailForm(
        event=event, data=text, **recipients_by(event, "state=submitted")
    )
    by_code = WriteSessionMailForm(
        event=event, data={"submissions": [submission.code], **text}
    )
    by_speaker = WriteSessionMailForm(
        event=event, data={"speakers": [speaker.pk], **text}
    )

    for form in (by_filter, by_code, by_speaker):
        assert form.is_valid(), form.errors
    assert by_filter.get_recipients() == [
        {"submission": submission, "speaker": speaker}
    ]
    assert by_code.get_recipients() == [{"submission": submission, "speaker": speaker}]
    assert by_speaker.get_recipients() == [{"speaker": speaker}]
    assert by_code.speaker_only_recipients is False


def test_write_session_mail_form_clean_lists_unreachable_managed_speakers():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    unreachable = SpeakerFactory(event=event, user=None, email=None, name="No Mail")
    reachable_managed = SpeakerFactory(
        event=event, user=None, email="managed@example.com", name="Has Mail"
    )
    reachable = SpeakerFactory(event=event)
    submission.speakers.add(unreachable, reachable_managed, reachable)
    form = WriteSessionMailForm(
        event=event,
        data={"submissions": [submission.code], "subject_0": "Test", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors

    assert form.unreachable_recipients == [unreachable]


def test_write_session_mail_form_offers_submitters_and_bare_orga_speakers():
    event = EventFactory()
    bare_orga = SpeakerFactory(
        event=event,
        user=None,
        origin="orga",
        name="Standalone",
        email="standalone@example.com",
    )
    SpeakerFactory(event=event, user=None, origin="orga", name="No Mail")
    SpeakerFactory(event=event, origin="cfp")
    submitter = SpeakerFactory(event=event, origin="cfp")
    sub1 = SubmissionFactory(event=event, title="Alpha Talk")
    sub1.speakers.add(submitter)
    sub2 = SubmissionFactory(event=event, title="Beta Talk")

    form = WriteSessionMailForm(event=event)

    assert set(form.fields["speakers"].queryset) == {bare_orga, submitter}
    assert set(form.fields["submissions"].choices) == {
        (sub1.code, "Alpha Talk"),
        (sub2.code, "Beta Talk"),
    }
    assert not form.fields["subject"].help_text
    assert form.speaker_only_recipients is False
    placeholders = form.get_valid_placeholders()
    assert "submission_title" in placeholders
    assert "proposal_title" in placeholders

    form = WriteSessionMailForm(
        event=event,
        data={"speakers": [bare_orga.pk], "subject_0": "Test", "text_0": "Hi {name}"},
    )
    assert form.is_valid(), form.errors

    assert form.get_recipients() == [{"speaker": bare_orga}]


def test_write_session_mail_form_multi_locale_subject_help_text():
    event = EventFactory(locales=["en", "de"])
    form = WriteSessionMailForm(event=event)

    assert form.fields["subject"].help_text


@pytest.mark.parametrize(
    ("text", "warned"),
    (("About {proposal_title}", True), ("Hi {name}", False)),
    ids=("submission_placeholder", "speaker_placeholder"),
)
def test_write_session_mail_form_warns_on_submission_placeholder_for_direct_speakers(
    text, warned
):
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    direct = SpeakerFactory(
        event=event,
        user=None,
        origin="orga",
        name="Standalone",
        email="direct@example.com",
    )
    form = WriteSessionMailForm(
        event=event,
        data={"speakers": [direct.pk], "subject_0": "Test", "text_0": text},
        **recipients_by(event, "state=submitted"),
    )
    assert form.is_valid(), form.errors

    assert form.submissionless_placeholder_recipients == ([direct] if warned else [])


@pytest.mark.parametrize(
    ("narrowing", "text", "placeholders", "warned"),
    (
        ("", "Please confirm: {confirmation_link}", ["confirmation_link"], True),
        ("exclude", "Please confirm: {confirmation_link}", [], False),
        ("only", "Hi {name}, about {proposal_title}", [], False),
    ),
    ids=("managed_included", "managed_excluded", "no_account_placeholder"),
)
def test_write_session_mail_form_warns_on_account_link_to_managed_speakers(
    narrowing, text, placeholders, warned
):
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    managed = SpeakerFactory(
        event=event, user=None, email="managed@example.com", name="Managed"
    )
    account_backed = SpeakerFactory(event=event)
    submission.speakers.add(managed, account_backed)
    form = WriteSessionMailForm(
        event=event,
        data={
            "submissions": [submission.code],
            "managed_recipients": narrowing,
            "subject_0": "Test",
            "text_0": text,
        },
    )
    assert form.is_valid(), form.errors

    assert form.account_link_placeholders == placeholders
    assert form.account_link_recipients == ([managed] if warned else [])


def test_write_session_mail_form_only_managed_rejects_account_placeholder():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    managed = SpeakerFactory(
        event=event, user=None, email="managed@example.com", name="Managed"
    )
    submission.speakers.add(managed)
    form = WriteSessionMailForm(
        event=event,
        data={
            "submissions": [submission.code],
            "managed_recipients": "only",
            "subject_0": "Test",
            "text_0": "Please confirm: {confirmation_link}",
        },
    )

    assert not form.is_valid()
    assert list(form.errors) == ["text"]
    assert "{confirmation_link}" in str(form.errors["text"])


@pytest.mark.parametrize(
    ("narrowing", "expect_managed", "expect_account"),
    (
        pytest.param("all", True, True, id="all"),
        pytest.param("", True, True, id="default"),
        pytest.param("exclude", False, True, id="exclude"),
        pytest.param("only", True, False, id="only"),
    ),
)
def test_write_session_mail_form_narrows_managed_recipients(
    narrowing, expect_managed, expect_account
):
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    managed = SpeakerFactory(
        event=event, user=None, email="managed@example.com", name="Managed"
    )
    account_backed = SpeakerFactory(event=event)
    submission.speakers.add(managed, account_backed)
    form = WriteSessionMailForm(
        event=event,
        data={
            "submissions": [submission.code],
            "managed_recipients": narrowing,
            "subject_0": "Test",
            "text_0": "Body",
        },
    )
    assert form.is_valid(), form.errors

    recipients = {entry["speaker"] for entry in form.get_recipients()}
    expected = set()
    if expect_managed:
        expected.add(managed)
    if expect_account:
        expected.add(account_backed)
    assert recipients == expected


def test_write_session_mail_form_clean_with_published_schedule():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    schedule = ScheduleFactory(event=event)
    slot = TalkSlotFactory(submission=submission, schedule=schedule, is_visible=True)
    # Clear any cached current_schedule so the form sees the fresh state
    event.__dict__.pop("current_schedule", None)
    form = WriteSessionMailForm(
        event=event,
        data={"submissions": [submission.code], "subject_0": "Test", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors

    assert form.get_recipients() == [
        {"submission": submission, "slot": slot, "speaker": speaker}
    ]


@pytest.mark.parametrize("field", ("subject", "text"))
def test_write_session_mail_form_speaker_only_recipients_reject_submission_placeholders(
    field,
):
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    data = {"speakers": [speaker.pk], "subject_0": "Test", "text_0": "Body"}
    form = WriteSessionMailForm(event=event, data=data)
    assert form.is_valid(), form.errors
    assert form.speaker_only_recipients is True
    placeholders = form.get_valid_placeholders()
    assert "submission_title" not in placeholders
    assert "proposal_title" not in placeholders

    data[f"{field}_0"] = "Value {proposal_code}"
    form = WriteSessionMailForm(event=event, data=data)

    assert not form.is_valid()
    assert list(form.errors) == [field]
    assert "{proposal_code}" in str(form.errors[field])


def test_write_session_mail_form_submissions_and_speakers_allow_submission_placeholders():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state="submitted")
    submission.speakers.add(speaker)
    other_speaker = SpeakerFactory(event=event)
    other_submission = SubmissionFactory(event=event, state="accepted")
    other_submission.speakers.add(other_speaker)
    text = {"subject_0": "Test", "text_0": "Body {proposal_title} {proposal_code}"}

    by_code = WriteSessionMailForm(
        event=event,
        data={"submissions": [submission.code], "speakers": [other_speaker.pk], **text},
    )
    by_filter = WriteSessionMailForm(
        event=event,
        data={"speakers": [other_speaker.pk], **text},
        **recipients_by(event, "state=submitted"),
    )

    for form in (by_code, by_filter):
        assert form.is_valid(), form.errors
        assert form.speaker_only_recipients is False
        placeholders = form.get_valid_placeholders()
        assert "proposal_title" in placeholders
        assert "submission_title" in placeholders


def test_write_session_mail_form_applies_custom_field_filters():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    answered = SubmissionFactory(event=event)
    answered_speaker = SpeakerFactory(event=event)
    answered.speakers.add(answered_speaker)
    AnswerFactory(question=question, submission=answered, answer="yes")
    silent = SubmissionFactory(event=event)
    silent_speaker = SpeakerFactory(event=event)
    silent.speakers.add(silent_speaker)

    form = WriteSessionMailForm(
        event=event,
        data={"subject_0": "Test", "text_0": "Body"},
        **recipients_by(
            event,
            f"question_{question.pk}=__answered__",
            user=make_orga_user(event, can_change_submissions=True),
        ),
    )
    assert form.is_valid(), form.errors

    speakers = {entry["speaker"] for entry in form.get_recipients()}
    assert speakers == {answered_speaker}


def test_write_session_mail_form_applies_multi_value_and_track_filters():
    event = EventFactory(feature_flags={"use_tracks": True})
    track = TrackFactory(event=event)
    accepted = SubmissionFactory(
        event=event, state=SubmissionStates.ACCEPTED, track=track
    )
    accepted_speaker = SpeakerFactory(event=event)
    accepted.speakers.add(accepted_speaker)
    confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    confirmed_speaker = SpeakerFactory(event=event)
    confirmed.speakers.add(confirmed_speaker)
    withdrawn = SubmissionFactory(event=event, state=SubmissionStates.WITHDRAWN)
    withdrawn.speakers.add(SpeakerFactory(event=event))
    text = {"subject_0": "Test", "text_0": "Body"}

    by_states = WriteSessionMailForm(
        event=event, data=text, **recipients_by(event, "state=accepted&state=confirmed")
    )
    by_track = WriteSessionMailForm(
        event=event, data=text, **recipients_by(event, f"track={track.pk}")
    )

    assert by_states.is_valid(), by_states.errors
    assert by_track.is_valid(), by_track.errors
    assert {entry["speaker"] for entry in by_states.get_recipients()} == {
        accepted_speaker,
        confirmed_speaker,
    }
    assert {entry["speaker"] for entry in by_track.get_recipients()} == {
        accepted_speaker
    }


def test_write_session_mail_form_save_creates_one_queued_mail_per_speaker():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    sub_a = SubmissionFactory(event=event)
    sub_b = SubmissionFactory(event=event)
    sub_a.speakers.add(speaker)
    sub_b.speakers.add(speaker)
    form = WriteSessionMailForm(
        event=event,
        data={
            "submissions": [sub_a.code, sub_b.code],
            "subject_0": "Hello",
            "text_0": "Same body for everyone",
        },
    )
    assert form.is_valid(), form.errors
    task_data = form.save_template_and_get_task_data()
    assert len(task_data["recipients"]) == 2

    result = task_create_mails_for_template.apply(kwargs=task_data).result

    assert result["count"] == 1
    with scopes_disabled():
        mail = QueuedMail.objects.get(template_id=task_data["template_id"])
    assert list(mail.to_speakers.all()) == [speaker]
    assert set(mail.submissions.all()) == {sub_a, sub_b}


def test_write_session_mail_form_save_speaker_only():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    form = WriteSessionMailForm(
        event=event,
        data={"speakers": [speaker.pk], "subject_0": "Hi", "text_0": "Hello {name}"},
    )
    assert form.is_valid(), form.errors
    task_data = form.save_template_and_get_task_data()
    result = task_create_mails_for_template.apply(kwargs=task_data).result

    assert result["count"] == 1
    with scopes_disabled():
        mail = QueuedMail.objects.get(template_id=task_data["template_id"])
    assert list(mail.to_speakers.all()) == [speaker]
    assert list(mail.submissions.all()) == []


def test_write_session_mail_form_save_skip_queue():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    djmail.outbox = []
    form = WriteSessionMailForm(
        event=event,
        may_skip_queue=True,
        data={
            "submissions": [submission.code],
            "subject_0": "Immediate",
            "text_0": "Sent now",
            "skip_queue": "on",
        },
    )
    assert form.is_valid(), form.errors
    task_data = form.save_template_and_get_task_data()
    result = task_create_mails_for_template.apply(kwargs=task_data).result

    assert result["count"] == 1
    assert result["skip_queue"] is True
    assert len(djmail.outbox) == 1


def test_write_session_mail_form_save_suppresses_template_error(
    register_signal_handler,
):
    slot_placeholder = TrustedPlainMailTextPlaceholder(
        identifier="test_slot_placeholder",
        args=["slot"],
        func=lambda slot: str(slot.room),
        sample="Room 101",
    )

    def provide_placeholder(signal, sender, **kwargs):
        return slot_placeholder

    register_signal_handler(register_mail_placeholders, provide_placeholder)

    event = EventFactory()
    ScheduleFactory(event=event)  # slot placeholders require a current_schedule
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    form = WriteSessionMailForm(
        event=event,
        data={
            "submissions": [submission.code],
            "subject_0": "Hello",
            "text_0": "Your room: {test_slot_placeholder}",
        },
    )
    assert form.is_valid(), form.errors
    task_data = form.save_template_and_get_task_data()
    result = task_create_mails_for_template.apply(kwargs=task_data).result

    assert result["count"] == 0
    assert result["render_failures"] == 1
