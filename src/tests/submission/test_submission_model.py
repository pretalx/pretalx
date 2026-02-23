# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now, timedelta
from django_scopes import scope

from pretalx.common.exceptions import SubmissionError
from pretalx.submission.models import (
    Answer,
    Resource,
    Submission,
    SubmissionStates,
    SubmitterAccessCode,
)
from pretalx.submission.models.submission import submission_image_path


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
)
@pytest.mark.django_db
def test_accept_success(submission, state):
    submission.event.plugins = "tests"
    submission.event.save()
    with scope(event=submission.event):
        submission.state = state
        submission.save()
        count = submission.logged_actions().count()

        submission.accept()
        assert submission.state == SubmissionStates.ACCEPTED
        assert submission.event.queued_mails.count() == int(
            state not in (SubmissionStates.CONFIRMED, SubmissionStates.ACCEPTED)
        )
        assert submission.logged_actions().count() == (count + 1)
        assert submission.event.wip_schedule.talks.count() == 1
        assert getattr(submission, "_state_change_called", 0) == (
            1 if state != SubmissionStates.ACCEPTED else 0
        )


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.CANCELED,
        SubmissionStates.WITHDRAWN,
    ),
)
@pytest.mark.django_db
def test_reject_success(submission, state):
    submission.event.plugins = "tests"
    submission.event.save()
    with scope(event=submission.event):
        submission.state = state
        submission.save()
        count = submission.logged_actions().count()

        submission.reject()

        assert submission.state == SubmissionStates.REJECTED
        assert submission.logged_actions().count() == (count + 1)
        assert submission.event.queued_mails.count() == 1
        assert submission.event.wip_schedule.talks.count() == 0
        assert submission._state_change_called == 1


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.REJECTED,
        SubmissionStates.WITHDRAWN,
    ),
)
@pytest.mark.django_db
def test_cancel_success(submission, state):
    with scope(event=submission.event):
        submission.state = state
        submission.save()
        count = submission.logged_actions().count()

        submission.cancel()

        assert submission.state == SubmissionStates.CANCELED
        assert submission.logged_actions().count() == (count + 1)
        assert submission.event.queued_mails.count() == 0
        assert submission.event.wip_schedule.talks.count() == 0


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.REJECTED,
        SubmissionStates.CANCELED,
    ),
)
@pytest.mark.django_db
def test_withdraw_success(submission, state):
    with scope(event=submission.event):
        submission.state = state
        submission.save()
        count = submission.logged_actions().count()

        submission.withdraw()

        assert submission.state == SubmissionStates.WITHDRAWN
        assert submission.logged_actions().count() == (count + 1)
        assert submission.event.queued_mails.count() == 0
        assert submission.event.wip_schedule.talks.count() == 0


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.REJECTED,
        SubmissionStates.CANCELED,
        SubmissionStates.WITHDRAWN,
    ),
)
@pytest.mark.django_db
def test_make_submitted(submission, state):
    with scope(event=submission.event):
        submission.state = state
        submission.save()

        submission.make_submitted()
        assert submission.state == SubmissionStates.SUBMITTED
        assert submission.event.queued_mails.count() == 0
        assert submission.event.wip_schedule.talks.count() == 0
        assert submission.logged_actions().count() == 1


@pytest.mark.django_db
def test_submission_remove_removes_submission(submission, answer):
    with scope(event=submission.event):
        count = Answer.objects.count()
        answer_count = submission.answers.count()
        submission_count = Submission.all_objects.count()
        assert answer_count
        submission.delete()
        assert Submission.all_objects.count() == submission_count - 1
        assert Answer.objects.count() == count - answer_count


@pytest.mark.django_db
def test_submission_delete_cleans_up_resource_files(submission):
    f = SimpleUploadedFile("testresource.txt", b"test content")
    resource = Resource.objects.create(
        submission=submission,
        resource=f,
        description="Test resource",
    )
    file_path = resource.resource.path
    assert resource.resource.storage.exists(file_path)

    with scope(event=submission.event):
        submission.delete()

    assert not resource.resource.storage.exists(file_path)


@pytest.mark.django_db
def test_nonstandard_duration(submission):
    assert submission.get_duration() == submission.submission_type.default_duration
    submission.duration = 9
    assert submission.get_duration() == 9


@pytest.mark.django_db
def test_submission_image_path(submission):
    assert submission_image_path(submission, "foo").startswith(
        f"{submission.event.slug}/submissions/{submission.code}"
    )


