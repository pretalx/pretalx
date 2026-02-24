import datetime as dt
import statistics

import pytest
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.utils.timezone import now, timedelta
from django_scopes import scope, scopes_disabled

from pretalx.common.exceptions import SubmissionError
from pretalx.mail.models import MailTemplateRoles
from pretalx.schedule.models.availability import Availability
from pretalx.submission.models import (
    Answer,
    Resource,
    ReviewScore,
    ReviewScoreCategory,
    Submission,
    SubmissionStates,
)
from pretalx.submission.models.question import QuestionTarget
from pretalx.submission.models.review import ReviewPhase
from pretalx.submission.models.submission import (
    SpeakerRole,
    SubmissionFavourite,
    SubmissionInvitation,
    generate_invite_code,
    submission_image_path,
)
from pretalx.submission.signals import (
    before_submission_state_change,
    submission_state_change,
)
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    ResourceFactory,
    ReviewFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmitterAccessCodeFactory,
    TagFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import refresh

pytestmark = pytest.mark.unit


def test_generate_invite_code_length():
    code = generate_invite_code()
    assert len(code) == 32


def test_generate_invite_code_custom_length():
    code = generate_invite_code(length=16)
    assert len(code) == 16


def test_generate_invite_code_uses_valid_charset():
    code = generate_invite_code()
    assert all(c in Submission.code_charset for c in code)


@pytest.mark.django_db
def test_submission_image_path_format():
    submission = SubmissionFactory()
    path = submission_image_path(submission, "photo.jpg")
    assert path.startswith(f"{submission.event.slug}/submissions/{submission.code}/")


def test_submission_states_get_max_length():
    result = SubmissionStates.get_max_length()
    assert result == max(len(val) for val in SubmissionStates.values)


@pytest.mark.parametrize(
    ("state", "expected_color"),
    (
        ("submitted", "--color-info"),
        ("accepted", "--color-success"),
        ("confirmed", "--color-success"),
        ("rejected", "--color-danger"),
        ("canceled", "--color-grey"),
        ("withdrawn", "--color-grey"),
    ),
    ids=["submitted", "accepted", "confirmed", "rejected", "canceled", "withdrawn"],
)
def test_submission_states_get_color(state, expected_color):
    assert SubmissionStates.get_color(state) == expected_color


def test_submission_states_method_names():
    assert SubmissionStates.method_names["submitted"] == "make_submitted"
    assert SubmissionStates.method_names["accepted"] == "accept"
    assert SubmissionStates.method_names["rejected"] == "reject"
    assert SubmissionStates.method_names["confirmed"] == "confirm"
    assert SubmissionStates.method_names["canceled"] == "cancel"
    assert SubmissionStates.method_names["withdrawn"] == "withdraw"


def test_submission_states_accepted_states():
    assert SubmissionStates.accepted_states == ("accepted", "confirmed")


@pytest.mark.django_db
def test_submission_manager_excludes_drafts():
    submission = SubmissionFactory(state=SubmissionStates.DRAFT)
    with scopes_disabled():
        assert submission not in Submission.objects.all()
        assert submission in Submission.all_objects.all()


@pytest.mark.django_db
def test_submission_all_objects_includes_drafts():
    draft = SubmissionFactory(state=SubmissionStates.DRAFT)
    submitted = SubmissionFactory(event=draft.event)
    with scopes_disabled():
        all_subs = list(Submission.all_objects.all())
        assert draft in all_subs
        assert submitted in all_subs


@pytest.mark.django_db
def test_speaker_role_str():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    with scopes_disabled():
        submission.speakers.add(speaker)
        role = SpeakerRole.objects.get(submission=submission, speaker=speaker)
    assert str(role) == f"SpeakerRole(submission={submission.code}, speaker={speaker})"


@pytest.mark.django_db
def test_speaker_role_unique_together():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    with scopes_disabled():
        SpeakerRole.objects.create(submission=submission, speaker=speaker, position=0)
        with pytest.raises(IntegrityError):
            SpeakerRole.objects.create(
                submission=submission, speaker=speaker, position=1
            )


@pytest.mark.django_db
def test_speaker_role_ordering():
    submission = SubmissionFactory()
    speaker1 = SpeakerFactory(event=submission.event)
    speaker2 = SpeakerFactory(event=submission.event)
    with scopes_disabled():
        SpeakerRole.objects.create(submission=submission, speaker=speaker1, position=1)
        SpeakerRole.objects.create(submission=submission, speaker=speaker2, position=0)
        roles = list(SpeakerRole.objects.filter(submission=submission))
    assert roles[0].speaker == speaker2
    assert roles[1].speaker == speaker1


@pytest.mark.parametrize(
    ("has_pk", "expected_format"),
    ((True, "with_pk"), (False, "no_pk")),
    ids=["with_pk", "no_pk"],
)
@pytest.mark.django_db
def test_submission_str(has_pk, expected_format):
    if has_pk:
        submission = SubmissionFactory()
        expected = f"Submission(event={submission.event.slug}, code={submission.code}, title={submission.title}, state={submission.state})"
    else:
        submission = Submission(code="ABCDEF", title="Test Talk", state="submitted")
        expected = "Submission(code=ABCDEF, title=Test Talk, state=submitted)"
    assert str(submission) == expected


def test_submission_image_url_no_image():
    submission = Submission()
    assert submission.image_url == ""


@pytest.mark.django_db
def test_submission_log_parent():
    submission = SubmissionFactory()
    assert submission.log_parent == submission.event


@pytest.mark.django_db
def test_submission_get_duration_default():
    submission = SubmissionFactory(duration=None)
    assert submission.get_duration() == submission.submission_type.default_duration


@pytest.mark.django_db
def test_submission_get_duration_custom():
    submission = SubmissionFactory(duration=45)
    assert submission.get_duration() == 45


