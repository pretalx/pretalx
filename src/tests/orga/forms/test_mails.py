import pytest
from django.core import mail as djmail
from django.utils import timezone
from django_scopes import scopes_disabled

from pretalx.mail.models import QueuedMailStates
from pretalx.mail.placeholders import SimpleFunctionalMailTextPlaceholder
from pretalx.mail.signals import register_mail_placeholders
from pretalx.orga.forms.mails import (
    MailDetailForm,
    MailTemplateForm,
    QueuedMailFilterForm,
    WriteMailBaseForm,
    WriteSessionMailForm,
    WriteTeamsMailForm,
)
from tests.factories import (
    AnswerOptionFactory,
    EventFactory,
    MailTemplateFactory,
    QuestionFactory,
    QueuedMailFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_mail_template_form_init_sets_required_fields():
    """subject and text must be required even though the model allows blank."""
    event = EventFactory()
    form = MailTemplateForm(event=event)

    assert form.fields["subject"].required is True
    assert form.fields["text"].required is True


@pytest.mark.django_db
def test_mail_template_form_init_uses_event_locales():
    event = EventFactory()
    form = MailTemplateForm(event=event)
    assert form.event == event


@pytest.mark.django_db
def test_mail_template_form_init_without_event():
    """MailTemplateForm can be initialized without an event."""
    form = MailTemplateForm(event=None)
    assert form.event is None


@pytest.mark.django_db
def test_mail_template_form_valid_data():
    event = EventFactory()
    form = MailTemplateForm(event=event, data={"subject_0": "Hello", "text_0": "World"})
    assert form.is_valid(), form.errors


@pytest.mark.parametrize(
    ("missing_field", "data"),
    (
        pytest.param("subject", {"subject_0": "", "text_0": "World"}, id="subject"),
        pytest.param("text", {"subject_0": "Hello", "text_0": ""}, id="text"),
    ),
)
@pytest.mark.django_db
def test_mail_template_form_clean_requires_field(missing_field, data):
    event = EventFactory()
    form = MailTemplateForm(event=event, data=data)

    assert not form.is_valid()
    assert missing_field in form.errors


@pytest.mark.django_db
def test_mail_template_form_clean_subject_valid_placeholder():
    event = EventFactory()
    form = MailTemplateForm(
        event=event, data={"subject_0": "Hello {event_name}", "text_0": "Body text"}
    )
    assert form.is_valid(), form.errors


@pytest.mark.parametrize(
    ("field", "data"),
    (
        pytest.param(
            "subject",
            {"subject_0": "Hello {nonexistent_placeholder}", "text_0": "Body text"},
            id="subject",
        ),
        pytest.param(
            "text", {"subject_0": "Hello", "text_0": "Body {does_not_exist}"}, id="text"
        ),
    ),
)
@pytest.mark.django_db
def test_mail_template_form_clean_rejects_invalid_placeholder(field, data):
    event = EventFactory()
    form = MailTemplateForm(event=event, data=data)

    assert not form.is_valid()
    assert field in form.errors


@pytest.mark.parametrize(
    ("field", "data"),
    (
        pytest.param(
            "subject",
            {"subject_0": "Hello { broken", "text_0": "Body text"},
            id="subject",
        ),
        pytest.param(
            "text", {"subject_0": "Hello", "text_0": "Body { broken"}, id="text"
        ),
    ),
)
@pytest.mark.django_db
def test_mail_template_form_clean_rejects_malformed_placeholder(field, data):
    event = EventFactory()
    form = MailTemplateForm(event=event, data=data)

    assert not form.is_valid()
    assert field in form.errors


@pytest.mark.django_db
def test_mail_template_form_clean_text_empty_link():
    event = EventFactory()
    form = MailTemplateForm(
        event=event, data={"subject_0": "Hello", "text_0": "[Click here]()"}
    )

    assert not form.is_valid()
    assert "text" in form.errors


@pytest.mark.django_db
def test_mail_template_form_clean_text_valid_link():
    """A template with a valid link passes validation."""
    event = EventFactory()
    form = MailTemplateForm(
        event=event,
        data={
            "subject_0": "Hello",
            "text_0": "Visit [our site](https://example.com) please",
        },
    )
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_mail_template_form_get_valid_placeholders_sets_event():
    event = EventFactory()
    with scopes_disabled():
        template = MailTemplateFactory(event=event)
    form = MailTemplateForm(event=event, instance=template)

    placeholders = form.get_valid_placeholders()

    assert "event_name" in placeholders


@pytest.mark.django_db
def test_mail_template_form_grouped_placeholders():
    event = EventFactory()
    form = MailTemplateForm(event=event)

    grouped = form.grouped_placeholders

    assert "event" in grouped
    assert "user" in grouped
    assert any(p.identifier == "event_name" for p in grouped["event"])
    assert all(
        hasattr(p, "rendered_sample") for group in grouped.values() for p in group
    )


@pytest.mark.django_db
def test_mail_template_form_grouped_placeholders_other_category(
    register_signal_handler,
):
    """Placeholders with empty required_context land in the 'other' group
    because they don't match any standard specificity key."""
    event = EventFactory()
    odd_placeholder = SimpleFunctionalMailTextPlaceholder(
        identifier="test_odd", args=[], func=lambda: "test", sample="test"
    )

    def provide_placeholder(signal, sender, **kwargs):
        return odd_placeholder

    register_signal_handler(register_mail_placeholders, provide_placeholder)

    with scopes_disabled():
        template = MailTemplateFactory(event=event)
    form = MailTemplateForm(event=event, instance=template)
    grouped = form.grouped_placeholders

    assert odd_placeholder in grouped["other"]


@pytest.mark.django_db
def test_mail_template_form_read_only():
    event = EventFactory()
    form = MailTemplateForm(
        event=event, read_only=True, data={"subject_0": "Hello", "text_0": "Body"}
    )

    for field in form.fields.values():
        assert field.disabled is True
    assert not form.is_valid()


@pytest.mark.django_db
def test_mail_template_form_save():
    event = EventFactory()
    form = MailTemplateForm(
        event=event, data={"subject_0": "Test subject", "text_0": "Test body"}
    )
    assert form.is_valid(), form.errors
    form.instance.event = event

    with scopes_disabled():
        template = form.save()

    assert template.pk is not None
    assert template.event == event
    assert str(template.subject) == "Test subject"
    assert str(template.text) == "Test body"


@pytest.mark.django_db
def test_mail_detail_form_init_no_to_users_removes_field():
    event = EventFactory()
    with scopes_disabled():
        mail = QueuedMailFactory(event=event, to="test@example.com")

    form = MailDetailForm(instance=mail)

    assert "to_users" not in form.fields


@pytest.mark.django_db
def test_mail_detail_form_init_with_to_users_keeps_field():
    event = EventFactory()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
        mail = QueuedMailFactory(event=event, to="")
        mail.to_users.add(speaker.user)

        form = MailDetailForm(instance=mail)

    assert "to_users" in form.fields
    assert form.fields["to_users"].required is False


@pytest.mark.django_db
def test_mail_detail_form_clean_no_recipients():
    event = EventFactory()
    with scopes_disabled():
        mail = QueuedMailFactory(event=event, to="someone@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Test",
            "text": "Body",
        },
    )

    assert not form.is_valid()
    assert "to" in form.errors


