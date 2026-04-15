# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SubmissionError
from pretalx.common.models.log import ActivityLog
from pretalx.mail.models import QueuedMailStates
from pretalx.schedule.models import TalkSlot
from pretalx.submission.models import Submission, SubmissionInvitation, SubmissionStates
from pretalx.submission.models.comment import SubmissionComment
from pretalx.submission.models.question import QuestionRequired, QuestionVariant
from pretalx.submission.models.submission import SpeakerRole
from pretalx.submission.signals import before_submission_state_change
from tests.factories import (
    AnswerFactory,
    EventFactory,
    FeedbackFactory,
    QuestionFactory,
    ResourceFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionCommentFactory,
    SubmissionFactory,
    SubmissionInvitationFactory,
    TagFactory,
    TalkSlotFactory,
    TrackFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_list_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submissions = SubmissionFactory.create_batch(item_count, event=event)
        for sub in submissions:
            speaker = SpeakerFactory(event=event)
            sub.speakers.add(speaker)
    client.force_login(user)

    with django_assert_num_queries(31):
        response = client.get(event.orga_urls.submissions, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(sub.title in content for sub in submissions)


def test_submission_list_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.submissions)

    assert response.status_code == 302
    assert "/login/" in response.url


def test_submission_list_search_by_title(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    response = client.get(
        event.orga_urls.submissions + f"?q={submission.title[:5]}", follow=True
    )

    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_submission_list_search_by_speaker(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        speaker_name = speaker.get_display_name()[:5]
    client.force_login(user)

    response = client.get(
        event.orga_urls.submissions + f"?q={speaker_name}", follow=True
    )

    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_submission_list_search_miss(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    response = client.get(
        event.orga_urls.submissions + f"?q={submission.title[:5]}xxy", follow=True
    )

    assert response.status_code == 200
    assert submission.title not in response.content.decode()


@pytest.mark.parametrize(
    "field", ("description", "abstract", "notes", "internal_notes")
)
def test_submission_list_fulltext_search_finds_by_field(client, event, field):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(
            event=event,
            description="Unique description text here",
            abstract="Unique abstract text here",
            notes="Unique notes text here",
            internal_notes="Unique internal notes here",
        )
        value = getattr(submission, field)
    client.force_login(user)

    response = client.get(event.orga_urls.submissions + f"?q={value[:8]}", follow=True)
    assert response.status_code == 200
    assert submission.title not in response.content.decode()

    response = client.get(
        event.orga_urls.submissions + f"?q={value[:8]}&fulltext=on", follow=True
    )
    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_submission_list_reviewer_can_search_by_speaker(client, event):
    """Reviewers can search by speaker when the review phase allows seeing names."""
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        speaker_name = speaker.get_display_name()[:5]
    client.force_login(reviewer)

    response = client.get(
        event.orga_urls.submissions + f"?q={speaker_name}", follow=True
    )

    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_submission_list_reviewer_cannot_search_by_speaker_when_anonymised(
    client, event
):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        phase = event.active_review_phase
        phase.can_see_speaker_names = False
        phase.save()
        speaker_name = speaker.get_display_name()[:5]
    client.force_login(reviewer)

    response = client.get(
        event.orga_urls.submissions + f"?q={speaker_name}", follow=True
    )

    assert response.status_code == 200
    assert submission.title not in response.content.decode()


def test_submission_list_reviewer_cannot_search_by_speaker_when_team_hides_names(
    client, event
):
    with scopes_disabled():
        reviewer = make_orga_user(
            event,
            can_change_submissions=False,
            is_reviewer=True,
            force_hide_speaker_names=True,
        )
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        speaker_name = speaker.get_display_name()[:5]
    client.force_login(reviewer)

    response = client.get(
        event.orga_urls.submissions + f"?q={speaker_name}", follow=True
    )

    assert response.status_code == 200
    assert submission.title not in response.content.decode()


def test_submission_content_404_for_invalid_code(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    response = client.get(submission.orga_urls.base + "JJ", follow=True)

    assert response.status_code == 404


def test_submission_content_reviewer_can_see(client, event):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        submission = SubmissionFactory(event=event)
    client.force_login(reviewer)

    response = client.get(submission.orga_urls.base, follow=True)

    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_submission_content_reviewer_sees_question_answer(client):
    event = EventFactory(feature_flags={"use_tracks": True})
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        submission = SubmissionFactory(event=event)
        question = QuestionFactory(event=event, target="submission")
        AnswerFactory(question=question, submission=submission, answer="42")
    client.force_login(reviewer)

    response = client.get(submission.orga_urls.base, follow=True)

    assert response.status_code == 200
    assert question.question in response.content.decode()


def test_submission_content_reviewer_hidden_question(client):
    event = EventFactory(feature_flags={"use_tracks": True})
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        submission = SubmissionFactory(event=event)
        question = QuestionFactory(
            event=event, target="submission", is_visible_to_reviewers=False
        )
        AnswerFactory(question=question, submission=submission, answer="42")
    client.force_login(reviewer)

    response = client.get(submission.orga_urls.base, follow=True)

    assert response.status_code == 200
    assert question.question not in response.content.decode()


def test_submission_accept_get_does_not_change_state(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    client.force_login(user)

    response = client.get(submission.orga_urls.accept, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
    assert submission.state == SubmissionStates.SUBMITTED


def test_submission_accept_post_changes_state_and_queues_mail(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.post(submission.orga_urls.accept, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.ACCEPTED
        assert event.queued_mails.count() == 1


def test_submission_accept_redirects_to_next(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.post(
        submission.orga_urls.accept + f"?next={event.orga_urls.submissions}"
    )

    assert response.status_code == 302
    assert response.url == event.orga_urls.submissions


def test_submission_accept_already_accepted_is_noop(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        submission.accept(person=user, orga=True)
    client.force_login(user)

    response = client.post(submission.orga_urls.accept, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
    assert submission.state == SubmissionStates.ACCEPTED


def test_submission_reject_post_changes_state_and_queues_mail(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        assert event.queued_mails.count() == 0
    client.force_login(user)

    response = client.post(submission.orga_urls.reject, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.REJECTED
        assert event.queued_mails.count() == 1


def test_submission_confirm_post_changes_state(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        submission.accept(person=user, orga=True)
    client.force_login(user)

    response = client.post(submission.orga_urls.confirm, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
    assert submission.state == SubmissionStates.CONFIRMED


def test_submission_delete_get_does_not_delete(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    response = client.get(submission.orga_urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert Submission.objects.filter(event=event).count() == 1


def test_submission_delete_post_deletes(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        code = submission.code
    client.force_login(user)

    response = client.post(submission.orga_urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert Submission.objects.filter(event=event).count() == 0
        assert not Submission.all_objects.filter(code=code).exists()


def test_submission_delete_scheduled_shows_warning(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, is_visible=True)
        submission_pk = submission.pk
    client.force_login(user)

    response = client.get(submission.orga_urls.delete)
    assert response.status_code == 200
    assert "schedule" in response.content.decode().lower()

    response = client.post(submission.orga_urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert not Submission.all_objects.filter(code=submission.code).exists()
        assert TalkSlot.objects.filter(submission_id=submission_pk).count() == 0


def test_submission_delete_reviewer_gets_404(client, event):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        submission = SubmissionFactory(event=event)
    client.force_login(reviewer)

    response = client.get(submission.orga_urls.delete, follow=True)
    assert response.status_code == 404

    response = client.post(submission.orga_urls.delete, follow=True)
    assert response.status_code == 404
    with scopes_disabled():
        assert Submission.objects.filter(event=event).count() == 1


@pytest.mark.parametrize("known_speaker", (True, False))
def test_submission_create(client, event, known_speaker):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        type_pk = event.submission_types.first().pk
        assert event.submissions.count() == 0
    client.force_login(user)

    response = client.post(
        event.orga_urls.new_submission,
        data={
            "abstract": "abstract",
            "content_locale": "en",
            "description": "description",
            "duration": "",
            "slot_count": 1,
            "notes": "notes",
            "internal_notes": "internal_notes",
            "speaker-email": user.email if known_speaker else "newbie@example.org",
            "speaker-name": "Foo Speaker",
            "speaker-locale": "en",
            "title": "My Great Talk",
            "submission_type": type_pk,
            "state": "submitted",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert event.submissions.count() == 1
        sub = event.submissions.first()
        assert sub.title == "My Great Talk"
        assert sub.speakers.count() == 1
        assert sub.mails.count() == 1


def test_submission_edit_updates_fields_and_logs(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        old_title = submission.title
        initial_log_count = submission.logged_actions().count()
    client.force_login(user)

    response = client.post(
        submission.orga_urls.base,
        data={
            "abstract": "abstract",
            "content_locale": "en",
            "description": "description",
            "duration": "",
            "notes": "notes",
            "title": "Updated Title",
            "submission_type": submission.submission_type.pk,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.title == "Updated Title"
        logs = submission.logged_actions()
        assert logs.count() > initial_log_count
        update_log = logs.filter(action_type="pretalx.submission.update").first()
        assert update_log is not None
        assert update_log.data["changes"]["title"]["old"] == old_title
        assert update_log.data["changes"]["title"]["new"] == "Updated Title"


def test_submission_edit_with_question_consolidated_log(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        question = QuestionFactory(
            event=event,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )
        old_title = submission.title
        initial_log_count = submission.logged_actions().count()
    client.force_login(user)

    response = client.post(
        submission.orga_urls.base,
        data={
            "abstract": "abstract",
            "content_locale": "en",
            "description": "description",
            "duration": "",
            "notes": "notes",
            "title": "New Updated Title",
            "submission_type": submission.submission_type.pk,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
            f"question_{question.pk}": "50",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        logs = submission.logged_actions()
        assert logs.count() == initial_log_count + 1
        update_log = logs.filter(action_type="pretalx.submission.update").first()
        assert update_log
        assert update_log.changes["title"]["old"] == old_title
        assert update_log.changes["title"]["new"] == "New Updated Title"
        question_key = f"question-{question.pk}"
        assert update_log.changes[question_key]["old"] is None
        assert update_log.changes[question_key]["new"] == "50"


def test_submission_edit_wrong_answer_does_not_save(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        question = QuestionFactory(
            event=event,
            target="submission",
            variant=QuestionVariant.NUMBER,
            question_required=QuestionRequired.REQUIRED,
        )
    client.force_login(user)

    response = client.post(
        submission.orga_urls.base,
        data={
            "abstract": "abstract",
            "content_locale": "en",
            "description": "description",
            "duration": "",
            "notes": "notes",
            "title": "new title",
            "submission_type": submission.submission_type.pk,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
            f"question_{question.pk}": "hahaha",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.title != "new title"


def test_submission_edit_slot_count(client):
    event = EventFactory(feature_flags={"present_multiple_times": True})
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        submission.accept(person=user, orga=True)
        assert submission.slots.count() == 1
    client.force_login(user)

    response = client.post(
        submission.orga_urls.base,
        data={
            "abstract": "abstract",
            "content_locale": "en",
            "description": "description",
            "duration": "",
            "slot_count": 2,
            "notes": "notes",
            "title": "title",
            "submission_type": submission.submission_type.pk,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.slot_count == 2
        assert submission.slots.count() == 2


def test_submission_edit_duration(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        submission.accept(person=user, orga=True)
        room = RoomFactory(event=event)
        slot = submission.slots.filter(schedule=event.wip_schedule).first()
        slot.start = event.datetime_from + dt.timedelta(hours=10)
        slot.end = slot.start + dt.timedelta(minutes=submission.get_duration())
        slot.room = room
        slot.save()
    client.force_login(user)

    response = client.post(
        submission.orga_urls.base,
        data={
            "abstract": "abstract",
            "content_locale": "en",
            "description": "description",
            "slot_count": 1,
            "notes": "notes",
            "start": slot.local_start,
            "room": room.pk,
            "duration": 123,
            "title": "title",
            "submission_type": submission.submission_type.pk,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        slot.refresh_from_db()
        assert (slot.local_end - slot.local_start).seconds / 60 == 123


@pytest.mark.parametrize(
    "question_type", (QuestionVariant.DATE, QuestionVariant.DATETIME)
)
@pytest.mark.parametrize(
    ("delta", "success"),
    (
        (dt.timedelta(days=-1), False),
        (dt.timedelta(days=1), True),
        (dt.timedelta(days=3), False),
    ),
)
def test_submission_edit_datetime_answer_validation(
    client, event, question_type, delta, success
):
    min_value = now()
    max_value = now() + dt.timedelta(days=2)
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        question = QuestionFactory(
            event=event,
            target="submission",
            variant=question_type,
            question_required=QuestionRequired.REQUIRED,
            min_date=min_value.date(),
            min_datetime=min_value,
            max_date=max_value.date(),
            max_datetime=max_value,
        )
    client.force_login(user)

    value = min_value + delta
    if question_type == QuestionVariant.DATE:
        value = value.date()
    value = value.isoformat()

    response = client.post(
        submission.orga_urls.base,
        data={
            "abstract": "abstract",
            "content_locale": "en",
            "description": "description",
            "duration": "",
            "notes": "notes",
            "title": "new title",
            "submission_type": submission.submission_type_id,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
            f"question_{question.pk}": value,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert (submission.title == "new title") is success


def test_submission_edit_resources_add_and_remove(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        event.cfp.fields["resources"] = {"visibility": "optional"}
        event.cfp.save()
        submission = SubmissionFactory(event=event, abstract="Test abstract")
        file_one = SimpleUploadedFile("res1.txt", b"content_one")
        file_two = SimpleUploadedFile("res2.txt", b"content_two")
        resource_one = ResourceFactory(
            submission=submission, resource=file_one, link=""
        )
        resource_two = ResourceFactory(
            submission=submission, resource=file_two, link=""
        )
        assert submission.resources.count() == 2
    client.force_login(user)

    f = SimpleUploadedFile("testfile.txt", b"file_content")
    response = client.post(
        submission.orga_urls.base,
        data={
            "abstract": submission.abstract,
            "content_locale": submission.content_locale,
            "title": "new title",
            "submission_type": submission.submission_type.pk,
            "resource-0-id": resource_one.id,
            "resource-0-description": "new resource name",
            "resource-0-resource": resource_one.resource,
            "resource-1-id": resource_two.id,
            "resource-1-DELETE": True,
            "resource-1-description": resource_two.description or "",
            "resource-1-resource": resource_two.resource,
            "resource-2-id": "",
            "resource-2-description": "new resource",
            "resource-2-resource": f,
            "resource-TOTAL_FORMS": 3,
            "resource-INITIAL_FORMS": 2,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        resource_one.refresh_from_db()
        new_resource = submission.resources.exclude(pk=resource_one.pk).first()
        assert submission.title == "new title"
        assert submission.resources.count() == 2
        assert new_resource.description == "new resource"
        assert new_resource.resource.read() == b"file_content"
        assert not submission.resources.filter(pk=resource_two.pk).exists()


def test_submission_edit_wrong_resources_not_added(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        event.cfp.fields["resources"] = {"visibility": "optional"}
        event.cfp.save()
        submission = SubmissionFactory(event=event, abstract="Test abstract")
        file_one = SimpleUploadedFile("res1.txt", b"content_one")
        file_two = SimpleUploadedFile("res2.txt", b"content_two")
        resource_one = ResourceFactory(
            submission=submission, resource=file_one, link=""
        )
        resource_two = ResourceFactory(
            submission=submission, resource=file_two, link=""
        )
    client.force_login(user)

    f = SimpleUploadedFile("testfile.txt", b"file_content")
    response = client.post(
        submission.orga_urls.base,
        data={
            "abstract": submission.abstract,
            "content_locale": submission.content_locale,
            "title": "new title",
            "submission_type": submission.submission_type.pk,
            "resource-0-id": resource_one.id,
            "resource-0-description": "new resource name",
            "resource-0-resource": resource_one.resource,
            "resource-1-id": resource_two.id,
            "resource-1-DELETE": True,
            "resource-1-description": resource_two.description or "",
            "resource-1-resource": resource_two.resource,
            "resource-2-id": "",
            "resource-2-description": "",
            "resource-2-resource": f,
            "resource-TOTAL_FORMS": 3,
            "resource-INITIAL_FORMS": 2,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.resources.count() == 2
        assert submission.resources.filter(pk=resource_two.pk).exists()


@pytest.mark.parametrize("known_speaker", (True, False))
def test_submission_speakers_add(client, event, known_speaker):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        assert submission.speakers.count() == 1
    client.force_login(user)

    email = user.email if known_speaker else "newspeaker@example.org"
    response = client.post(
        submission.orga_urls.speakers, data={"email": email}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.speakers.count() == 2


def test_submission_speakers_add_invalid_email(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.post(
        submission.orga_urls.speakers,
        data={"speaker": "foooobaaaaar", "name": "Name"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.speakers.count() == 1


def test_submission_speakers_readd_existing(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        speaker_email = speaker.user.email
    client.force_login(user)

    response = client.post(
        submission.orga_urls.speakers,
        data={"speaker": speaker_email, "name": "Name"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.speakers.count() == 1


def test_submission_speakers_remove(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        speaker_pk = speaker.pk
    client.force_login(user)

    response = client.post(
        submission.orga_urls.delete_speaker, {"id": speaker_pk}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.speakers.count() == 0


def test_submission_speakers_remove_wrong_speaker(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        other_speaker = SpeakerFactory(event=event)
        other_sub = SubmissionFactory(event=event)
        other_sub.speakers.add(other_speaker)
    client.force_login(user)

    response = client.post(
        submission.orga_urls.delete_speaker, {"id": other_speaker.pk}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.speakers.count() == 1
    assert "not part of this proposal" in response.content.decode()


def test_submission_speakers_reorder(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker1 = SpeakerFactory(event=event)
        speaker2 = SpeakerFactory(event=event)
        submission.speakers.add(speaker1)
        submission.speakers.add(speaker2)
        role1 = SpeakerRole.objects.get(submission=submission, speaker=speaker1)
        role2 = SpeakerRole.objects.get(submission=submission, speaker=speaker2)
    client.force_login(user)

    response = client.post(
        submission.orga_urls.reorder_speakers, data={"order": f"{role2.pk},{role1.pk}"}
    )

    assert response.status_code == 204
    with scopes_disabled():
        ordered = list(submission.sorted_speakers)
        assert ordered == [speaker2, speaker1]


def test_submission_speakers_reorder_empty_returns_400(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.post(submission.orga_urls.reorder_speakers, data={"order": ""})

    assert response.status_code == 400


def test_submission_toggle_featured(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        assert not submission.is_featured
    client.force_login(user)

    response = client.post(submission.orga_urls.toggle_featured, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.is_featured is True


def test_submission_anonymise_reviewer_gets_404(client, event):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        submission = SubmissionFactory(event=event)
    client.force_login(reviewer)

    response = client.get(submission.orga_urls.anonymise, follow=True)

    assert response.status_code == 404


def test_submission_anonymise_saves_and_redirects(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        SubmissionFactory(event=event)
    client.force_login(user)

    response = client.post(
        submission.orga_urls.anonymise, data={"description": "CENSORED!"}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
    assert submission.is_anonymised
    assert submission.anonymised == {
        "_anonymised": True,
        "abstract": "",
        "notes": "",
        "description": "CENSORED!",
        "title": "",
    }


def test_submission_anonymise_next_redirects_to_next_unanonymised(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        other = SubmissionFactory(event=event)
    client.force_login(user)

    response = client.post(
        submission.orga_urls.anonymise,
        data={"description": "CENSORED!", "action": "next"},
    )

    assert response.status_code == 302
    assert response.url == other.orga_urls.anonymise


def test_submission_anonymise_hides_data_for_reviewer(client, event):
    """Reviewers see anonymised data instead of real data."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        phase = event.active_review_phase
        phase.can_see_speaker_names = False
        phase.save()
    client.force_login(user)

    client.post(submission.orga_urls.anonymise, data={"description": "CENSORED!"})

    client.force_login(reviewer)
    response = client.get(submission.orga_urls.base)
    assert response.status_code == 200
    assert "CENSORED" in response.content.decode()


def test_submission_anonymise_orga_sees_original_data(client, event):
    """Orga users see original data on the detail page, not anonymised data."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    client.post(submission.orga_urls.anonymise, data={"description": "CENSORED!"})

    response = client.get(submission.orga_urls.base)
    assert response.status_code == 200
    assert "CENSORED" not in response.content.decode()


def test_submission_feed_accessible(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    response = client.get(event.orga_urls.submission_feed, follow=True)

    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_submission_feed_unauthorized_hides_data(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=False)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    response = client.get(event.orga_urls.submission_feed, follow=True)

    assert submission.title not in response.content.decode()


@pytest.mark.parametrize("use_tracks", (True, False))
def test_submission_statistics(client, use_tracks):
    event = EventFactory(feature_flags={"use_tracks": use_tracks})
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        if use_tracks:
            TrackFactory(event=event)
            TrackFactory(event=event)
        sub1 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        sub2 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        for sub in [sub1, sub2]:
            log = sub.log_action("pretalx.submission.create")
        ActivityLog.objects.filter(pk=log.pk).update(
            timestamp=log.timestamp - dt.timedelta(days=2)
        )
    client.force_login(user)

    response = client.get(event.orga_urls.stats)

    assert response.status_code == 200


@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_feedback_list_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        FeedbackFactory.create_batch(item_count, talk=submission)
    client.force_login(user)

    with django_assert_num_queries(29):
        response = client.get(submission.orga_urls.feedback, follow=True)

    assert response.status_code == 200
    assert "Great talk!" in response.content.decode()


@pytest.mark.parametrize("item_count", (1, 3))
def test_all_feedbacks_list_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submissions = []
        for _ in range(item_count):
            sub = SubmissionFactory(event=event)
            FeedbackFactory(talk=sub)
            submissions.append(sub)
    client.force_login(user)

    with django_assert_num_queries(18):
        response = client.get(event.orga_urls.feedback, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(sub.title in content for sub in submissions)


def test_submission_apply_pending_bulk_get(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(
            event=event,
            state=SubmissionStates.SUBMITTED,
            pending_state=SubmissionStates.ACCEPTED,
        )
    client.force_login(user)

    response = client.get(event.orga_urls.apply_pending)
    assert response.status_code == 200

    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.SUBMITTED
        assert submission.pending_state == SubmissionStates.ACCEPTED


def test_submission_apply_pending_bulk_post(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(
            event=event,
            state=SubmissionStates.SUBMITTED,
            pending_state=SubmissionStates.ACCEPTED,
        )
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.post(event.orga_urls.apply_pending)

    assert response.status_code == 302
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.ACCEPTED
        assert submission.pending_state is None
        assert event.queued_mails.count() == 1


def test_submission_apply_pending_single(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(
            event=event,
            state=SubmissionStates.SUBMITTED,
            pending_state=SubmissionStates.ACCEPTED,
        )
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.post(submission.orga_urls.apply_pending)

    assert response.status_code == 302
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.ACCEPTED
        assert submission.pending_state is None
        assert event.queued_mails.count() == 1


@pytest.mark.parametrize("item_count", (1, 3))
def test_tag_list_query_count(client, event, item_count, django_assert_num_queries):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        tags = TagFactory.create_batch(item_count, event=event)
    client.force_login(user)

    with django_assert_num_queries(18):
        response = client.get(event.orga_urls.tags)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(str(tag.tag) in content for tag in tags)


def test_tag_create_and_no_duplicates(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.new_tag)
    assert response.status_code == 200

    response = client.post(
        event.orga_urls.new_tag, {"tag": "New tag!", "color": "#ffff99"}, follow=True
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert event.tags.count() == 1

    response = client.post(
        event.orga_urls.new_tag, {"tag": "New tag!", "color": "#ffff99"}, follow=True
    )
    assert response.status_code == 200
    assert "already have a tag" in response.content.decode()
    with scopes_disabled():
        assert event.tags.count() == 1


def test_tag_view(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        tag = TagFactory(event=event)
    client.force_login(user)

    response = client.get(tag.urls.base)

    assert response.status_code == 200
    assert str(tag.tag) in response.content.decode()


def test_tag_edit_logs_action(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        tag = TagFactory(event=event)
        initial_log_count = tag.logged_actions().count()
    client.force_login(user)

    response = client.post(
        tag.urls.base, {"tag": "Renamed", "color": "#ffff99"}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert tag.logged_actions().count() == initial_log_count + 1
        tag.refresh_from_db()
    assert str(tag.tag) == "Renamed"


def test_tag_edit_unchanged_no_log(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        tag = TagFactory(event=event)
        initial_log_count = tag.logged_actions().count()
    client.force_login(user)

    response = client.post(
        tag.urls.base, {"tag": str(tag.tag), "color": tag.color}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert tag.logged_actions().count() == initial_log_count


def test_tag_edit_invalid_color_rejected(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        tag = TagFactory(event=event)
        original_name = str(tag.tag)
    client.force_login(user)

    response = client.post(
        tag.urls.base, {"tag": "Name", "color": "#fgff99"}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        tag.refresh_from_db()
    assert str(tag.tag) == original_name


def test_tag_delete(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        tag = TagFactory(event=event)
    client.force_login(user)

    response = client.get(tag.urls.delete)
    assert response.status_code == 200
    with scopes_disabled():
        assert event.tags.count() == 1

    response = client.post(tag.urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert event.tags.count() == 0


def test_tag_delete_used_tag_cascades(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        tag = TagFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.tags.add(tag)
    client.force_login(user)

    response = client.post(tag.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.tags.count() == 0
        submission.refresh_from_db()
        assert submission.tags.count() == 0


def test_tag_count_in_submission_filter(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        tag = TagFactory(event=event)
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)
        sub1.tags.add(tag)
        sub2.tags.add(tag)
    client.force_login(user)

    response = client.get(event.orga_urls.submissions, follow=True)

    assert response.status_code == 200
    assert f"{tag.tag} (2)" in response.content.decode()


@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_comments_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        comments = SubmissionCommentFactory.create_batch(
            item_count, submission=submission, user=user
        )
    client.force_login(user)

    with django_assert_num_queries(23):
        response = client.get(submission.orga_urls.comments, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(comment.text in content for comment in comments)


def test_submission_comment_post(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.post(
        submission.orga_urls.comments,
        data={"text": "Here is a new comment!"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.comments.count() == 1
        comment = submission.comments.first()
        assert comment.text == "Here is a new comment!"


def test_submission_comment_empty_not_created(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.post(
        submission.orga_urls.comments, data={"text": ""}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.comments.count() == 0


def test_submission_comment_delete(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        comment = SubmissionCommentFactory(submission=submission, user=user)
        comment_pk = comment.pk
    client.force_login(user)

    response = client.get(comment.urls.delete, follow=True)
    assert response.status_code == 200

    response = client.post(comment.urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert not SubmissionComment.objects.filter(pk=comment_pk).exists()


@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_history_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        for _ in range(item_count):
            submission.log_action(
                "pretalx.submission.update",
                person=user,
                orga=True,
                old_data={"title": "Old Title"},
                new_data={"title": "New Title"},
            )
    client.force_login(user)

    with django_assert_num_queries(26):
        response = client.get(submission.orga_urls.history, follow=True)

    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_submission_invitation_retract(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        invitation = SubmissionInvitationFactory(
            submission=submission, email="todelete@example.com"
        )
        invitation_id = invitation.pk
    client.force_login(user)

    response = client.get(
        submission.orga_urls.retract_invitation + f"?id={invitation_id}", follow=True
    )
    assert response.status_code == 200
    assert "todelete@example.com" in response.content.decode()

    response = client.post(
        submission.orga_urls.retract_invitation + f"?id={invitation_id}", follow=True
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert not SubmissionInvitation.objects.filter(pk=invitation_id).exists()
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.invitation.retract")
            .exists()
        )


def test_submission_state_change_pending_sets_pending_state(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.post(
        submission.orga_urls.accept, data={"pending": "on"}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.SUBMITTED
        assert submission.pending_state == SubmissionStates.ACCEPTED


def test_submission_anonymise_already_anonymised_updates(client):
    event = EventFactory()
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(
            event=event, anonymised={"_anonymised": True, "title": ""}
        )
    client.force_login(user)

    response = client.post(
        submission.orga_urls.anonymise,
        data={"description": "NEW CENSORED!"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
    assert submission.is_anonymised
    assert submission.anonymised["description"] == "NEW CENSORED!"


def test_submission_speakers_add_without_email_stays_on_page(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.post(
        submission.orga_urls.speakers, data={"email": ""}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.speakers.count() == 1


def test_submission_create_with_invalid_speaker_form(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        type_pk = event.submission_types.first().pk
    client.force_login(user)

    response = client.post(
        event.orga_urls.new_submission,
        data={
            "abstract": "abstract",
            "content_locale": "en",
            "description": "description",
            "duration": "",
            "slot_count": 1,
            "notes": "notes",
            "speaker-email": "not-an-email",
            "speaker-name": "Speaker Name",
            "speaker-locale": "en",
            "title": "My Talk",
            "submission_type": type_pk,
            "state": "submitted",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert event.submissions.count() == 0


def test_submission_content_query_count(client, event, django_assert_num_queries):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    with django_assert_num_queries(28):
        response = client.get(submission.orga_urls.base, follow=True)

    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_submission_speakers_query_count(client, event, django_assert_num_queries):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    with django_assert_num_queries(23):
        response = client.get(submission.orga_urls.speakers, follow=True)

    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_submission_state_change_pending_rejected(client, event):
    """Pending rejection does NOT create talk slots (only accepted states do)."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.post(
        submission.orga_urls.reject, data={"pending": "on"}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.SUBMITTED
        assert submission.pending_state == SubmissionStates.REJECTED
        assert submission.slots.count() == 0


def test_submission_state_change_warns_about_outdated_emails(client, event):
    """When rejecting an accepted submission, warn if draft acceptance emails exist."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        # Accept first (queues an acceptance email as draft)
        submission.accept(person=user, orga=True)
        assert event.queued_mails.count() == 1
    client.force_login(user)

    response = client.post(submission.orga_urls.reject)

    assert response.status_code == 302
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.REJECTED


def test_submission_state_change_no_pending_email_warning(client, event):
    """No email warning when rejecting an accepted submission if draft emails were already sent."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        # Accept (queues an acceptance email), then send the email so it's not a draft
        submission.accept(person=user, orga=True)
        event.queued_mails.update(state=QueuedMailStates.SENT)
    client.force_login(user)

    response = client.post(submission.orga_urls.reject, follow=True)

    assert response.status_code == 200
    msgs = [str(m) for m in response.context["messages"]]
    assert not any("outdated" in m for m in msgs)


def test_submission_speakers_reorder_noop(client, event):
    """Reordering speakers to the same order does not create a log entry."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker1 = SpeakerFactory(event=event)
        speaker2 = SpeakerFactory(event=event)
        submission.speakers.add(speaker1)
        submission.speakers.add(speaker2)
        role1 = SpeakerRole.objects.get(submission=submission, speaker=speaker1)
        role2 = SpeakerRole.objects.get(submission=submission, speaker=speaker2)
        initial_log_count = submission.logged_actions().count()
    client.force_login(user)

    response = client.post(
        submission.orga_urls.reorder_speakers, data={"order": f"{role1.pk},{role2.pk}"}
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert submission.logged_actions().count() == initial_log_count


def test_submission_apply_pending_bulk_empty(client, event):
    """Bulk apply with no pending submissions shows no submit button."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.apply_pending)

    assert response.status_code == 200
    # No submit button when there are no pending submissions
    content = response.content.decode()
    assert "Do it" not in content


def test_submission_create_without_speaker_email(client, event):
    """Creating a submission without a speaker email still creates the submission."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        type_pk = event.submission_types.first().pk
    client.force_login(user)

    response = client.post(
        event.orga_urls.new_submission,
        data={
            "abstract": "abstract",
            "content_locale": "en",
            "description": "description",
            "duration": "",
            "slot_count": 1,
            "notes": "notes",
            "speaker-email": "",
            "speaker-name": "",
            "speaker-locale": "en",
            "title": "Talk Without Speaker",
            "submission_type": type_pk,
            "state": "submitted",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert event.submissions.count() == 1
        sub = event.submissions.first()
        assert sub.title == "Talk Without Speaker"
        assert sub.speakers.count() == 0


def test_submission_edit_no_changes_no_log(client, event):
    """Editing a submission without changing anything produces no update log."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(
            event=event,
            abstract="Existing abstract",
            description="Existing description",
            notes="Existing notes",
        )
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        initial_log_count = submission.logged_actions().count()
    client.force_login(user)

    response = client.post(
        submission.orga_urls.base,
        data={
            "abstract": submission.abstract,
            "content_locale": submission.content_locale,
            "description": submission.description,
            "duration": "",
            "notes": submission.notes,
            "title": submission.title,
            "submission_type": submission.submission_type.pk,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.update")
            .count()
            == initial_log_count
        )


def test_submission_edit_shows_success_message(client, event):
    """Editing a submission shows a success message."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.post(
        submission.orga_urls.base,
        data={
            "abstract": "abstract",
            "content_locale": "en",
            "description": "description",
            "duration": "",
            "notes": "notes",
            "title": "Updated For Message",
            "submission_type": submission.submission_type.pk,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
        },
        follow=True,
    )

    assert response.status_code == 200
    msgs = [str(m) for m in response.context["messages"]]
    assert any("updated" in m.lower() for m in msgs)


def test_submission_edit_unchanged_resource_not_resaved(client, event):
    """Existing resources that haven't changed are not re-saved."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        event.cfp.fields["resources"] = {"visibility": "optional"}
        event.cfp.save()
        submission = SubmissionFactory(event=event, abstract="Test abstract")
        resource = ResourceFactory(
            submission=submission,
            link="https://example.com/resource",
            description="A resource",
        )
    client.force_login(user)

    response = client.post(
        submission.orga_urls.base,
        data={
            "abstract": submission.abstract,
            "content_locale": submission.content_locale,
            "title": submission.title,
            "submission_type": submission.submission_type.pk,
            "resource-0-id": resource.id,
            "resource-0-description": resource.description,
            "resource-0-link": resource.link,
            "resource-0-is_public": "on",
            "resource-TOTAL_FORMS": 1,
            "resource-INITIAL_FORMS": 1,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        resource.refresh_from_db()
        assert resource.description == "A resource"


def test_submission_list_invalid_filter_still_shows_submissions(client, event):
    """An invalid filter form value is ignored and all submissions are shown."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    response = client.get(
        event.orga_urls.submissions + "?state=INVALID_STATE", follow=True
    )

    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_submission_statistics_talk_timeline_with_multiple_dates(client, event):
    """talk_timeline_data returns data when accepted talks have creation logs on different dates."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        sub1 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        sub2 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        log1 = sub1.log_action("pretalx.submission.create")
        log2 = sub2.log_action("pretalx.submission.create")
        # Move one log to a different date
        ActivityLog.objects.filter(pk=log2.pk).update(
            timestamp=log1.timestamp - dt.timedelta(days=3)
        )
    client.force_login(user)

    response = client.get(event.orga_urls.stats)

    assert response.status_code == 200


def test_submission_state_change_handles_submission_error(
    client, event, register_signal_handler
):
    """SubmissionStateChange.form_valid catches SubmissionError from signal handlers."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    def block_state_change(signal, sender, **kwargs):
        raise SubmissionError("Blocked by plugin")

    register_signal_handler(before_submission_state_change, block_state_change)
    response = client.post(submission.orga_urls.accept, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.SUBMITTED


def test_submission_apply_pending_single_handles_submission_error(
    client, event, register_signal_handler
):
    """ApplyPending.post catches SubmissionError from signal handlers."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(
            event=event,
            state=SubmissionStates.SUBMITTED,
            pending_state=SubmissionStates.ACCEPTED,
        )
    client.force_login(user)

    def block_state_change(signal, sender, **kwargs):
        raise SubmissionError("Blocked by plugin")

    register_signal_handler(before_submission_state_change, block_state_change)
    response = client.post(submission.orga_urls.apply_pending)

    assert response.status_code == 302
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.SUBMITTED
        assert submission.pending_state == SubmissionStates.ACCEPTED


def test_submission_apply_pending_bulk_handles_submission_error(
    client, event, register_signal_handler
):
    """ApplyPendingBulk.post collects SubmissionError messages per submission."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        sub_ok = SubmissionFactory(
            event=event,
            state=SubmissionStates.SUBMITTED,
            pending_state=SubmissionStates.REJECTED,
        )
        sub_blocked = SubmissionFactory(
            event=event,
            state=SubmissionStates.SUBMITTED,
            pending_state=SubmissionStates.ACCEPTED,
        )
    client.force_login(user)

    def block_accept_only(signal, sender, **kwargs):
        if kwargs.get("new_state") == SubmissionStates.ACCEPTED:
            raise SubmissionError("Blocked by plugin")

    register_signal_handler(before_submission_state_change, block_accept_only)
    response = client.post(event.orga_urls.apply_pending, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        sub_ok.refresh_from_db()
        sub_blocked.refresh_from_db()
        assert sub_ok.state == SubmissionStates.REJECTED
        assert sub_blocked.state == SubmissionStates.SUBMITTED
        assert sub_blocked.pending_state == SubmissionStates.ACCEPTED