@pytest.mark.django_db
def test_submission_update_duration(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        submission.update_talk_slots()
        slot = event.wip_schedule.talks.get(submission=submission)
        slot.start = event.datetime_from
        slot.end = event.datetime_from + dt.timedelta(minutes=30)
        slot.save()
        submission.duration = 60
        submission.save()
        submission.update_duration()
        slot.refresh_from_db()
    assert slot.end == slot.start + dt.timedelta(minutes=60)


@pytest.mark.parametrize(
    ("data", "expected"),
    (
        ("", {}),
        (None, {}),
        ("{}", {}),
        ("[]", {}),
        ("[1,2,3]", {}),
        ('{"a": "b"}', {"a": "b"}),
        ("invalid_json;", {}),
    ),
    ids=[
        "empty_string",
        "none",
        "empty_dict",
        "list",
        "list_of_ints",
        "valid_dict",
        "invalid_json",
    ],
)
def test_submission_anonymised(data, expected):
    s = Submission()
    s.anonymised_data = data
    assert s.anonymised == expected


@pytest.mark.parametrize(
    ("data", "expected"),
    (
        ("{}", False),
        ('{"_anonymised": true}', True),
        ('{"_anonymised": false}', False),
        ("", False),
    ),
    ids=["empty_dict", "anonymised_true", "anonymised_false", "empty_string"],
)
def test_submission_is_anonymised(data, expected):
    s = Submission()
    s.anonymised_data = data
    assert s.is_anonymised is expected


@pytest.mark.django_db
def test_submission_reviewer_answers(event):
    submission = SubmissionFactory(event=event)
    q_visible = QuestionFactory(
        event=event, is_visible_to_reviewers=True, target="submission"
    )
    q_hidden = QuestionFactory(
        event=event, is_visible_to_reviewers=False, target="submission"
    )
    with scopes_disabled():
        a_visible = AnswerFactory(question=q_visible, submission=submission)
        AnswerFactory(question=q_hidden, submission=submission)
        result = list(submission.reviewer_answers)
    assert result == [a_visible]


@pytest.mark.django_db
def test_submission_export_duration():
    submission = SubmissionFactory(duration=90)
    assert submission.export_duration == "01:30"


@pytest.mark.django_db
def test_submission_export_duration_default():
    submission = SubmissionFactory(duration=None)
    expected_minutes = submission.submission_type.default_duration
    result = submission.export_duration
    hours = expected_minutes // 60
    minutes = expected_minutes % 60
    assert result == f"{hours:02}:{minutes:02}"


@pytest.mark.django_db
def test_submission_integer_uuid():
    submission = SubmissionFactory()
    uuid_val = submission.integer_uuid
    assert isinstance(uuid_val, int)
    assert uuid_val >= 0


@pytest.mark.django_db
def test_submission_integer_uuid_deterministic():
    submission = SubmissionFactory()
    assert submission.integer_uuid == submission.integer_uuid


@pytest.mark.django_db
def test_submission_integer_uuid_unique():
    s1 = SubmissionFactory()
    s2 = SubmissionFactory(event=s1.event)
    assert s1.integer_uuid != s2.integer_uuid


@pytest.mark.django_db
def test_submission_sorted_speakers(event):
    submission = SubmissionFactory(event=event)
    speaker1 = SpeakerFactory(event=event)
    speaker2 = SpeakerFactory(event=event)
    with scopes_disabled():
        SpeakerRole.objects.create(submission=submission, speaker=speaker1, position=2)
        SpeakerRole.objects.create(submission=submission, speaker=speaker2, position=1)
        result = list(submission.sorted_speakers)
    assert result == [speaker2, speaker1]


@pytest.mark.django_db
def test_submission_display_speaker_names(event):
    submission = SubmissionFactory(event=event)
    speaker1 = SpeakerFactory(event=event, name="Alice")
    speaker2 = SpeakerFactory(event=event, name="Bob")
    with scopes_disabled():
        SpeakerRole.objects.create(submission=submission, speaker=speaker1, position=0)
        SpeakerRole.objects.create(submission=submission, speaker=speaker2, position=1)
        result = submission.display_speaker_names
    assert result == "Alice, Bob"


@pytest.mark.django_db
def test_submission_display_title_with_speakers(event):
    submission = SubmissionFactory(event=event, title="My Talk")
    speaker = SpeakerFactory(event=event, name="Alice")
    with scopes_disabled():
        submission.speakers.add(speaker)
        result = submission.display_title_with_speakers
    assert "My Talk" in result
    assert "Alice" in result


@pytest.mark.django_db
def test_submission_display_title_with_speakers_no_speakers():
    submission = SubmissionFactory(title="Solo Talk")
    with scopes_disabled():
        result = submission.display_title_with_speakers
    assert "Solo Talk" in result


@pytest.mark.django_db
def test_submission_median_score(event):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        ReviewFactory(submission=submission, score=1)
        ReviewFactory(submission=submission, score=3)
        ReviewFactory(submission=submission, score=5)
        assert submission.median_score == statistics.median([1, 3, 5])


@pytest.mark.django_db
def test_submission_median_score_none():
    submission = SubmissionFactory()
    with scopes_disabled():
        assert submission.median_score is None


@pytest.mark.django_db
def test_submission_median_score_skips_none_scores(event):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        ReviewFactory(submission=submission, score=2)
        ReviewFactory(submission=submission, score=None)
        ReviewFactory(submission=submission, score=4)
        assert submission.median_score == statistics.median([2, 4])


@pytest.mark.django_db
def test_submission_mean_score(event):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        ReviewFactory(submission=submission, score=1)
        ReviewFactory(submission=submission, score=2)
        ReviewFactory(submission=submission, score=3)
        assert submission.mean_score == round(statistics.fmean([1, 2, 3]), 1)


@pytest.mark.django_db
def test_submission_mean_score_none():
    submission = SubmissionFactory()
    with scopes_disabled():
        assert submission.mean_score is None


@pytest.mark.django_db
def test_submission_save_sends_signal_on_create(register_signal_handler):
    """Creating a non-draft submission fires submission_state_change."""
    received = []

    def handler(signal, sender, **kwargs):
        received.append(kwargs)

    register_signal_handler(submission_state_change, handler)

    submission = SubmissionFactory(state=SubmissionStates.SUBMITTED)
    assert len(received) == 1
    assert received[0]["submission"] == submission
    assert received[0]["old_state"] is None


@pytest.mark.django_db
def test_submission_save_no_signal_on_draft_create(register_signal_handler):
    """Creating a draft submission does not fire submission_state_change."""
    received = []
    register_signal_handler(
        submission_state_change,
        lambda signal, sender, **kwargs: received.append(kwargs),
    )

    SubmissionFactory(state=SubmissionStates.DRAFT)
    assert received == []


@pytest.mark.django_db
def test_submission_set_state_noop(event):
    """Setting state to the same value clears pending_state and updates slots."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    with scope(event=event):
        submission.pending_state = SubmissionStates.ACCEPTED
        submission.save()
        submission.set_state(SubmissionStates.ACCEPTED)
        submission.refresh_from_db()
    assert submission.pending_state is None


@pytest.mark.parametrize(
    ("initial_state", "target_state"),
    (
        (SubmissionStates.SUBMITTED, SubmissionStates.REJECTED),
        (SubmissionStates.ACCEPTED, SubmissionStates.CANCELED),
        (SubmissionStates.SUBMITTED, SubmissionStates.WITHDRAWN),
    ),
    ids=["rejected", "canceled", "withdrawn"],
)
@pytest.mark.django_db
def test_submission_set_state_clears_is_featured(event, initial_state, target_state):
    submission = SubmissionFactory(event=event, state=initial_state, is_featured=True)
    with scope(event=event):
        submission.set_state(target_state)
        submission.refresh_from_db()
    assert submission.is_featured is False


@pytest.mark.django_db
def test_submission_set_state_signal_veto(event, register_signal_handler):
    """before_submission_state_change can veto state changes via SubmissionError."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    def veto_handler(signal, sender, **kwargs):
        raise SubmissionError("vetoed")

    register_signal_handler(before_submission_state_change, veto_handler)

    with scope(event=event), pytest.raises(SubmissionError, match="vetoed"):
        submission.set_state(SubmissionStates.ACCEPTED)

    submission.refresh_from_db()
    assert submission.state == SubmissionStates.SUBMITTED


@pytest.mark.django_db
def test_submission_set_state_no_signal_on_initial_submit(
    event, register_signal_handler
):
    """Initial submit from draft doesn't fire before_submission_state_change."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    called = []
    register_signal_handler(
        before_submission_state_change,
        lambda signal, sender, **kwargs: called.append(True),
    )

    with scope(event=event):
        submission.set_state(SubmissionStates.SUBMITTED)

    assert submission.state == SubmissionStates.SUBMITTED
    assert called == []


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.REJECTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.CANCELED,
        SubmissionStates.WITHDRAWN,
    ),
    ids=["submitted", "accepted", "rejected", "confirmed", "canceled", "withdrawn"],
)
@pytest.mark.django_db
def test_submission_accept(event, state):
    submission = SubmissionFactory(event=event, state=state)
    with scope(event=event):
        submission.accept()

    assert submission.state == SubmissionStates.ACCEPTED
    with scope(event=event):
        assert event.wip_schedule.talks.filter(submission=submission).exists()


@pytest.mark.django_db
def test_submission_accept_sends_mail_from_submitted(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
    with scope(event=event):
        mail_count_before = event.queued_mails.count()
        submission.accept()
        assert event.queued_mails.count() == mail_count_before + 1


@pytest.mark.django_db
def test_submission_accept_no_mail_from_confirmed(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
    with scope(event=event):
        mail_count_before = event.queued_mails.count()
        submission.accept()
        assert event.queued_mails.count() == mail_count_before


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.CANCELED,
        SubmissionStates.WITHDRAWN,
    ),
    ids=["submitted", "accepted", "confirmed", "canceled", "withdrawn"],
)
@pytest.mark.django_db
def test_submission_reject(event, state):
    submission = SubmissionFactory(event=event, state=state)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
    with scope(event=event):
        submission.reject()

    assert submission.state == SubmissionStates.REJECTED
    with scope(event=event):
        assert not event.wip_schedule.talks.filter(submission=submission).exists()


@pytest.mark.django_db
def test_submission_reject_sends_mail(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
    with scope(event=event):
        mail_count_before = event.queued_mails.count()
        submission.reject()
        assert event.queued_mails.count() == mail_count_before + 1


@pytest.mark.django_db
def test_submission_reject_no_duplicate_mail(event):
    """Rejecting an already-rejected submission doesn't send a second mail."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.REJECTED)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
    with scope(event=event):
        mail_count_before = event.queued_mails.count()
        submission.reject()
        assert event.queued_mails.count() == mail_count_before


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.REJECTED,
        SubmissionStates.CANCELED,
    ),
    ids=["submitted", "accepted", "confirmed", "rejected", "canceled"],
)
@pytest.mark.django_db
def test_submission_withdraw(event, state):
    submission = SubmissionFactory(event=event, state=state)
    with scope(event=event):
        submission.withdraw()
    assert submission.state == SubmissionStates.WITHDRAWN
    with scope(event=event):
        assert not event.wip_schedule.talks.filter(submission=submission).exists()


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.REJECTED,
        SubmissionStates.WITHDRAWN,
    ),
    ids=["submitted", "accepted", "confirmed", "rejected", "withdrawn"],
)
@pytest.mark.django_db
def test_submission_cancel(event, state):
    submission = SubmissionFactory(event=event, state=state)
    with scope(event=event):
        submission.cancel()
    assert submission.state == SubmissionStates.CANCELED
    with scope(event=event):
        assert not event.wip_schedule.talks.filter(submission=submission).exists()