@pytest.mark.django_db
def test_mail_detail_form_clean_with_to_address():
    event = EventFactory()
    with scopes_disabled():
        mail = QueuedMailFactory(event=event, to="someone@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "recipient@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Test",
            "text": "Body",
        },
    )

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_mail_detail_form_save_moves_known_address_to_to_users():
    event = EventFactory()
    with scopes_disabled():
        user = UserFactory(email="known@example.com")
        mail = QueuedMailFactory(event=event, to="old@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "known@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Test",
            "text": "Body",
        },
    )
    assert form.is_valid(), form.errors

    with scopes_disabled():
        saved = form.save()
        saved.refresh_from_db()

    assert saved.to == ""
    assert list(saved.to_users.all()) == [user]


@pytest.mark.django_db
def test_mail_detail_form_save_keeps_unknown_address_in_to():
    event = EventFactory()
    with scopes_disabled():
        mail = QueuedMailFactory(event=event, to="old@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "unknown@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Test",
            "text": "Body",
        },
    )
    assert form.is_valid(), form.errors

    with scopes_disabled():
        saved = form.save()
        saved.refresh_from_db()

    assert saved.to == "unknown@example.com"
    assert list(saved.to_users.all()) == []


@pytest.mark.django_db
def test_mail_detail_form_save_mixed_known_and_unknown():
    """Known addresses move to to_users, unknown ones stay in to."""
    event = EventFactory()
    with scopes_disabled():
        user = UserFactory(email="known@example.com")
        mail = QueuedMailFactory(event=event, to="old@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "known@example.com,unknown@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Test",
            "text": "Body",
        },
    )
    assert form.is_valid(), form.errors

    with scopes_disabled():
        saved = form.save()
        saved.refresh_from_db()

    assert saved.to == "unknown@example.com"
    assert list(saved.to_users.all()) == [user]


