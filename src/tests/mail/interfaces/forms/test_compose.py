# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import mail as djmail
from django_scopes import scopes_disabled

from pretalx.mail.domain.placeholders import TrustedPlainMailTextPlaceholder
from pretalx.mail.interfaces.forms.compose import (
    WriteMailBaseForm,
    WriteSessionMailForm,
    WriteTeamsMailForm,
)
from pretalx.mail.models import QueuedMail
from pretalx.mail.signals import register_mail_placeholders
from pretalx.mail.tasks import task_create_mails_for_template
from tests.factories import (
    AnswerOptionFactory,
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

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


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


def test_write_teams_mail_form_init_populates_recipients():
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser)
    team.limit_events.add(event)

    form = WriteTeamsMailForm(event=event, may_skip_queue=True)

    assert "recipients" in form.fields
    choice_values = [v for v, _ in form.fields["recipients"].choices]
    assert team.pk in choice_values


def test_write_teams_mail_form_init_grouped_choices():
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

    choices = form.fields["recipients"].choices
    assert len(choices) == 2
    group_names = [c[0] for c in choices]
    assert any("Reviewer" in str(g) for g in group_names)


def test_write_teams_mail_form_skip_queue_removed():
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser)
    team.limit_events.add(event)

    form = WriteTeamsMailForm(event=event, may_skip_queue=True)

    assert "skip_queue" not in form.fields


def test_write_teams_mail_form_get_valid_placeholders():
    event = EventFactory()
    TeamFactory(organiser=event.organiser).limit_events.add(event)

    form = WriteTeamsMailForm(event=event, may_skip_queue=True)
    placeholders = form.get_valid_placeholders()

    assert "event_name" in placeholders
    assert "name" in placeholders