@pytest.mark.django_db
def test_submission_confirm(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    with scope(event=event):
        submission.confirm()
    assert submission.state == SubmissionStates.CONFIRMED


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.REJECTED,
        SubmissionStates.CANCELED,
        SubmissionStates.WITHDRAWN,
    ),
    ids=["accepted", "confirmed", "rejected", "canceled", "withdrawn"],
)
@pytest.mark.django_db
def test_submission_make_submitted(event, state):
    submission = SubmissionFactory(event=event, state=state)
    with scope(event=event):
        submission.make_submitted()
    assert submission.state == SubmissionStates.SUBMITTED


@pytest.mark.django_db
def test_submission_make_submitted_from_draft_no_log(event):
    """make_submitted from DRAFT doesn't log because it's the initial submission."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    with scope(event=event):
        submission.make_submitted()
        assert submission.state == SubmissionStates.SUBMITTED
        assert submission.logged_actions().count() == 0


@pytest.mark.django_db
def test_submission_make_submitted_from_accepted_logs(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    with scope(event=event):
        submission.make_submitted()
        assert submission.logged_actions().count() == 1


@pytest.mark.django_db
def test_submission_apply_pending_state_noop(event):
    """apply_pending_state does nothing if pending_state is None."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.pending_state = None
        submission.save()
        submission.apply_pending_state()
    assert submission.state == SubmissionStates.SUBMITTED