@pytest.mark.django_db
def test_mail_detail_form_save_normalizes_email_case():
    """Email addresses in 'to' are lowercased and deduplicated."""
    event = EventFactory()
    with scopes_disabled():
        mail = QueuedMailFactory(event=event, to="old@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "FOO@Example.Com,foo@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Test",
            "text": "Body",
        },
    )
    assert form.is_valid(), form.errors

    with scopes_disabled():
        saved = form.save()
        saved.refresh_from_db()

    assert saved.to == "foo@example.com"


@pytest.mark.django_db
def test_mail_detail_form_save_without_to_change():
    """Saving without changing 'to' does not trigger address resolution."""
    event = EventFactory()
    with scopes_disabled():
        mail = QueuedMailFactory(event=event, to="test@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "test@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Updated subject",
            "text": "Updated body",
        },
    )
    assert form.is_valid(), form.errors
    with scopes_disabled():
        saved = form.save()
        saved.refresh_from_db()
    assert saved.subject == "Updated subject"
    assert saved.to == "test@example.com"


@pytest.mark.parametrize(
    ("may_skip_queue", "expected"),
    (
        pytest.param(True, True, id="allowed"),
        pytest.param(False, False, id="not_allowed"),
    ),
)
@pytest.mark.django_db
def test_write_mail_base_form_skip_queue_field(may_skip_queue, expected):
    event = EventFactory()
    form = WriteMailBaseForm(event=event, may_skip_queue=may_skip_queue)
    assert ("skip_queue" in form.fields) is expected


@pytest.mark.django_db
def test_write_teams_mail_form_init_populates_recipients():
    event = EventFactory()
    with scopes_disabled():
        team = TeamFactory(organiser=event.organiser)
        team.limit_events.add(event)

    form = WriteTeamsMailForm(event=event, may_skip_queue=True)

    assert "recipients" in form.fields
    choice_values = [v for v, _ in form.fields["recipients"].choices]
    assert team.pk in choice_values


@pytest.mark.django_db
def test_write_teams_mail_form_init_grouped_choices():
    """When both reviewer and non-reviewer teams exist, choices are grouped."""
    event = EventFactory()
    with scopes_disabled():
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


@pytest.mark.django_db
def test_write_teams_mail_form_skip_queue_removed():
    """skip_queue is always removed for team mails to avoid permission issues."""
    event = EventFactory()
    with scopes_disabled():
        team = TeamFactory(organiser=event.organiser)
        team.limit_events.add(event)

    form = WriteTeamsMailForm(event=event, may_skip_queue=True)

    assert "skip_queue" not in form.fields


@pytest.mark.django_db
def test_write_teams_mail_form_get_valid_placeholders():
    event = EventFactory()
    with scopes_disabled():
        TeamFactory(organiser=event.organiser).limit_events.add(event)

    form = WriteTeamsMailForm(event=event, may_skip_queue=True)
    placeholders = form.get_valid_placeholders()

    assert "event_name" in placeholders
    assert "name" in placeholders


@pytest.mark.django_db
def test_write_teams_mail_form_get_recipients():
    event = EventFactory()
    with scopes_disabled():
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

    with scopes_disabled():
        recipients = list(form.get_recipients())

    assert recipients == [user]