@pytest.mark.django_db
def test_submission_change_slot_count(accepted_submission):
    with scope(event=accepted_submission.event):
        assert (
            accepted_submission.slots.filter(
                schedule=accepted_submission.event.wip_schedule
            ).count()
            == 1
        )
        accepted_submission.event.feature_flags["present_multiple_times"] = True
        accepted_submission.event.save()
        accepted_submission.slot_count = 2
        accepted_submission.save()
        accepted_submission.accept()
        assert (
            accepted_submission.slots.filter(
                schedule=accepted_submission.event.wip_schedule
            ).count()
            == 2
        )
        accepted_submission.slot_count = 1
        accepted_submission.save()
        accepted_submission.accept()
        assert (
            accepted_submission.slots.filter(
                schedule=accepted_submission.event.wip_schedule
            ).count()
            == 1
        )


@pytest.mark.django_db
def test_submission_assign_code(submission, monkeypatch):
    from pretalx.common.models import mixins as models_mixins  # noqa: PLC0415
    from pretalx.submission.models import (  # noqa: PLC0415
        submission as pretalx_submission,
    )

    called = -1
    submission_codes = [submission.code, submission.code, "abcdef"]

    def yield_random_codes(*args, **kwargs):
        nonlocal called
        called += 1
        return submission_codes[called]

    monkeypatch.setattr(models_mixins, "get_random_string", yield_random_codes)
    new_submission = pretalx_submission.Submission()
    assert not new_submission.code
    new_submission.assign_code()
    assert new_submission.code == "abcdef"
    assert new_submission.code != submission.code


@pytest.mark.parametrize(
    ("data", "loaded"),
    (
        ("", {}),
        (None, {}),
        ("{}", {}),
        ("[]", {}),
        ("[1,2,3]", {}),
        ('{"a": "b"}', {"a": "b"}),
        ("1saser;", {}),
    ),
)
def test_submission_anonymise(data, loaded):
    s = Submission()
    s.anonymised_data = data
    assert s.anonymised == loaded
    assert not s.is_anonymised


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        (SubmissionStates.SUBMITTED, 0),
        (SubmissionStates.ACCEPTED, 1),
        (SubmissionStates.REJECTED, 1),
        (SubmissionStates.CONFIRMED, 0),
        (SubmissionStates.CANCELED, 0),
    ),
)
@pytest.mark.django_db
def test_send_state_mail(submission, state, expected):
    with scope(event=submission.event):
        submission.state = state
        submission.save()
        count = submission.event.queued_mails.all().count()
        submission.send_state_mail()
        assert submission.event.queued_mails.all().count() == count + expected


@pytest.mark.django_db
def test_public_slots_without_schedule(submission):
    with scope(event=submission.event):
        submission.event.schedules.all().delete()
        submission.event.is_public = True
        submission.event.feature_flags["show_schedule"] = True
        submission.event.save()
        assert submission.public_slots == []


@pytest.mark.django_db
def test_public_slots_with_visible_agenda(submission, slot):
    with scope(event=submission.event):
        submission.event.is_public = True
        submission.event.feature_flags["show_schedule"] = True
        submission.event.save()
        assert len(submission.public_slots) == 0


@pytest.mark.django_db
def test_content_for_mail(submission, file_question, boolean_question):
    f = SimpleUploadedFile("testresource.txt", b"a resource")
    with scope(event=submission.event):
        Answer.objects.create(
            question=boolean_question, answer=True, submission=submission
        )
        fa = Answer.objects.create(
            question=file_question, answer_file=f, submission=submission
        )
        host = submission.event.custom_domain or settings.SITE_URL

        assert (
            submission.get_content_for_mail().strip()
            == f"""**Proposal title**: {submission.title}

**Abstract**: {submission.abstract}

**Description**: {submission.description}

**Notes**: {submission.notes}

**Language**: {submission.content_locale}

**{boolean_question.question}**: Yes

**{file_question.question}**: {host}{fa.answer_file.url}""".strip()
        )


@pytest.mark.django_db
def test_send_invite_requires_signature(submission):
    with scope(event=submission.event), pytest.raises(Exception):  # noqa: B017, PT011
        submission.send_invite(None)


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.REJECTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.CANCELED,
    ),
)
@pytest.mark.parametrize(
    "pending_state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.REJECTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.CANCELED,
    ),
)
@pytest.mark.django_db
def test_pending_state(submission, state, pending_state):
    with scope(event=submission.event):
        submission.state = state
        submission.pending_state = pending_state
        submission.save()
        count = submission.logged_actions().count()

        submission.apply_pending_state()

        assert submission.state == pending_state
        assert submission.logged_actions().count() == (
            count + int(state != pending_state)
        )
        if pending_state == "accepted" and state == "submitted":
            assert submission.event.queued_mails.count() == 1
            assert submission.event.wip_schedule.talks.count() == 1