@pytest.mark.django_db
def test_submission_apply_pending_state_same_as_state(event):
    """If pending_state equals current state, it's cleared without action."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    with scope(event=event):
        submission.pending_state = SubmissionStates.ACCEPTED
        submission.save()
        submission.apply_pending_state()
    submission.refresh_from_db()
    assert submission.pending_state is None
    assert submission.state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
def test_submission_apply_pending_state_transitions(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.pending_state = SubmissionStates.ACCEPTED
        submission.save()
        submission.apply_pending_state()
    assert submission.state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
def test_submission_update_talk_slots_creates_slots(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.accept()
        assert event.wip_schedule.talks.filter(submission=submission).count() == 1


@pytest.mark.django_db
def test_submission_update_talk_slots_deletes_on_reject(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.accept()
        assert event.wip_schedule.talks.filter(submission=submission).count() == 1
        submission.reject()
        assert event.wip_schedule.talks.filter(submission=submission).count() == 0


@pytest.mark.django_db
def test_submission_update_talk_slots_adjusts_count(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.accept()
        assert event.wip_schedule.talks.filter(submission=submission).count() == 1
        submission.slot_count = 3
        submission.save()
        submission.update_talk_slots()
        assert event.wip_schedule.talks.filter(submission=submission).count() == 3


@pytest.mark.django_db
def test_submission_update_talk_slots_reduces_count(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.accept()
        submission.slot_count = 3
        submission.save()
        submission.update_talk_slots()
        assert event.wip_schedule.talks.filter(submission=submission).count() == 3
        submission.slot_count = 1
        submission.save()
        submission.update_talk_slots()
        assert event.wip_schedule.talks.filter(submission=submission).count() == 1


@pytest.mark.django_db
def test_submission_update_talk_slots_visibility_confirmed(event):
    """Confirmed submissions have visible talk slots."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.accept()
        submission.confirm()
        slot = event.wip_schedule.talks.get(submission=submission)
    assert slot.is_visible is True


@pytest.mark.django_db
def test_submission_update_talk_slots_visibility_accepted(event):
    """Accepted (not confirmed) submissions have invisible talk slots."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.accept()
        slot = event.wip_schedule.talks.get(submission=submission)
    assert slot.is_visible is False


@pytest.mark.django_db
def test_submission_update_talk_slots_pending_accepted(event):
    """Slots are created when pending_state is accepted."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        assert event.wip_schedule.talks.filter(submission=submission).count() == 0
        submission.pending_state = SubmissionStates.ACCEPTED
        submission.save()
        submission.update_talk_slots()
        assert event.wip_schedule.talks.filter(submission=submission).count() == 1


@pytest.mark.parametrize(
    ("content_locale", "event_locales", "fallback", "expected_locale"),
    (
        ("en", ["en", "de"], None, "en"),
        ("de", ["en", "de"], None, "de"),
        ("fr", ["en", "de"], "de", "de"),
        ("fr", ["en", "de"], "ja", "en"),
        ("fr", ["en", "de"], None, "en"),
    ),
    ids=[
        "content_locale_in_event",
        "content_locale_de_in_event",
        "fallback_used",
        "fallback_not_in_event",
        "no_fallback",
    ],
)
@pytest.mark.django_db
def test_submission_get_email_locale(
    content_locale, event_locales, fallback, expected_locale
):
    event = EventFactory(locale_array=",".join(event_locales), locale=event_locales[0])
    submission = SubmissionFactory(event=event, content_locale=content_locale)
    assert submission.get_email_locale(fallback=fallback) == expected_locale


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        (SubmissionStates.ACCEPTED, 1),
        (SubmissionStates.REJECTED, 1),
        (SubmissionStates.SUBMITTED, 0),
        (SubmissionStates.CONFIRMED, 0),
        (SubmissionStates.CANCELED, 0),
    ),
    ids=["accepted", "rejected", "submitted", "confirmed", "canceled"],
)
@pytest.mark.django_db
def test_submission_send_state_mail(event, state, expected):
    submission = SubmissionFactory(event=event, state=state)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
    with scope(event=event):
        mail_count_before = event.queued_mails.count()
        submission.send_state_mail()
        assert event.queued_mails.count() == mail_count_before + expected


@pytest.mark.django_db
def test_submission_delete_removes_related(event):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        AnswerFactory(question=QuestionFactory(event=event), submission=submission)
        ResourceFactory(submission=submission)
    sub_pk = submission.pk
    with scope(event=event):
        submission.delete()
    with scopes_disabled():
        assert not Submission.all_objects.filter(pk=sub_pk).exists()
        assert not Answer.objects.filter(submission_id=sub_pk).exists()
        assert not Resource.objects.filter(submission_id=sub_pk).exists()