@pytest.mark.django_db
def test_write_teams_mail_form_get_recipients_excludes_inactive():
    event = EventFactory()
    with scopes_disabled():
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

    with scopes_disabled():
        recipients = list(form.get_recipients())

    assert recipients == [active_user]


@pytest.mark.django_db
def test_write_teams_mail_form_save_creates_mails():
    event = EventFactory()
    with scopes_disabled():
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

    with scopes_disabled():
        result = form.save()

    assert len(result) == 1
    mail = result[0]
    assert mail.subject == f"Hello {user.name}"
    assert mail.text == f"Dear {user.name}"


@pytest.mark.django_db
def test_write_session_mail_form_clean_requires_recipients():
    event = EventFactory()
    with scopes_disabled():
        form = WriteSessionMailForm(
            event=event, data={"subject_0": "Test", "text_0": "Body"}
        )
        assert not form.is_valid()

    assert "__all__" in form.errors


@pytest.mark.django_db
def test_write_session_mail_form_clean_with_state_filter():
    event = EventFactory()
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        form = WriteSessionMailForm(
            event=event,
            data={"state": ["submitted"], "subject_0": "Test", "text_0": "Body"},
        )
        assert form.is_valid(), form.errors

    recipients = form.get_recipients()
    recipient_users = {
        r["user"].user if hasattr(r["user"], "user") else r["user"]
        for r in recipients
        if "user" in r
    }
    assert recipient_users == {speaker.user}


@pytest.mark.django_db
def test_write_session_mail_form_clean_with_specific_submissions():
    event = EventFactory()
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        form = WriteSessionMailForm(
            event=event,
            data={
                "submissions": [submission.code],
                "subject_0": "Test",
                "text_0": "Body",
            },
        )
        assert form.is_valid(), form.errors

    recipients = form.get_recipients()
    recipient_users = {
        r["user"].user if hasattr(r["user"], "user") else r["user"]
        for r in recipients
        if "user" in r
    }
    assert recipient_users == {speaker.user}


@pytest.mark.django_db
def test_write_session_mail_form_clean_with_specific_speakers():
    event = EventFactory()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
        form = WriteSessionMailForm(
            event=event,
            data={"speakers": [speaker.pk], "subject_0": "Test", "text_0": "Body"},
        )
        assert form.is_valid(), form.errors

    recipients = form.get_recipients()
    assert recipients == [{"user": speaker}]


@pytest.mark.django_db
def test_write_session_mail_form_clean_with_published_schedule():
    """Recipients include slot data when submissions have current_slots."""
    event = EventFactory()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
        schedule = ScheduleFactory(event=event)
        schedule.published = timezone.now()
        schedule.save()
        TalkSlotFactory(submission=submission, schedule=schedule, is_visible=True)
        # Clear any cached current_schedule so the form sees the fresh state
        event.__dict__.pop("current_schedule", None)
        form = WriteSessionMailForm(
            event=event,
            data={
                "submissions": [submission.code],
                "subject_0": "Test",
                "text_0": "Body",
            },
        )
        assert form.is_valid(), form.errors

    recipients = form.get_recipients()
    slot_recipients = [r for r in recipients if "slot" in r]
    assert len(slot_recipients) == 1
    assert slot_recipients[0]["submission"] == submission


@pytest.mark.django_db
def test_write_session_mail_form_get_valid_placeholders_without_speakers():
    event = EventFactory()
    with scopes_disabled():
        form = WriteSessionMailForm(event=event)

    placeholders = form.get_valid_placeholders()

    assert "submission_title" in placeholders
    assert "proposal_title" in placeholders


@pytest.mark.django_db
def test_write_session_mail_form_get_valid_placeholders_with_speakers():
    """With speaker selection, submission/slot placeholders are removed."""
    event = EventFactory()
    with scopes_disabled():
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


@pytest.mark.django_db
def test_write_session_mail_form_submissions_field_choices():
    event = EventFactory()
    with scopes_disabled():
        sub1 = SubmissionFactory(event=event, title="Alpha Talk")
        sub2 = SubmissionFactory(event=event, title="Beta Talk")
        form = WriteSessionMailForm(event=event)

    choice_codes = [code for code, _ in form.fields["submissions"].choices]
    assert sub1.code in choice_codes
    assert sub2.code in choice_codes