@pytest.mark.django_db
def test_editable_with_access_code_requirement(submission, track):
    with scope(event=submission.event):
        submission.state = SubmissionStates.DRAFT
        submission.save()

        assert submission.editable

        submission.track = track
        submission.track.requires_access_code = True
        submission.track.save()
        submission.save()

        del submission.editable
        assert not submission.editable

        access_code = SubmitterAccessCode.objects.create(
            event=submission.event, code="TEST123"
        )
        access_code.tracks.add(submission.track)
        submission.access_code = access_code
        submission.save()

        del submission.editable
        assert submission.editable

        access_code.valid_until = now() - timedelta(hours=1)
        access_code.save()

        del submission.editable
        assert not submission.editable


@pytest.mark.django_db
def test_editable_with_access_code_for_submission_type(submission):
    with scope(event=submission.event):
        submission.state = SubmissionStates.DRAFT
        submission.save()
        submission.submission_type.requires_access_code = True
        submission.submission_type.save()

        assert not submission.editable

        access_code = SubmitterAccessCode.objects.create(
            event=submission.event,
            code="TYPE123",
        )
        access_code.submission_types.add(submission.submission_type)
        submission.access_code = access_code
        submission.save()

        del submission.editable
        assert submission.editable


@pytest.mark.django_db
def test_deleting_sole_track_deletes_access_code(event, track):
    with scope(event=event):
        access_code = SubmitterAccessCode.objects.create(event=event, code="TRACK1")
        access_code.tracks.add(track)
        ac_pk = access_code.pk

        track.delete()
        assert not SubmitterAccessCode.objects.filter(pk=ac_pk).exists()


@pytest.mark.django_db
def test_deleting_one_of_multiple_tracks_keeps_access_code(event, track):
    with scope(event=event):
        other_track = event.tracks.create(name="Other", color="#00ff00")
        access_code = SubmitterAccessCode.objects.create(event=event, code="TRACK2")
        access_code.tracks.add(track, other_track)

        track.delete()
        access_code.refresh_from_db()
        assert list(access_code.tracks.all()) == [other_track]


@pytest.mark.django_db
def test_deleting_sole_submission_type_deletes_access_code(event, submission_type):
    with scope(event=event):
        access_code = SubmitterAccessCode.objects.create(event=event, code="TYPE1")
        access_code.submission_types.add(submission_type)
        ac_pk = access_code.pk

        submission_type.delete()
        assert not SubmitterAccessCode.objects.filter(pk=ac_pk).exists()


@pytest.mark.django_db
def test_deleting_one_of_multiple_types_keeps_access_code(event, submission_type):
    with scope(event=event):
        other_type = event.submission_types.create(name="Other")
        access_code = SubmitterAccessCode.objects.create(event=event, code="TYPE2")
        access_code.submission_types.add(submission_type, other_type)

        submission_type.delete()
        access_code.refresh_from_db()
        assert list(access_code.submission_types.all()) == [other_type]


@pytest.mark.django_db
def test_before_state_change_signal_fires(submission):
    submission.event.plugins = "tests"
    submission.event.save()
    with scope(event=submission.event):
        submission.state = SubmissionStates.SUBMITTED
        submission.save()

        submission.accept()

        assert submission.state == SubmissionStates.ACCEPTED
        assert submission._before_state_change_called == 1
        assert submission._state_change_called == 1


@pytest.mark.django_db
def test_before_state_change_signal_veto(submission):
    submission.event.plugins = "tests"
    submission.event.save()
    with scope(event=submission.event):
        submission.state = SubmissionStates.SUBMITTED
        submission.save()
        submission._veto_state_change = True

        with pytest.raises(SubmissionError):
            submission.accept()

        assert submission.state == SubmissionStates.SUBMITTED
        assert submission._before_state_change_called == 1
        assert getattr(submission, "_state_change_called", 0) == 0


@pytest.mark.django_db
def test_before_state_change_signal_no_fire_on_noop(submission):
    submission.event.plugins = "tests"
    submission.event.save()
    with scope(event=submission.event):
        submission.state = SubmissionStates.ACCEPTED
        submission.save()

        submission.accept()

        assert submission.state == SubmissionStates.ACCEPTED
        assert getattr(submission, "_before_state_change_called", 0) == 0


@pytest.mark.django_db
def test_before_state_change_signal_no_fire_on_initial_submit(submission):
    submission.event.plugins = "tests"
    submission.event.save()
    with scope(event=submission.event):
        submission.state = SubmissionStates.DRAFT
        submission.save()
        submission._veto_state_change = True

        submission.make_submitted()

        assert submission.state == SubmissionStates.SUBMITTED
        assert getattr(submission, "_before_state_change_called", 0) == 0