@pytest.mark.django_db
def test_submission_delete_cleans_up_resource_files(event):
    submission = SubmissionFactory(event=event)
    f = SimpleUploadedFile("testresource.txt", b"test content")
    resource = Resource.objects.create(
        submission=submission, resource=f, description="Test resource"
    )
    file_path = resource.resource.path
    assert resource.resource.storage.exists(file_path)
    with scope(event=event):
        submission.delete()
    assert not resource.resource.storage.exists(file_path)


@pytest.mark.django_db
def test_submission_get_content_for_mail(event):
    submission = SubmissionFactory(
        event=event,
        title="My Talk",
        abstract="An abstract",
        description="A description",
        notes="Some notes",
    )
    with scopes_disabled():
        content = submission.get_content_for_mail()
    assert "My Talk" in content
    assert "An abstract" in content
    assert "A description" in content
    assert "Some notes" in content


@pytest.mark.django_db
def test_submission_get_content_for_mail_with_boolean_answer(event):
    submission = SubmissionFactory(event=event)
    q = QuestionFactory(event=event, variant="boolean", target="submission")
    with scopes_disabled():
        Answer.objects.create(question=q, answer="True", submission=submission)
        content = submission.get_content_for_mail()
    assert str(q.question) in content


@pytest.mark.django_db
def test_submission_get_content_for_mail_with_file_answer(event):
    submission = SubmissionFactory(event=event)
    q = QuestionFactory(event=event, variant="file", target="submission")
    f = SimpleUploadedFile("test.txt", b"content")
    with scopes_disabled():
        Answer.objects.create(question=q, answer_file=f, submission=submission)
        content = submission.get_content_for_mail()
    assert str(q.question) in content


@pytest.mark.django_db
def test_submission_get_instance_data_with_resources(event):
    submission = SubmissionFactory(event=event)
    ResourceFactory(
        submission=submission, link="https://example.com", description="Slides"
    )
    ResourceFactory(submission=submission, link="https://example.com/2", description="")
    with scopes_disabled():
        data = submission.get_instance_data()
    assert "resources" in data
    assert "[Slides](https://example.com)" in data["resources"]
    assert "https://example.com/2" in data["resources"]


@pytest.mark.django_db
def test_submission_get_instance_data_with_tags(event):
    submission = SubmissionFactory(event=event)
    tag = TagFactory(event=event, tag="python")
    with scopes_disabled():
        submission.tags.add(tag)
        data = submission.get_instance_data()
    assert "python" in data["tags"]


@pytest.mark.django_db
def test_submission_editable_draft_no_deadline(event):
    """Draft submissions are editable when there's no deadline."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    with scope(event=event):
        event.cfp.deadline = None
        event.cfp.save()
        submission.submission_type.deadline = None
        submission.submission_type.save()
    assert submission.editable is True


@pytest.mark.django_db
def test_submission_editable_draft_past_deadline(event):
    """Draft submissions are not editable after deadline (without access code)."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    with scope(event=event):
        event.cfp.deadline = now() - timedelta(hours=1)
        event.cfp.save()
        submission.submission_type.deadline = None
        submission.submission_type.save()
    assert submission.editable is False


@pytest.mark.django_db
def test_submission_editable_draft_track_requires_access_code(event):
    """Draft with track requiring access code is not editable without one."""
    track = TrackFactory(event=event, requires_access_code=True)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.DRAFT, track=track
    )
    assert submission.editable is False


@pytest.mark.django_db
def test_submission_editable_draft_type_requires_access_code(event):
    """Draft with type requiring access code is not editable without one."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    with scopes_disabled():
        submission.submission_type.requires_access_code = True
        submission.submission_type.save()
    assert submission.editable is False


@pytest.mark.django_db
def test_submission_editable_draft_with_valid_access_code(event):
    """Draft with valid access code is editable even past deadline."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    with scope(event=event):
        event.cfp.deadline = now() - timedelta(hours=1)
        event.cfp.save()
    access_code = SubmitterAccessCodeFactory(event=event)
    with scopes_disabled():
        submission.access_code = access_code
        submission.save()
    assert submission.editable is True


@pytest.mark.django_db
def test_submission_editable_submitted_speakers_cant_edit(event):
    """Submitted submissions not editable when feature flag is off."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    event.feature_flags = {
        **event.feature_flags,
        "speakers_can_edit_submissions": False,
    }
    event.save()
    assert submission.editable is False


@pytest.mark.django_db
def test_submission_editable_submitted_with_feature_flag_and_open_deadline(event):
    """Submitted submissions are editable when feature flag is on and deadline open."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    event.feature_flags = {**event.feature_flags, "speakers_can_edit_submissions": True}
    event.save()
    with scope(event=event):
        event.cfp.deadline = now() + timedelta(hours=1)
        event.cfp.save()
        submission.submission_type.deadline = None
        submission.submission_type.save()
    assert submission.editable is True


@pytest.mark.django_db
def test_submission_editable_accepted_with_feature_flag(event):
    """Accepted submissions are editable when feature flag is on."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    event.feature_flags = {**event.feature_flags, "speakers_can_edit_submissions": True}
    event.save()
    assert submission.editable is True


@pytest.mark.django_db
def test_submission_editable_rejected_not_editable(event):
    """Rejected submissions are not editable."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.REJECTED)
    event.feature_flags = {**event.feature_flags, "speakers_can_edit_submissions": True}
    event.save()
    assert submission.editable is False