@pytest.mark.django_db
def test_write_session_mail_form_speakers_field_queryset():
    event = EventFactory()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
        form = WriteSessionMailForm(event=event)

        assert speaker in form.fields["speakers"].queryset


@pytest.mark.django_db
def test_write_session_mail_form_multi_locale_subject_help_text():
    event = EventFactory()
    event.locale_array = "en,de"
    event.save()
    with scopes_disabled():
        form = WriteSessionMailForm(event=event)

    assert form.fields["subject"].help_text


@pytest.mark.django_db
def test_write_session_mail_form_single_locale_no_subject_help_text():
    event = EventFactory()
    with scopes_disabled():
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
@pytest.mark.django_db
def test_write_session_mail_form_clean_filter_returns_none_by_default(method):
    event = EventFactory()
    with scopes_disabled():
        form = WriteSessionMailForm(event=event)

    assert getattr(form, method)() is None


@pytest.mark.django_db
def test_write_session_mail_form_save_creates_queued_mails():
    event = EventFactory()
    with scopes_disabled():
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
        result = form.save()

    assert len(result) == 1
    with scopes_disabled():
        mail = result[0]
        assert list(mail.to_users.all()) == [speaker.user]
        assert list(mail.submissions.all()) == [submission]


@pytest.mark.django_db
def test_write_session_mail_form_save_speaker_only():
    """Saving with speaker-only recipients creates mail without submission link."""
    event = EventFactory()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
        form = WriteSessionMailForm(
            event=event,
            data={
                "speakers": [speaker.pk],
                "subject_0": "Hi",
                "text_0": "Hello {name}",
            },
        )
        assert form.is_valid(), form.errors
        result = form.save()

    assert len(result) == 1
    with scopes_disabled():
        mail = result[0]
        assert list(mail.to_users.all()) == [speaker.user]
        assert list(mail.submissions.all()) == []


@pytest.mark.django_db
def test_write_session_mail_form_save_deduplicates():
    """When a speaker gets the same content via both filter and specific
    selection, only one mail is created."""
    event = EventFactory()
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        form = WriteSessionMailForm(
            event=event,
            data={
                "state": ["submitted"],
                "submissions": [submission.code],
                "subject_0": "Hello",
                "text_0": "Same body",
            },
        )
        assert form.is_valid(), form.errors
        result = form.save()

    with scopes_disabled():
        user_mails = [m for m in result if speaker.user in m.to_users.all()]
    assert len(user_mails) == 1


@pytest.mark.django_db
def test_write_session_mail_form_save_skip_queue():
    event = EventFactory()
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    djmail.outbox = []
    with scopes_disabled():
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
        result = form.save()

    assert len(result) == 1
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_write_session_mail_form_save_suppresses_template_error():
    """When a placeholder can't be rendered (e.g. {session_room} without a
    slot), the mail is silently skipped rather than crashing."""
    event = EventFactory()
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        form = WriteSessionMailForm(
            event=event,
            data={
                "submissions": [submission.code],
                "subject_0": "Hello",
                "text_0": "Your room: {session_room}",
            },
        )
        assert form.is_valid(), form.errors
        result = form.save()

    assert result == []


@pytest.mark.django_db
def test_write_session_mail_form_save_with_track_filter():
    event = EventFactory()
    with scopes_disabled():
        event.feature_flags["use_tracks"] = True
        event.save()
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
        result = form.save()

    with scopes_disabled():
        all_recipients = set()
        for mail in result:
            all_recipients.update(mail.to_users.all())
    assert speaker.user in all_recipients
    assert other_speaker.user not in all_recipients


@pytest.mark.django_db
def test_write_session_mail_form_init_with_question_filter():
    """Initialising with a question in initial sets up the question/answer
    filter attributes that the clean_* methods later return."""
    event = EventFactory()
    with scopes_disabled():
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


@pytest.mark.django_db
def test_write_session_mail_form_init_with_search_filter():
    event = EventFactory()
    with scopes_disabled():
        form = WriteSessionMailForm(event=event, initial={"q": "keyword"})

    assert form.filter_search == "keyword"