def test_write_teams_mail_form_get_recipients():
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser)
    team.limit_events.add(event)
    user = UserFactory()
    team.members.add(user)
    form = WriteTeamsMailForm(
        event=event,
        may_skip_queue=True,
        data={"recipients": [str(team.pk)], "subject_0": "Test", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors

    recipients = list(form.get_recipients())

    assert recipients == [user]


def test_write_teams_mail_form_get_recipients_excludes_inactive():
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser)
    team.limit_events.add(event)
    active_user = UserFactory()
    inactive_user = UserFactory(is_active=False)
    team.members.add(active_user, inactive_user)
    form = WriteTeamsMailForm(
        event=event,
        may_skip_queue=True,
        data={"recipients": [str(team.pk)], "subject_0": "Test", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors

    recipients = list(form.get_recipients())

    assert recipients == [active_user]


def test_write_session_mail_form_clean_requires_recipients():
    event = EventFactory()
    form = WriteSessionMailForm(
        event=event, data={"subject_0": "Test", "text_0": "Body"}
    )
    assert not form.is_valid()

    assert "__all__" in form.errors


def test_write_session_mail_form_clean_with_state_filter():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    form = WriteSessionMailForm(
        event=event,
        data={"state": ["submitted"], "subject_0": "Test", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors

    recipients = form.get_recipients()
    recipient_speakers = {r["speaker"] for r in recipients if "speaker" in r}
    assert recipient_speakers == {speaker}


def test_write_session_mail_form_clean_with_specific_submissions():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    form = WriteSessionMailForm(
        event=event,
        data={"submissions": [submission.code], "subject_0": "Test", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors

    recipients = form.get_recipients()
    recipient_speakers = {r["speaker"] for r in recipients if "speaker" in r}
    assert recipient_speakers == {speaker}


def test_write_session_mail_form_clean_with_specific_speakers():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    form = WriteSessionMailForm(
        event=event,
        data={"speakers": [speaker.pk], "subject_0": "Test", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors

    recipients = form.get_recipients()
    assert recipients == [{"speaker": speaker}]


def test_write_session_mail_form_clean_lists_unreachable_managed_speakers():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    managed = SpeakerFactory(event=event, user=None, email=None, name="No Mail")
    reachable = SpeakerFactory(event=event)
    submission.speakers.add(managed, reachable)
    form = WriteSessionMailForm(
        event=event,
        data={"submissions": [submission.code], "subject_0": "Test", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors

    assert form.unreachable_recipients == [managed]


def test_write_session_mail_form_clean_no_unreachable_for_reachable_managed():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    managed = SpeakerFactory(
        event=event, user=None, email="managed@example.com", name="Has Mail"
    )
    submission.speakers.add(managed)
    form = WriteSessionMailForm(
        event=event,
        data={"submissions": [submission.code], "subject_0": "Test", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors

    assert form.unreachable_recipients == []


def test_write_session_mail_form_offers_bare_non_cfp_speakers():
    event = EventFactory()
    bare_orga = SpeakerFactory(
        event=event,
        user=None,
        origin="orga",
        name="Standalone",
        email="standalone@example.com",
    )
    bare_email_less = SpeakerFactory(
        event=event, user=None, origin="orga", name="No Mail"
    )
    bare_cfp = SpeakerFactory(event=event, origin="cfp")
    submitter = SpeakerFactory(event=event, origin="cfp")
    submission = SubmissionFactory(event=event)
    submission.speakers.add(submitter)

    form = WriteSessionMailForm(event=event)

    assert set(form.fields["speakers"].queryset) == {bare_orga, submitter}
    assert bare_cfp not in form.fields["speakers"].queryset
    assert bare_email_less not in form.fields["speakers"].queryset


def test_write_session_mail_form_clean_with_bare_speaker_recipient():
    event = EventFactory()
    bare = SpeakerFactory(
        event=event, user=None, origin="orga", email="bare@example.com"
    )
    form = WriteSessionMailForm(
        event=event,
        data={"speakers": [bare.pk], "subject_0": "Test", "text_0": "Hi {name}"},
    )
    assert form.is_valid(), form.errors

    assert form.get_recipients() == [{"speaker": bare}]


def test_write_session_mail_form_warns_on_submission_placeholder_for_direct_speakers():
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
        data={
            "state": ["submitted"],
            "speakers": [direct.pk],
            "subject_0": "Test",
            "text_0": "About {proposal_title}",
        },
    )
    assert form.is_valid(), form.errors

    assert form.submissionless_placeholder_recipients == [direct]


def test_write_session_mail_form_no_placeholder_warning_without_submission_placeholder():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    direct = SpeakerFactory(
        event=event, user=None, origin="orga", email="direct@example.com"
    )
    form = WriteSessionMailForm(
        event=event,
        data={
            "state": ["submitted"],
            "speakers": [direct.pk],
            "subject_0": "Test",
            "text_0": "Hi {name}",
        },
    )
    assert form.is_valid(), form.errors

    assert form.submissionless_placeholder_recipients == []


def test_write_session_mail_form_warns_on_account_link_to_managed_speakers():
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
            "subject_0": "Test",
            "text_0": "Please confirm: {confirmation_link}",
        },
    )
    assert form.is_valid(), form.errors

    assert form.account_link_placeholders == ["confirmation_link"]
    assert form.account_link_recipients == [managed]


def test_write_session_mail_form_no_account_link_warning_without_managed():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    submission.speakers.add(SpeakerFactory(event=event))
    form = WriteSessionMailForm(
        event=event,
        data={
            "submissions": [submission.code],
            "subject_0": "Test",
            "text_0": "Please confirm: {confirmation_link}",
        },
    )
    assert form.is_valid(), form.errors

    assert form.account_link_placeholders == []
    assert form.account_link_recipients == []


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
    assert "text" in form.errors


def test_write_session_mail_form_only_managed_allows_regular_placeholders():
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
            "text_0": "Hi {name}, about {proposal_title}",
        },
    )

    assert form.is_valid(), form.errors


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
    TalkSlotFactory(submission=submission, schedule=schedule, is_visible=True)
    # Clear any cached current_schedule so the form sees the fresh state
    event.__dict__.pop("current_schedule", None)
    form = WriteSessionMailForm(
        event=event,
        data={"submissions": [submission.code], "subject_0": "Test", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors

    recipients = form.get_recipients()
    slot_recipients = [r for r in recipients if "slot" in r]
    assert len(slot_recipients) == 1
    assert slot_recipients[0]["submission"] == submission


def test_write_session_mail_form_get_valid_placeholders_without_speakers():
    event = EventFactory()
    form = WriteSessionMailForm(event=event)

    placeholders = form.get_valid_placeholders()

    assert "submission_title" in placeholders
    assert "proposal_title" in placeholders


def test_write_session_mail_form_get_valid_placeholders_with_speakers():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    form = WriteSessionMailForm(
        event=event,
        data={"speakers": [speaker.pk], "subject_0": "Test", "text_0": "Body"},
    )
    form.is_valid()

    placeholders = form.get_valid_placeholders()
    assert "submission_title" not in placeholders
    assert "proposal_title" not in placeholders


def test_write_session_mail_form_get_valid_placeholders_with_submissions_and_speakers():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    other_speaker = SpeakerFactory(event=event)
    other_submission = SubmissionFactory(event=event)
    other_submission.speakers.add(other_speaker)
    form = WriteSessionMailForm(
        event=event,
        data={
            "submissions": [submission.code],
            "speakers": [other_speaker.pk],
            "subject_0": "Test",
            "text_0": "Body {proposal_title}",
        },
    )
    assert form.is_valid(), form.errors

    placeholders = form.get_valid_placeholders()
    assert "proposal_title" in placeholders
    assert "submission_title" in placeholders


def test_write_session_mail_form_get_valid_placeholders_with_filters_and_speakers():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state="submitted")
    submission.speakers.add(speaker)
    other_speaker = SpeakerFactory(event=event)
    other_submission = SubmissionFactory(event=event, state="accepted")
    other_submission.speakers.add(other_speaker)
    form = WriteSessionMailForm(
        event=event,
        data={
            "state": ["submitted"],
            "speakers": [other_speaker.pk],
            "subject_0": "Test",
            "text_0": "Body {proposal_title}",
        },
    )
    assert form.is_valid(), form.errors

    placeholders = form.get_valid_placeholders()
    assert "proposal_title" in placeholders
    assert "submission_title" in placeholders


def test_write_session_mail_form_speaker_only_recipients_unbound():
    event = EventFactory()
    form = WriteSessionMailForm(event=event)
    assert form.speaker_only_recipients is False


def test_write_session_mail_form_speaker_only_recipients_true():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    form = WriteSessionMailForm(
        event=event,
        data={"speakers": [speaker.pk], "subject_0": "Test", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors
    assert form.speaker_only_recipients is True


def test_write_session_mail_form_speaker_only_recipients_false_with_submissions():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    form = WriteSessionMailForm(
        event=event,
        data={
            "submissions": [submission.code],
            "speakers": [speaker.pk],
            "subject_0": "Test",
            "text_0": "Body",
        },
    )
    assert form.is_valid(), form.errors
    assert form.speaker_only_recipients is False


def test_write_session_mail_form_speaker_only_recipients_false_with_filters():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state="submitted")
    submission.speakers.add(speaker)
    form = WriteSessionMailForm(
        event=event,
        data={
            "state": ["submitted"],
            "speakers": [speaker.pk],
            "subject_0": "Test",
            "text_0": "Body",
        },
    )
    assert form.is_valid(), form.errors
    assert form.speaker_only_recipients is False


def test_write_session_mail_form_speaker_only_recipients_false_without_speakers():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state="submitted")
    form = WriteSessionMailForm(
        event=event,
        data={"submissions": [submission.code], "subject_0": "Test", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors
    assert form.speaker_only_recipients is False


def test_write_session_mail_form_submissions_field_choices():
    event = EventFactory()
    sub1 = SubmissionFactory(event=event, title="Alpha Talk")
    sub2 = SubmissionFactory(event=event, title="Beta Talk")
    form = WriteSessionMailForm(event=event)

    choice_codes = [code for code, _ in form.fields["submissions"].choices]
    assert sub1.code in choice_codes
    assert sub2.code in choice_codes


def test_write_session_mail_form_speakers_field_queryset():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    form = WriteSessionMailForm(event=event)

    assert speaker in form.fields["speakers"].queryset


def test_write_session_mail_form_multi_locale_subject_help_text():
    event = EventFactory(locales=["en", "de"])
    form = WriteSessionMailForm(event=event)

    assert form.fields["subject"].help_text


def test_write_session_mail_form_single_locale_no_subject_help_text():
    event = EventFactory()
    form = WriteSessionMailForm(event=event)

    assert not form.fields["subject"].help_text


@pytest.mark.parametrize(
    "method",
    (
        "clean_question",
        "clean_answer__options",
        "clean_answer",
        "clean_unanswered",
        "clean_q",
    ),
)
def test_write_session_mail_form_clean_filter_returns_none_by_default(method):
    event = EventFactory()
    form = WriteSessionMailForm(event=event)

    assert getattr(form, method)() is None


def test_write_session_mail_form_init_with_question_filter():
    event = EventFactory()
    question = QuestionFactory(event=event, variant="choices")
    option = AnswerOptionFactory(question=question)
    form = WriteSessionMailForm(
        event=event,
        initial={
            "question": question.pk,
            "answer__options": option.pk,
            "answer": "test",
            "unanswered": True,
        },
    )

    assert form.filter_question == question
    assert form.filter_option == option
    assert form.filter_answer == "test"
    assert form.filter_unanswered is True


def test_write_session_mail_form_init_with_search_filter():
    event = EventFactory()
    form = WriteSessionMailForm(event=event, initial={"q": "keyword"})

    assert form.filter_search == "keyword"


def test_write_session_mail_form_init_with_nonexistent_question():
    event = EventFactory()
    form = WriteSessionMailForm(event=event, initial={"question": 99999})
    assert not hasattr(form, "filter_option")


def test_write_teams_mail_form_save_creates_mails():
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser)
    team.limit_events.add(event)
    user = UserFactory()
    team.members.add(user)
    form = WriteTeamsMailForm(
        event=event,
        may_skip_queue=True,
        data={
            "recipients": [str(team.pk)],
            "subject_0": "Hello {name}",
            "text_0": "Dear {name}",
        },
    )
    assert form.is_valid(), form.errors
    djmail.outbox = []

    result = form.save()

    assert len(result) == 1
    mail = result[0]
    assert mail.subject == f"Hello {user.name}"
    assert mail.text == f"Dear {user.name}"


def test_write_teams_mail_form_save_stays_transient_and_account_addressed():
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser)
    team.limit_events.add(event)
    user = UserFactory()
    team.members.add(user)
    SpeakerFactory(event=event, user=user, email="contact-override@example.com")
    form = WriteTeamsMailForm(
        event=event,
        may_skip_queue=True,
        data={"recipients": [str(team.pk)], "subject_0": "Hello", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors
    djmail.outbox = []

    result = form.save()

    assert len(result) == 1
    assert result[0].pk is None
    assert result[0].to == user.email
    with scopes_disabled():
        assert QueuedMail.objects.filter(event=event).count() == 0
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]


def test_write_session_mail_form_save_creates_queued_mails():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    form = WriteSessionMailForm(
        event=event,
        data={
            "submissions": [submission.code],
            "subject_0": "Hello",
            "text_0": "Body text",
        },
    )
    assert form.is_valid(), form.errors
    task_data = form.save_template_and_get_task_data()
    result = task_create_mails_for_template.apply(kwargs=task_data).result

    assert result["count"] == 1
    with scopes_disabled():
        mail = QueuedMail.objects.get(template_id=task_data["template_id"])
    assert list(mail.to_speakers.all()) == [speaker]
    assert list(mail.submissions.all()) == [submission]


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


def test_write_session_mail_form_save_deduplicates():
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
    task_create_mails_for_template.apply(kwargs=task_data)

    with scopes_disabled():
        user_mails = list(
            QueuedMail.objects.filter(
                template_id=task_data["template_id"], to_speakers=speaker
            )
        )
    assert len(user_mails) == 1
    assert set(user_mails[0].submissions.values_list("pk", flat=True)) == {
        sub_a.pk,
        sub_b.pk,
    }


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


def test_write_session_mail_form_save_with_track_filter():
    event = EventFactory(feature_flags={"use_tracks": True})
    track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    other_sub = SubmissionFactory(event=event)
    other_speaker = SpeakerFactory(event=event)
    other_sub.speakers.add(other_speaker)
    form = WriteSessionMailForm(
        event=event,
        data={"track": [track.pk], "subject_0": "Track mail", "text_0": "Body"},
    )
    assert form.is_valid(), form.errors
    task_data = form.save_template_and_get_task_data()
    task_create_mails_for_template.apply(kwargs=task_data)

    all_recipients = set()
    with scopes_disabled():
        for mail in QueuedMail.objects.filter(template_id=task_data["template_id"]):
            all_recipients.update(mail.to_speakers.all())
    assert speaker in all_recipients
    assert other_speaker not in all_recipients


@pytest.mark.parametrize("field", ("subject", "text"))
def test_write_session_mail_form_speaker_only_rejects_submission_placeholder(field):
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    data = {"speakers": [speaker.pk], "subject_0": "Test", "text_0": "Body"}
    data[f"{field}_0"] = "Value {proposal_code}"
    form = WriteSessionMailForm(event=event, data=data)

    assert not form.is_valid()
    assert "{proposal_code}" in str(form.errors[field])


def test_write_session_mail_form_submission_placeholder_valid_with_submissions():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    other_speaker = SpeakerFactory(event=event)
    other_submission = SubmissionFactory(event=event)
    other_submission.speakers.add(other_speaker)
    form = WriteSessionMailForm(
        event=event,
        data={
            "submissions": [submission.code],
            "speakers": [other_speaker.pk],
            "subject_0": "Test",
            "text_0": "Body {proposal_code}",
        },
    )
    assert form.is_valid(), form.errors