@pytest.mark.django_db
def test_submission_user_state_review_after_deadline(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        event.cfp.deadline = now() - timedelta(hours=1)
        event.cfp.save()
        submission.submission_type.deadline = None
        submission.submission_type.save()
    assert submission.user_state == "review"


@pytest.mark.django_db
def test_submission_user_state_submitted_before_deadline(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        event.cfp.deadline = now() + timedelta(hours=1)
        event.cfp.save()
        submission.submission_type.deadline = None
        submission.submission_type.save()
    assert submission.user_state == SubmissionStates.SUBMITTED


@pytest.mark.django_db
def test_submission_user_state_accepted():
    submission = SubmissionFactory(state=SubmissionStates.ACCEPTED)
    assert submission.user_state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
def test_submission_send_invite_requires_sender(event):
    submission = SubmissionFactory(event=event)
    with pytest.raises(ValueError, match="sender"):
        submission.send_invite("test@example.com")


@pytest.mark.django_db
def test_submission_send_invite_with_from(event):
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    djmail.outbox = []
    with scope(event=event):
        submission.send_invite("test@example.com", _from=user)
    assert len(djmail.outbox) == 1
    assert "test@example.com" in djmail.outbox[0].to


@pytest.mark.django_db
def test_submission_send_invite_with_custom_subject_and_text(event):
    submission = SubmissionFactory(event=event)
    djmail.outbox = []
    with scope(event=event):
        submission.send_invite(
            "test@example.com", subject="Join us!", text="Please speak at our event."
        )
    assert len(djmail.outbox) == 1
    assert "Join us!" in djmail.outbox[0].subject
    assert "Please speak at our event." in djmail.outbox[0].body


@pytest.mark.django_db
def test_submission_send_invite_multiple_recipients(event):
    submission = SubmissionFactory(event=event)
    djmail.outbox = []
    with scope(event=event):
        submission.send_invite(
            "a@example.com,b@example.com", subject="Join!", text="Please speak."
        )
    assert len(djmail.outbox) == 2


@pytest.mark.django_db
def test_submission_invite_speaker_existing_user(event):
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    with scopes_disabled():
        speaker = submission.invite_speaker(user.email, user=user)
        assert speaker is not None
        assert submission.speakers.filter(pk=speaker.pk).exists()


@pytest.mark.django_db
def test_submission_invite_speaker_new_user(event):
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    with scopes_disabled():
        speaker = submission.invite_speaker(
            "newperson@example.com", name="New Person", user=user
        )
        assert speaker is not None
        assert submission.speakers.filter(pk=speaker.pk).exists()


@pytest.mark.django_db
def test_submission_add_speaker(event):
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    with scopes_disabled():
        speaker = submission.add_speaker(user=user)
        assert submission.speakers.filter(pk=speaker.pk).exists()


@pytest.mark.django_db
def test_submission_add_speaker_sets_position(event):
    submission = SubmissionFactory(event=event)
    speaker1 = SpeakerFactory(event=event)
    speaker2 = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.add_speaker(speaker=speaker1)
        submission.add_speaker(speaker=speaker2)
        pos1 = SpeakerRole.objects.get(submission=submission, speaker=speaker1).position
        pos2 = SpeakerRole.objects.get(submission=submission, speaker=speaker2).position
    assert pos2 > pos1


@pytest.mark.django_db
def test_submission_add_speaker_logs_with_user(event):
    submission = SubmissionFactory(event=event)
    log_user = UserFactory()
    target_user = UserFactory()
    with scopes_disabled():
        submission.add_speaker(user=target_user, log_user=log_user)
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.speakers.add")
            .exists()
        )


@pytest.mark.django_db
def test_submission_remove_speaker(event):
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
        submission.remove_speaker(speaker)
        assert not submission.speakers.filter(pk=speaker.pk).exists()


@pytest.mark.django_db
def test_submission_remove_speaker_logs(event):
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
        submission.remove_speaker(speaker)
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.speakers.remove")
            .exists()
        )


@pytest.mark.django_db
def test_submission_remove_speaker_nonexistent(event):
    """Removing a speaker who isn't on the submission does nothing."""
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.remove_speaker(speaker)
        assert submission.logged_actions().count() == 0


@pytest.mark.django_db
def test_submission_add_favourite(event):
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    with scopes_disabled():
        submission.add_favourite(user)
        assert SubmissionFavourite.objects.filter(
            user=user, submission=submission
        ).exists()


@pytest.mark.django_db
def test_submission_add_favourite_idempotent(event):
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    with scopes_disabled():
        submission.add_favourite(user)
        submission.add_favourite(user)
        assert (
            SubmissionFavourite.objects.filter(user=user, submission=submission).count()
            == 1
        )


@pytest.mark.django_db
def test_submission_remove_favourite(event):
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    with scopes_disabled():
        submission.add_favourite(user)
        submission.remove_favourite(user)
        assert not SubmissionFavourite.objects.filter(
            user=user, submission=submission
        ).exists()


@pytest.mark.parametrize(
    ("state", "expected_count"),
    ((SubmissionStates.DRAFT, 0), (SubmissionStates.SUBMITTED, 1)),
    ids=["draft_skipped", "submitted_logged"],
)
@pytest.mark.django_db
def test_submission_log_action(event, state, expected_count):
    """log_action is a no-op for draft submissions but works for non-drafts."""
    submission = SubmissionFactory(event=event, state=state)
    with scopes_disabled():
        submission.log_action("pretalx.submission.test")
        assert submission.logged_actions().count() == expected_count


@pytest.mark.django_db
def test_submission_slot_no_current_schedule(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        assert submission.slot is None


@pytest.mark.django_db
def test_submission_current_slots_no_current_schedule(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        assert submission.current_slots is None


@pytest.mark.django_db
def test_submission_public_slots_no_visible_agenda(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    event.is_public = False
    event.save()
    with scope(event=event):
        assert submission.public_slots == []


@pytest.mark.django_db
def test_submission_does_accept_feedback_no_slot(event):
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        assert submission.does_accept_feedback is False


@pytest.mark.django_db
def test_submission_queryset_with_sorted_speakers(event):
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
        qs = Submission.objects.all().with_sorted_speakers()
        result = list(qs)
    assert result == [submission]


@pytest.mark.django_db
def test_submission_invitation_str(event):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email="test@example.com"
        )
    result = str(invitation)
    assert submission.title in result
    assert "test@example.com" in result


@pytest.mark.django_db
def test_submission_invitation_event(event):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email="test@example.com"
        )
    assert invitation.event == event


@pytest.mark.django_db
def test_submission_invitation_send(event):
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    with scopes_disabled():
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email="test@example.com"
        )
    with scope(event=event):
        mail = invitation.send(_from=user)
    assert mail is not None