@pytest.mark.django_db
def test_write_session_mail_form_init_with_nonexistent_question():
    """When initial has a question pk that doesn't exist, filter attributes are not set."""
    event = EventFactory()
    with scopes_disabled():
        form = WriteSessionMailForm(event=event, initial={"question": 99999})
    assert not hasattr(form, "filter_option")


@pytest.mark.django_db
def test_queued_mail_filter_form_init_sent_removes_status():
    event = EventFactory()
    with scopes_disabled():
        form = QueuedMailFilterForm(event=event, sent=True)

    assert "status" not in form.fields


@pytest.mark.django_db
def test_queued_mail_filter_form_init_no_failed_removes_status():
    event = EventFactory()
    with scopes_disabled():
        form = QueuedMailFilterForm(event=event, sent=False)

    assert "status" not in form.fields


@pytest.mark.django_db
def test_queued_mail_filter_form_init_with_failed_shows_status():
    event = EventFactory()
    with scopes_disabled():
        QueuedMailFactory(
            event=event,
            state=QueuedMailStates.DRAFT,
            error_data={"error": "SMTP failed", "type": "Exception"},
        )
        QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
        form = QueuedMailFilterForm(event=event, sent=False)

    assert "status" in form.fields
    choice_values = [v for v, _ in form.fields["status"].choices]
    assert choice_values == ["draft", "failed"]


@pytest.mark.django_db
def test_queued_mail_filter_form_init_no_tracks_removes_track():
    event = EventFactory()
    with scopes_disabled():
        event.feature_flags["use_tracks"] = False
        event.save()
        form = QueuedMailFilterForm(event=event, sent=False)

    assert "track" not in form.fields


@pytest.mark.django_db
def test_queued_mail_filter_form_init_with_tracks_shows_track():
    event = EventFactory()
    with scopes_disabled():
        track = TrackFactory(event=event)
        form = QueuedMailFilterForm(event=event, sent=False)

    assert "track" in form.fields
    with scopes_disabled():
        assert track in form.fields["track"].queryset


@pytest.mark.django_db
def test_queued_mail_filter_form_filter_queryset_by_status():
    event = EventFactory()
    with scopes_disabled():
        failed = QueuedMailFactory(
            event=event,
            state=QueuedMailStates.DRAFT,
            error_data={"error": "fail", "type": "Exception"},
        )
        QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
        form = QueuedMailFilterForm(
            event=event, sent=False, data={"status": ["failed"]}
        )
    assert form.is_valid(), form.errors

    with scopes_disabled():
        qs = event.queued_mails.filter(
            state=QueuedMailStates.DRAFT
        ).with_computed_state()
        result = list(form.filter_queryset(qs))

    assert result == [failed]


@pytest.mark.django_db
def test_queued_mail_filter_form_filter_queryset_by_track():
    event = EventFactory()
    with scopes_disabled():
        track = TrackFactory(event=event)
        submission = SubmissionFactory(event=event, track=track)
        mail_with_track = QueuedMailFactory(event=event)
        mail_with_track.submissions.add(submission)
        QueuedMailFactory(event=event)
        form = QueuedMailFilterForm(event=event, sent=False, data={"track": [track.pk]})
    assert form.is_valid(), form.errors

    with scopes_disabled():
        result = list(form.filter_queryset(event.queued_mails.all()))

    assert result == [mail_with_track]


@pytest.mark.django_db
def test_queued_mail_filter_form_filter_queryset_no_filters():
    event = EventFactory()
    with scopes_disabled():
        mail = QueuedMailFactory(event=event)
        form = QueuedMailFilterForm(event=event, sent=True, data={})
    assert form.is_valid(), form.errors

    with scopes_disabled():
        result = list(form.filter_queryset(event.queued_mails.all()))

    assert result == [mail]


@pytest.mark.django_db
def test_queued_mail_filter_form_init_sent_none_with_tracks():
    """When sent=None and tracks enabled, track filter uses unfiltered mail count."""
    event = EventFactory()
    with scopes_disabled():
        TrackFactory(event=event)
        form = QueuedMailFilterForm(event=event, sent=None)

    assert "track" in form.fields