@pytest.mark.django_db
def test_submission_invitation_send_requires_from(event):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email="test@example.com"
        )
    with pytest.raises(ValueError, match="sender"):
        invitation.send()


@pytest.mark.django_db
def test_submission_invitation_retract(event):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email="test@example.com"
        )
        invitation.retract()
        assert not SubmissionInvitation.objects.filter(pk=invitation.pk).exists()


@pytest.mark.django_db
def test_submission_invitation_retract_logs(event):
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    with scopes_disabled():
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email="test@example.com"
        )
        invitation.retract(person=user)
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.invitation.retract")
            .exists()
        )


@pytest.mark.django_db
def test_submission_invitation_unique_together(event):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        SubmissionInvitation.objects.create(
            submission=submission, email="test@example.com"
        )
        with pytest.raises(IntegrityError):
            SubmissionInvitation.objects.create(
                submission=submission, email="test@example.com"
            )


@pytest.mark.django_db
def test_submission_score_categories_with_track(event):
    track = TrackFactory(event=event)
    cat_all = ReviewScoreCategory.objects.create(
        event=event, name="General", active=True
    )
    cat_track = ReviewScoreCategory.objects.create(
        event=event, name="Track-specific", active=True
    )
    cat_track.limit_tracks.add(track)
    cat_inactive = ReviewScoreCategory.objects.create(
        event=event, name="Inactive", active=False
    )

    submission = SubmissionFactory(event=event, track=track)
    with scopes_disabled():
        categories = list(submission.score_categories)
    assert cat_all in categories
    assert cat_track in categories
    assert cat_inactive not in categories


@pytest.mark.django_db
def test_submission_score_categories_no_track(event):
    track = TrackFactory(event=event)
    cat_all = ReviewScoreCategory.objects.create(
        event=event, name="General", active=True
    )
    cat_track = ReviewScoreCategory.objects.create(
        event=event, name="Track-specific", active=True
    )
    cat_track.limit_tracks.add(track)

    submission = SubmissionFactory(event=event, track=None)
    with scopes_disabled():
        categories = list(submission.score_categories)
    assert cat_all in categories
    assert cat_track not in categories


def test_submission_editable_unsaved():
    """Unsaved submissions (no event FK) are always editable."""
    submission = Submission()
    assert submission.editable is True


@pytest.mark.django_db
def test_submission_public_answers(event):
    submission = SubmissionFactory(event=event)
    q_public = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SUBMISSION
    )
    q_private = QuestionFactory(
        event=event, is_public=False, target=QuestionTarget.SUBMISSION
    )
    with scopes_disabled():
        a_public = AnswerFactory(question=q_public, submission=submission)
        AnswerFactory(question=q_private, submission=submission)
        result = list(submission.public_answers)
    assert result == [a_public]


@pytest.mark.django_db
def test_submission_public_answers_with_track(event):
    track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    q_track = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SUBMISSION
    )
    q_other_track = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SUBMISSION
    )
    other_track = TrackFactory(event=event)
    with scopes_disabled():
        q_track.tracks.add(track)
        q_other_track.tracks.add(other_track)
        a_track = AnswerFactory(question=q_track, submission=submission)
        AnswerFactory(question=q_other_track, submission=submission)
        result = list(submission.public_answers)
    assert a_track in result
    assert all(a.question != q_other_track for a in result)


@pytest.mark.django_db
def test_submission_get_instance_data_resource_label_only(event):
    """Resource with description but no link shows as 'File: label'."""
    submission = SubmissionFactory(event=event)
    ResourceFactory(submission=submission, link="", description="My Slides")
    with scopes_disabled():
        data = submission.get_instance_data()
    assert "resources" in data
    assert "My Slides" in data["resources"]


@pytest.mark.django_db
def test_submission_get_instance_data_resource_filename(event):
    """Resource with file but no link or description uses filename."""
    submission = SubmissionFactory(event=event)
    f = SimpleUploadedFile("slides.pdf", b"content")
    Resource.objects.create(
        submission=submission, resource=f, description=None, link=None
    )
    with scopes_disabled():
        data = submission.get_instance_data()
    assert "resources" in data
    assert "slides" in data["resources"]


@pytest.mark.django_db
def test_submission_get_instance_data_resource_no_file_no_link(event):
    """Resource with no link, no description, and no file is skipped."""
    submission = SubmissionFactory(event=event)
    Resource.objects.create(
        submission=submission, resource=None, description=None, link=None
    )
    with scopes_disabled():
        data = submission.get_instance_data()
    assert "resources" not in data


@pytest.mark.django_db
def test_submission_update_review_scores(event):
    submission = SubmissionFactory(event=event)
    cat = ReviewScoreCategory.objects.create(
        event=event, name="Quality", active=True, weight=1
    )
    score_option = ReviewScore.objects.create(category=cat, value=5)
    with scopes_disabled():
        review = ReviewFactory(submission=submission, score=None)
        review.scores.add(score_option)
        submission.update_review_scores()
        review.refresh_from_db()
    assert review.score is not None


@pytest.mark.django_db
def test_submission_send_initial_mails(event):
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    with scopes_disabled():
        submission.speakers.add(speaker)
    djmail.outbox = []
    with scope(event=event):
        submission.send_initial_mails(user)
    assert len(djmail.outbox) == 1
    assert user.email in djmail.outbox[0].to


@pytest.mark.django_db
def test_submission_get_content_locale_display(event):
    submission = SubmissionFactory(event=event, content_locale="en")
    result = submission.get_content_locale_display()
    assert result == "English"


@pytest.mark.django_db
def test_submission_does_accept_feedback_with_past_slot(event):
    """does_accept_feedback is True when the slot has started."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    with scope(event=event):
        submission.update_talk_slots()
        slot = event.wip_schedule.talks.get(submission=submission)
        slot.start = now() - timedelta(hours=2)
        slot.end = now() - timedelta(hours=1)
        slot.room = room
        slot.save()
        event.release_schedule(name="v1")
    with scope(event=event):
        assert submission.does_accept_feedback is True


@pytest.mark.django_db
def test_submission_public_slots_with_visible_agenda(event):
    """public_slots delegates to current_slots when the agenda is visible,
    rather than returning the early-exit empty list."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    event.is_public = True
    event.feature_flags = {**event.feature_flags, "show_schedule": True}
    event.save()
    with scope(event=event):
        submission.update_talk_slots()
        event.release_schedule(name="v1")
        result = submission.public_slots
    assert result is not None


@pytest.mark.django_db
def test_submission_current_slots_with_schedule(event):
    """current_slots returns a queryset (not None) when a schedule is released."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        submission.update_talk_slots()
        event.release_schedule(name="v1")
        result = submission.current_slots
    assert result is not None


@pytest.mark.django_db
def test_submission_sorted_speakers_with_prefetch(event):
    """sorted_speakers uses prefetch cache when available."""
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
        qs = Submission.objects.all().with_sorted_speakers()
        sub = qs.get(pk=submission.pk)
        result = list(sub.sorted_speakers)
    assert result == [speaker]


@pytest.mark.django_db
def test_submission_active_resources(event):
    submission = SubmissionFactory(event=event)
    r_link = ResourceFactory(submission=submission, link="https://example.com")
    ResourceFactory(submission=submission, link="")
    with scopes_disabled():
        result = list(submission.active_resources)
    assert result == [r_link]


@pytest.mark.django_db
def test_submission_private_resources(event):
    submission = SubmissionFactory(event=event)
    ResourceFactory(submission=submission, link="https://example.com", is_public=False)
    ResourceFactory(submission=submission, link="https://public.com", is_public=True)
    with scopes_disabled():
        result = list(submission.private_resources)
    assert len(result) == 1
    assert result[0].is_public is False


@pytest.mark.django_db
def test_submission_public_resources(event):
    submission = SubmissionFactory(event=event)
    ResourceFactory(submission=submission, link="https://example.com", is_public=False)
    r_public = ResourceFactory(
        submission=submission, link="https://public.com", is_public=True
    )
    with scopes_disabled():
        result = list(submission.public_resources)
    assert result == [r_public]


@pytest.mark.django_db
def test_submission_availabilities(event):
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
        Availability.objects.create(
            event=event,
            person=speaker,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=4),
        )
    with scope(event=event):
        result = submission.availabilities
    assert len(result) == 1
    assert result[0].start == event.datetime_from
    assert result[0].end == event.datetime_from + dt.timedelta(hours=4)


@pytest.mark.django_db
def test_submission_get_content_for_mail_with_text_answer(event):
    """Regular text answers appear in mail content."""
    submission = SubmissionFactory(event=event)
    q = QuestionFactory(event=event, variant="string", target="submission")
    with scopes_disabled():
        Answer.objects.create(question=q, answer="My answer", submission=submission)
        content = submission.get_content_for_mail()
    assert "My answer" in content


@pytest.mark.django_db
def test_submission_get_content_for_mail_with_empty_answer(event):
    """Text answers with no content show a dash."""
    submission = SubmissionFactory(event=event)
    q = QuestionFactory(event=event, variant="string", target="submission")
    with scopes_disabled():
        Answer.objects.create(question=q, answer="", submission=submission)
        content = submission.get_content_for_mail()
    assert str(q.question) in content
    assert "-" in content


def test_submission_get_instance_data_unsaved():
    """get_instance_data skips resources/tags for unsaved submissions."""
    submission = Submission(title="Unsaved", code="ABCDEF")
    data = submission.get_instance_data()
    assert "resources" not in data
    assert "tags" not in data


@pytest.mark.django_db
def test_submission_send_initial_mails_with_notification(event):
    """send_initial_mails sends an internal notification when setting is on."""
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    with scopes_disabled():
        submission.speakers.add(speaker)
    event.mail_settings = {**event.mail_settings, "mail_on_new_submission": True}
    event.save()
    djmail.outbox = []
    with scope(event=event):
        submission.send_initial_mails(user)
    assert len(djmail.outbox) == 2


@pytest.mark.django_db
def test_submission_send_initial_mails_template_already_has_content(event):
    """send_initial_mails doesn't duplicate full_submission_content placeholder."""
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    with scopes_disabled():
        submission.speakers.add(speaker)
    with scope(event=event):
        template = event.get_mail_template(MailTemplateRoles.NEW_SUBMISSION)
        template.text = str(template.text) + "\n{full_submission_content}"
        template.save()
        original_text = str(template.text)
        submission.send_initial_mails(user)
        template.refresh_from_db()
        assert str(template.text) == original_text


@pytest.mark.django_db
def test_submission_editable_submitted_past_deadline_with_review_phase(event):
    """Submitted is editable past deadline if active review phase allows it."""

    event.feature_flags = {**event.feature_flags, "speakers_can_edit_submissions": True}
    event.save()
    with scope(event=event):
        event.cfp.deadline = now() - timedelta(hours=1)
        event.cfp.save()
        ReviewPhase.objects.filter(event=event).update(is_active=False)
        ReviewPhase.objects.create(
            event=event,
            name="Open Review",
            position=0,
            speakers_can_change_submissions=True,
            is_active=True,
        )
    event = refresh(event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scopes_disabled():
        submission.submission_type.deadline = None
        submission.submission_type.save()
    with scope(event=event):
        assert submission.editable is True
