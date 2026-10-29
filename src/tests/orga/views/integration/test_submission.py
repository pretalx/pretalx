# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from urllib.parse import urlencode

import pytest
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SendMailException, SubmissionError
from pretalx.common.models.log import ActivityLog
from pretalx.mail.enums import QueuedMailStates
from pretalx.person.enums import SpeakerProfileOrigin
from pretalx.person.models import SpeakerProfile
from pretalx.schedule.models import TalkSlot
from pretalx.submission.models import Submission, SubmissionInvitation, SubmissionStates
from pretalx.submission.models.comment import SubmissionComment
from pretalx.submission.models.question import QuestionRequired, QuestionVariant
from pretalx.submission.models.submission import SpeakerRole
from pretalx.submission.signals import before_submission_state_change
from tests.factories import (
    AnswerFactory,
    AttendeeSignupFactory,
    EventFactory,
    FeedbackFactory,
    QuestionFactory,
    QueuedMailFactory,
    ResourceFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionCommentFactory,
    SubmissionFactory,
    SubmissionInvitationFactory,
    SubmissionTypeFactory,
    TagFactory,
    TalkSlotFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import DIALOG_HEADERS, make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _states(submission):
    with scopes_disabled():
        submission = Submission.objects.get(pk=submission.pk)
    return submission.state, submission.pending_state


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

    with django_assert_num_queries(27):
        response = client.get(event.orga_urls.submissions, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(sub.title in content for sub in submissions)


@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_list_requires_signup_column_query_count(
    client, event, item_count, django_assert_num_queries
):
    event.feature_flags["attendee_signup"] = True
    event.save()
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        prefs = user.get_event_preferences(event)
        prefs.set(
            "tables.SubmissionTable.columns",
            ["title", "speakers", "submission_type", "state", "requires_signup"],
            commit=True,
        )
        submissions = SubmissionFactory.create_batch(item_count, event=event)
        for sub in submissions:
            speaker = SpeakerFactory(event=event)
            sub.speakers.add(speaker)
    client.force_login(user)

    with django_assert_num_queries(24):
        response = client.get(event.orga_urls.submissions, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(sub.title in content for sub in submissions)
    assert "Requires signup" in content


def test_submission_list_htmx_partial_renders_request_aware_columns(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    response = client.get(
        event.orga_urls.submissions,
        headers={"HX-Request": "true", "HX-Target": "table-content-SubmissionTable"},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert submission.title in content
    next_query = urlencode({"next": event.orga_urls.submissions})
    assert f'href="{submission.orga_urls.accept}?{next_query}"' in content


def test_submission_list_requires_signup_column_orders(client, event):
    event.feature_flags["attendee_signup"] = True
    event.save()
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        prefs = user.get_event_preferences(event)
        prefs.set(
            "tables.SubmissionTable.columns",
            ["title", "state", "requires_signup"],
            commit=True,
        )
        required = SubmissionFactory(event=event, attendee_signup_required=True)
        not_required = SubmissionFactory(event=event, attendee_signup_required=False)
    client.force_login(user)

    response = client.get(
        event.orga_urls.submissions + "?sort=requires_signup", follow=True
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert content.index(not_required.title) < content.index(required.title)


@pytest.mark.parametrize(
    ("column", "factory"),
    (("submission_type", SubmissionTypeFactory), ("track", TrackFactory)),
)
def test_submission_list_sorts_by_translated_name(client, event, column, factory):
    event.feature_flags["use_tracks"] = True
    event.save()
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        first = factory(event=event, name={"en": "Alpha", "de": "Zulu"})
        second = factory(event=event, name={"en": "beta", "de": "Yankee"})
        third = factory(event=event, name="Gamma")
        submissions = {
            obj: SubmissionFactory(event=event, **{column: obj})
            for obj in (third, first, second)
        }
    client.force_login(user)

    response = client.get(event.orga_urls.submissions + f"?sort={column}", follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    positions = [
        content.index(submissions[obj].title) for obj in (first, second, third)
    ]
    assert positions == sorted(positions)


@pytest.mark.parametrize("url_attr", ("submissions", "new_submission"))
def test_submission_views_anonymous_redirect_to_login(client, event, url_attr):
    response = client.get(getattr(event.orga_urls, url_attr))

    assert response.status_code == 302
    assert "/login/" in response.url


def test_submission_list_search(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        speaker_name = speaker.get_display_name()[:5]
    client.force_login(user)

    response = client.get(
        event.orga_urls.submissions + f"?q={submission.title[:5]}", follow=True
    )
    assert response.status_code == 200
    assert submission.title in response.content.decode()

    response = client.get(
        event.orga_urls.submissions + f"?q={speaker_name}", follow=True
    )
    assert response.status_code == 200
    assert submission.title in response.content.decode()

    response = client.get(
        event.orga_urls.submissions + f"?q={submission.title[:5]}xxy", follow=True
    )
    assert response.status_code == 200
    assert submission.title not in response.content.decode()

    response = client.get(
        event.orga_urls.submissions + "?state=INVALID_STATE", follow=True
    )
    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_submission_list_fulltext_search_finds_by_field(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(
            event=event,
            description="Unique description text here",
            abstract="Unique abstract text here",
            notes="Unique notes text here",
            internal_notes="Unique internal notes here",
        )
    client.force_login(user)

    for field in ("description", "abstract", "notes", "internal_notes"):
        value = getattr(submission, field)[:8]

        response = client.get(event.orga_urls.submissions + f"?q={value}", follow=True)
        assert response.status_code == 200
        assert submission.title not in response.content.decode()

        response = client.get(
            event.orga_urls.submissions + f"?q={value}&fulltext=on", follow=True
        )
        assert response.status_code == 200
        assert submission.title in response.content.decode()


def test_submission_list_reviewer_search_by_speaker_follows_phase_visibility(
    client, event
):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        speaker_name = speaker.get_display_name()[:5]
    client.force_login(reviewer)
    url = event.orga_urls.submissions + f"?q={speaker_name}"

    response = client.get(url, follow=True)
    assert response.status_code == 200
    assert submission.title in response.content.decode()

    with scopes_disabled():
        phase = event.active_review_phase
        phase.can_see_speaker_names = False
        phase.save()

    response = client.get(url, follow=True)
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


def test_submission_content_reviewer_sees_only_visible_questions(client, event):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        submission = SubmissionFactory(event=event)
        question = QuestionFactory(event=event, target="submission")
        hidden_question = QuestionFactory(
            event=event, target="submission", is_visible_to_reviewers=False
        )
        AnswerFactory(question=question, submission=submission, answer="42")
        AnswerFactory(question=hidden_question, submission=submission, answer="43")
    client.force_login(reviewer)

    response = client.get(submission.orga_urls.base, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert submission.title in content
    assert question.question in content
    assert hidden_question.question not in content


def test_submission_accept_and_confirm(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.get(submission.orga_urls.accept, follow=True)
    assert response.status_code == 200
    assert _states(submission) == (SubmissionStates.SUBMITTED, None)

    response = client.post(
        submission.orga_urls.accept + f"?next={event.orga_urls.submissions}"
    )
    assert response.status_code == 302
    assert response.url == event.orga_urls.submissions
    assert _states(submission) == (SubmissionStates.ACCEPTED, None)
    with scopes_disabled():
        assert event.queued_mails.count() == 1

    response = client.post(submission.orga_urls.accept, follow=True)
    assert response.status_code == 200
    assert _states(submission) == (SubmissionStates.ACCEPTED, None)
    with scopes_disabled():
        assert event.queued_mails.count() == 1

    response = client.post(submission.orga_urls.confirm, follow=True)
    assert response.status_code == 200
    assert _states(submission) == (SubmissionStates.CONFIRMED, None)


def test_submission_accept_no_mail_for_managed_speaker(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        managed = SpeakerFactory(
            event=event, user=None, email="managed@example.com", name="Managed"
        )
        submission.speakers.add(managed)
    client.force_login(user)

    response = client.post(submission.orga_urls.accept, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.ACCEPTED
        assert event.queued_mails.count() == 0


def test_submission_reject_warns_about_pending_mails(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        assert event.queued_mails.count() == 0
    client.force_login(user)
    warning = "There may be pending emails for this proposal that are now incorrect or outdated."

    response = client.post(submission.orga_urls.reject, follow=True)
    assert response.status_code == 200
    assert warning not in [str(m) for m in response.context["messages"]]
    assert _states(submission) == (SubmissionStates.REJECTED, None)
    with scopes_disabled():
        assert event.queued_mails.count() == 1

    response = client.post(submission.orga_urls.accept, follow=True)
    assert response.status_code == 200
    assert warning in [str(m) for m in response.context["messages"]]
    assert _states(submission) == (SubmissionStates.ACCEPTED, None)
    with scopes_disabled():
        assert event.queued_mails.count() == 2
        event.queued_mails.update(state=QueuedMailStates.SENT)

    response = client.post(submission.orga_urls.reject, follow=True)
    assert response.status_code == 200
    assert warning not in [str(m) for m in response.context["messages"]]
    assert _states(submission) == (SubmissionStates.REJECTED, None)


def test_submission_delete(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        code = submission.code
    client.force_login(user)

    response = client.get(submission.orga_urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert Submission.objects.filter(event=event).count() == 1

    response = client.post(submission.orga_urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert Submission.objects.filter(event=event).count() == 0
        assert not Submission.all_objects.filter(code=code).exists()


def test_submission_delete_htmx_renders_dialog_and_redirects_via_header(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    response = client.get(submission.orga_urls.delete, headers=DIALOG_HEADERS)

    assert response.status_code == 200
    assert all(name.endswith("#dialog") for name in response.template_name)
    assert response.template_name[-1] == "common/includes/action_confirm.html#dialog"
    assert response.context["action_object_name"] == submission.title

    response = client.post(submission.orga_urls.delete, headers=DIALOG_HEADERS)

    assert response.status_code == 286
    assert response["HX-Redirect"] == event.orga_urls.submissions
    with scopes_disabled():
        assert Submission.objects.filter(event=event).count() == 0


def test_submission_accept_htmx_renders_dialog_and_redirects_via_header(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    client.force_login(user)

    response = client.get(submission.orga_urls.accept, headers=DIALOG_HEADERS)

    assert response.status_code == 200
    assert response.template_name[-1] == "common/includes/action_confirm.html#dialog"
    assert response.context["target"] == SubmissionStates.ACCEPTED

    response = client.post(submission.orga_urls.accept, headers=DIALOG_HEADERS)

    assert response.status_code == 286
    assert response["HX-Redirect"] == event.orga_urls.submissions
    with scopes_disabled():
        submission.refresh_from_db()
    assert submission.state == SubmissionStates.ACCEPTED


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


@pytest.mark.parametrize(
    ("user_kwargs", "expected"),
    (
        ({"can_change_submissions": True}, 200),
        ({"can_change_submissions": False, "is_reviewer": True}, 404),
        ({"can_change_submissions": False, "can_change_event_settings": True}, 404),
        (None, 404),
    ),
    ids=("orga", "reviewer", "settings_only_orga", "unrelated_user"),
)
def test_submission_create_page_access_by_role(client, event, user_kwargs, expected):
    with scopes_disabled():
        user = (
            UserFactory()
            if user_kwargs is None
            else make_orga_user(event, **user_kwargs)
        )
    client.force_login(user)

    response = client.get(event.orga_urls.new_submission)

    assert response.status_code == expected
    if expected == 200:
        with scopes_disabled():
            submission_type = event.submission_types.first()
        assert str(submission_type.name) in response.content.decode()


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
            "speaker-send_invite": "on",
            "speaker-invite_subject": "Claim your speaker profile",
            "speaker-invite_text": "Please claim your profile: {invitation_link}",
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
        # Exactly one create log entry, attributed to the orga.
        creates = list(
            sub.logged_actions().filter(action_type="pretalx.submission.create")
        )
        assert len(creates) == 1
        assert creates[0].is_orga_action is True


def test_submission_create_preserves_submitted_content_locale(client):
    event = EventFactory(locales=["en", "de"], content_locales=["en", "de"])
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        type_pk = event.submission_types.first().pk
    client.force_login(user)

    response = client.post(
        event.orga_urls.new_submission,
        data={
            "abstract": "abstract",
            "content_locale": "de",
            "description": "description",
            "duration": "",
            "slot_count": 1,
            "notes": "notes",
            "internal_notes": "internal_notes",
            "speaker-email": "newbie@example.org",
            "speaker-name": "Foo Speaker",
            "speaker-locale": "en",
            "title": "Mein toller Vortrag",
            "submission_type": type_pk,
            "state": "submitted",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        sub = event.submissions.get()
        assert sub.content_locale == "de"


def test_submission_create_with_state_accepted_applies_scheduling(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        type_pk = event.submission_types.first().pk
        room = RoomFactory(event=event)
    start = event.datetime_from + dt.timedelta(hours=2)
    end = start + dt.timedelta(minutes=30)
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
            "speaker-email": "newbie@example.org",
            "speaker-name": "Foo Speaker",
            "speaker-locale": "en",
            "title": "Pre-scheduled Talk",
            "submission_type": type_pk,
            "state": "accepted",
            "room": room.pk,
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        sub = event.submissions.get()
        assert sub.state == SubmissionStates.ACCEPTED
        slot = sub.slots.select_related("room", "schedule").get(
            schedule=event.wip_schedule
        )
        assert slot.room == room
        assert slot.start == start
        assert slot.end == end


def test_submission_create_fires_before_state_change_signal(
    client, event, register_signal_handler
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        type_pk = event.submission_types.first().pk

    received = []

    def block_state_change(signal, sender, **kwargs):
        received.append(kwargs)
        raise SubmissionError("Blocked by plugin")

    register_signal_handler(before_submission_state_change, block_state_change)
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
            "speaker-email": "newbie@example.org",
            "speaker-name": "Foo Speaker",
            "speaker-locale": "en",
            "title": "Vetoed Talk",
            "submission_type": type_pk,
            "state": "accepted",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert len(received) == 1
    assert received[0]["new_state"] == SubmissionStates.ACCEPTED
    with scopes_disabled():
        assert not event.submissions.filter(title="Vetoed Talk").exists()


def test_submission_edit_logs_changes(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(
            event=event,
            state=SubmissionStates.ACCEPTED,
            abstract="Existing abstract",
            description="Existing description",
            notes="Existing notes",
        )
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
    data = {
        "abstract": "Existing abstract",
        "content_locale": submission.content_locale,
        "description": "Existing description",
        "duration": "",
        "notes": "Existing notes",
        "title": old_title,
        "submission_type": submission.submission_type.pk,
        "resource-TOTAL_FORMS": 0,
        "resource-INITIAL_FORMS": 0,
    }

    response = client.post(submission.orga_urls.base, data=data, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert submission.logged_actions().count() == initial_log_count

    response = client.post(
        submission.orga_urls.base,
        data={**data, "title": "New Updated Title", f"question_{question.pk}": "50"},
        follow=True,
    )
    assert response.status_code == 200
    msgs = [str(m) for m in response.context["messages"]]
    assert any("updated" in m.lower() for m in msgs)
    with scopes_disabled():
        submission.refresh_from_db(fields=["title"])
        assert submission.title == "New Updated Title"
        logs = submission.logged_actions()
        assert logs.count() == initial_log_count + 1
        update_log = logs.filter(action_type="pretalx.submission.update").get()
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
        submission = SubmissionFactory(
            event=event, title="Original title", abstract="Test abstract"
        )
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

    def data(new_description):
        # The test client reads the FieldFiles to EOF, so every POST needs
        # fresh instances.
        with scopes_disabled():
            resource_one.refresh_from_db(fields=["resource"])
            resource_two.refresh_from_db(fields=["resource"])
        return {
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
            "resource-2-description": new_description,
            "resource-2-resource": SimpleUploadedFile("testfile.txt", b"file_content"),
            "resource-TOTAL_FORMS": 3,
            "resource-INITIAL_FORMS": 2,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        }

    response = client.post(submission.orga_urls.base, data=data(""), follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db(fields=["title"])
        assert submission.resources.count() == 2
        assert submission.resources.filter(pk=resource_two.pk).exists()
        assert submission.title == "Original title"

    response = client.post(
        submission.orga_urls.base, data=data("new resource"), follow=True
    )
    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db(fields=["title"])
        resource_one.refresh_from_db(fields=["description"])
        new_resource = submission.resources.exclude(pk=resource_one.pk).get()
        assert submission.title == "new title"
        assert resource_one.description == "new resource name"
        assert new_resource.description == "new resource"
        assert new_resource.resource.read() == b"file_content"
        assert not submission.resources.filter(pk=resource_two.pk).exists()


def test_submission_edit_unchanged_resource_not_resaved(client, event):
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
    response = client.post(submission.orga_urls.speakers, data={"email": email})

    assert response.status_code == 302
    with scopes_disabled():
        assert submission.speakers.count() == 2
        added = (
            submission.speakers.select_related("user", "event")
            .exclude(pk=speaker.pk)
            .get()
        )
    assert response.url == added.orga_urls.base


def test_submission_speakers_add_denied_for_reviewer(client, event):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        submission = SubmissionFactory(event=event)
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.speakers,
        data={"email": "sneaky@example.com", "name": "Sneaky Add"},
        follow=True,
    )

    assert response.status_code == 404
    with scopes_disabled():
        assert submission.speakers.count() == 0


def test_submission_speakers_page_and_add_edge_cases(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        other = SubmissionFactory(event=event, title="Other proposal")
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        other.speakers.add(speaker)
        speaker_email = speaker.user.email
        managed = SpeakerFactory(event=event, user=None, email="managed@example.com")
    djmail.outbox = []
    client.force_login(user)

    response = client.get(submission.orga_urls.speakers, follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Other proposal" in content
    assert other.orga_urls.base in content

    response = client.post(
        submission.orga_urls.speakers, data={"speaker": f"profile:{managed.code}"}
    )
    assert response.status_code == 302
    assert response.url == submission.orga_urls.speakers
    with scopes_disabled():
        assert set(submission.speakers.all()) == {speaker, managed}
        managed.refresh_from_db(fields=["invitation_token"])
        assert managed.invitation_token is None
        assert event.queued_mails.count() == 0
    assert len(djmail.outbox) == 0

    for data in (
        {"speaker": "foooobaaaaar", "name": "Name"},
        {"email": ""},
        {"speaker": speaker_email, "name": "Name"},
    ):
        response = client.post(submission.orga_urls.speakers, data=data, follow=True)
        assert response.status_code == 200
        with scopes_disabled():
            assert set(submission.speakers.all()) == {speaker, managed}

    response = client.post(
        submission.orga_urls.speakers, data={"name": "No Mail Person"}, follow=True
    )
    assert response.status_code == 200
    assert "confirm_email_less" in response.text
    with scopes_disabled():
        assert set(submission.speakers.all()) == {speaker, managed}

    response = client.post(
        submission.orga_urls.speakers,
        data={"name": "No Mail Person", "confirm_email_less": "on"},
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        no_mail_speaker = submission.speakers.exclude(
            pk__in=[speaker.pk, managed.pk]
        ).get()
        assert no_mail_speaker.name == "No Mail Person"
        assert no_mail_speaker.email is None
        assert no_mail_speaker.user is None


def test_submission_speakers_remove(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        managed = SpeakerFactory(
            event=event, user=None, origin=SpeakerProfileOrigin.ORGA
        )
        submission.speakers.add(speaker, managed)
        mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
        mail.to_speakers.add(managed)
        other_speaker = SpeakerFactory(event=event)
        other_sub = SubmissionFactory(event=event)
        other_sub.speakers.add(other_speaker)
        speaker_name = speaker.get_display_name()
    client.force_login(user)

    response = client.post(
        f"{submission.orga_urls.delete_speaker}?id={other_speaker.pk}", follow=True
    )
    assert response.status_code == 200
    assert "not part of this proposal" in response.content.decode()
    with scopes_disabled():
        assert set(submission.speakers.all()) == {speaker, managed}

    url = f"{submission.orga_urls.delete_speaker}?id={speaker.pk}"
    response = client.get(url, follow=True)
    assert response.status_code == 200
    assert speaker_name in response.content.decode()
    with scopes_disabled():
        assert set(submission.speakers.all()) == {speaker, managed}

    response = client.post(url, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert list(submission.speakers.all()) == [managed]

    url = f"{submission.orga_urls.delete_speaker}?id={managed.pk}"
    response = client.post(url, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert submission.speakers.count() == 0
        managed.refresh_from_db(fields=["origin"])
        assert managed.origin == SpeakerProfileOrigin.ORGA
        submission.speakers.add(managed)

    response = client.post(url, {"delete_profile": "on"}, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert submission.speakers.count() == 0
        assert not SpeakerProfile.objects.filter(pk=managed.pk).exists()
        assert not event.queued_mails.filter(pk=mail.pk).exists()


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
        role1.position = 0
        role2.position = 1
        SpeakerRole.objects.bulk_update([role1, role2], ["position"])
        initial_log_count = submission.logged_actions().count()
    client.force_login(user)

    for order in ("", "9999999"):
        response = client.post(
            submission.orga_urls.reorder_speakers, data={"order": order}
        )
        assert response.status_code == 400

    response = client.post(
        submission.orga_urls.reorder_speakers, data={"order": f"{role1.pk},{role2.pk}"}
    )
    assert response.status_code == 204
    with scopes_disabled():
        assert list(Submission.objects.get(pk=submission.pk).sorted_speakers) == [
            speaker1,
            speaker2,
        ]
        assert submission.logged_actions().count() == initial_log_count

    response = client.post(
        submission.orga_urls.reorder_speakers, data={"order": f"{role2.pk},{role1.pk}"}
    )
    assert response.status_code == 204
    with scopes_disabled():
        assert list(Submission.objects.get(pk=submission.pk).sorted_speakers) == [
            speaker2,
            speaker1,
        ]
        assert submission.logged_actions().count() == initial_log_count + 1


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


def test_submission_anonymise(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        submission = SubmissionFactory(event=event)
        other = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        phase = event.active_review_phase
        phase.can_see_speaker_names = False
        phase.save()
    client.force_login(user)

    response = client.post(
        submission.orga_urls.anonymise,
        data={"description": "CENSORED!", "action": "next"},
    )
    assert response.status_code == 302
    assert response.url == other.orga_urls.anonymise
    with scopes_disabled():
        submission.refresh_from_db(fields=["anonymised"])
    assert submission.is_anonymised
    assert submission.anonymised == {
        "_anonymised": True,
        "abstract": "",
        "notes": "",
        "description": "CENSORED!",
        "title": "",
    }

    response = client.post(
        submission.orga_urls.anonymise,
        data={"description": "NEW CENSORED!"},
        follow=True,
    )
    assert response.status_code == 200
    assert len(response.context["submit_buttons"]) == 2
    with scopes_disabled():
        submission.refresh_from_db(fields=["anonymised"])
    assert submission.anonymised["description"] == "NEW CENSORED!"

    response = client.post(
        other.orga_urls.anonymise, data={"description": "LAST ONE"}, follow=True
    )
    assert response.status_code == 200
    assert len(response.context["submit_buttons"]) == 1

    response = client.get(submission.orga_urls.base)
    assert response.status_code == 200
    assert "CENSORED" not in response.content.decode()

    client.force_login(reviewer)
    response = client.get(submission.orga_urls.base)
    assert response.status_code == 200
    assert "NEW CENSORED!" in response.content.decode()


@pytest.mark.parametrize("use_tracks", (True, False))
def test_submission_statistics(client, use_tracks):
    event = EventFactory(feature_flags={"use_tracks": use_tracks})
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        if use_tracks:
            TrackFactory(event=event)
            TrackFactory(event=event)
    client.force_login(user)

    response = client.get(event.orga_urls.stats)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Proposals by submission date" not in content
    assert "Proposals by state" not in content

    with scopes_disabled():
        sub1 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        sub2 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        sub3 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        logs = [
            sub.log_action("pretalx.submission.create") for sub in (sub1, sub2, sub3)
        ]
        # Move one accepted proposal to another date so the talk timeline has
        # two data points.
        ActivityLog.objects.filter(pk=logs[1].pk).update(
            timestamp=logs[1].timestamp - dt.timedelta(days=2)
        )

    response = client.get(event.orga_urls.stats)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Proposals by state" in content
    assert "Proposals by submission date" in content
    assert response.context["talk_timeline_data"] != ""
    assert ("Proposals by track" in content) is use_tracks


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

    with django_assert_num_queries(21):
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

    with django_assert_num_queries(14):
        response = client.get(event.orga_urls.feedback, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(sub.title in content for sub in submissions)


def test_submission_apply_pending_bulk(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.apply_pending)
    assert response.status_code == 200
    # No submit button when there are no pending submissions
    assert "Do it" not in response.content.decode()

    with scopes_disabled():
        submission = SubmissionFactory(
            event=event,
            state=SubmissionStates.SUBMITTED,
            pending_state=SubmissionStates.ACCEPTED,
        )
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)

    response = client.get(event.orga_urls.apply_pending)
    assert response.status_code == 200
    assert "Do it" in response.content.decode()
    assert _states(submission) == (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
    )

    response = client.post(event.orga_urls.apply_pending)
    assert response.status_code == 302
    assert _states(submission) == (SubmissionStates.ACCEPTED, None)
    with scopes_disabled():
        assert event.queued_mails.count() == 1


@pytest.mark.parametrize("item_count", (1, 3))
def test_tag_list_query_count(client, event, item_count, django_assert_num_queries):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        tags = TagFactory.create_batch(item_count, event=event)
    client.force_login(user)

    with django_assert_num_queries(14):
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


def test_tag_edit_and_delete(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        tag = TagFactory(event=event)
        original_name = str(tag.tag)
        initial_log_count = tag.logged_actions().count()
    client.force_login(user)

    response = client.get(tag.urls.base)
    assert response.status_code == 200
    assert original_name in response.content.decode()

    response = client.post(
        tag.urls.base, {"tag": original_name, "color": tag.color}, follow=True
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert tag.logged_actions().count() == initial_log_count

    response = client.post(
        tag.urls.base, {"tag": "Renamed", "color": "#fgff99"}, follow=True
    )
    assert response.status_code == 200
    with scopes_disabled():
        tag.refresh_from_db(fields=["tag"])
        assert tag.logged_actions().count() == initial_log_count
    assert str(tag.tag) == original_name

    response = client.post(
        tag.urls.base, {"tag": "Renamed", "color": "#ffff99"}, follow=True
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert tag.logged_actions().count() == initial_log_count + 1
        tag.refresh_from_db(fields=["tag"])
    assert str(tag.tag) == "Renamed"

    response = client.get(tag.urls.delete)
    assert response.status_code == 200
    with scopes_disabled():
        assert event.tags.count() == 1

    response = client.post(tag.urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert event.tags.count() == 0


def test_tag_offered_in_submission_filter_and_delete_cascades(client, event):
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
    content = response.content.decode()
    assert f'value="{tag.pk}"' in content
    assert tag.tag in content

    response = client.post(tag.urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert event.tags.count() == 0
        assert sub1.tags.count() == 0
        assert sub2.tags.count() == 0


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

    with django_assert_num_queries(16):
        response = client.get(submission.orga_urls.comments, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(comment.text in content for comment in comments)


def test_submission_comment_create_and_delete(client, event):
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

    response = client.post(
        submission.orga_urls.comments,
        data={"text": "Here is a new comment!"},
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        comment = submission.comments.get()
        assert comment.text == "Here is a new comment!"
        assert [log.action_type for log in comment.logged_actions()] == [
            "pretalx.submission.comment.create"
        ]
        delete_url = comment.urls.delete

    response = client.get(delete_url, follow=True)
    assert response.status_code == 200

    response = client.post(delete_url, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert not SubmissionComment.objects.filter(pk=comment.pk).exists()


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

    with django_assert_num_queries(19):
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


def test_submission_pending_state_changes(client, event):
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
    assert _states(submission) == (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
    )

    response = client.post(
        submission.orga_urls.make_submitted, data={"pending": "on"}, follow=True
    )
    assert response.status_code == 200
    assert _states(submission) == (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
    )

    response = client.post(
        submission.orga_urls.reject, data={"pending": "on"}, follow=True
    )
    assert response.status_code == 200
    assert _states(submission) == (
        SubmissionStates.SUBMITTED,
        SubmissionStates.REJECTED,
    )
    with scopes_disabled():
        assert submission.slots.count() == 0

    response = client.post(submission.orga_urls.make_submitted, follow=True)
    assert response.status_code == 200
    assert _states(submission) == (SubmissionStates.SUBMITTED, None)

    response = client.post(
        submission.orga_urls.accept, data={"pending": "on"}, follow=True
    )
    assert response.status_code == 200
    assert _states(submission) == (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
    )

    response = client.post(submission.orga_urls.apply_pending)
    assert response.status_code == 302
    assert _states(submission) == (SubmissionStates.ACCEPTED, None)
    with scopes_disabled():
        assert event.queued_mails.count() == 1


def test_submission_speakers_add_invite_send_error_rolls_back(
    client, event, monkeypatch
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)
    djmail.outbox = []

    def explode(*args, **kwargs):
        raise SendMailException("nope")

    monkeypatch.setattr("pretalx.orga.forms.submission.send_speaker_invite", explode)

    response = client.post(
        submission.orga_urls.speakers,
        data={
            "email": "newperson@example.com",
            "name": "New Person",
            "send_invite": "on",
            "invite_subject": "Claim your speaker profile",
            "invite_text": "Claim it: {invitation_link}",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert response.context["form"].non_field_errors()
    assert len(djmail.outbox) == 0
    with scopes_disabled():
        assert submission.speakers.count() == 0
        assert not SpeakerProfile.objects.filter(event=event).exists()


def test_submission_create_speaker_invite_send_error_shows_message(
    client, event, monkeypatch
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        type_pk = event.submission_types.first().pk
    client.force_login(user)
    djmail.outbox = []

    def explode(*args, **kwargs):
        raise SendMailException("mail server down")

    monkeypatch.setattr("pretalx.orga.forms.submission.send_speaker_invite", explode)

    response = client.post(
        event.orga_urls.new_submission,
        data={
            "abstract": "abstract",
            "content_locale": "en",
            "description": "description",
            "duration": "",
            "slot_count": 1,
            "notes": "notes",
            "speaker-email": "newbie@example.org",
            "speaker-name": "Foo Speaker",
            "speaker-locale": "en",
            "speaker-send_invite": "on",
            "speaker-invite_subject": "Claim your speaker profile",
            "speaker-invite_text": "Claim it: {invitation_link}",
            "title": "Talk With Failing Invite",
            "submission_type": type_pk,
            "state": "submitted",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert "mail server down" in response.content.decode()
    with scopes_disabled():
        assert event.submissions.count() == 1


def test_submission_create_without_speaker_and_with_answers(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        type_pk = event.submission_types.first().pk
        question = QuestionFactory(
            event=event,
            target="submission",
            variant=QuestionVariant.STRING,
            question_required=QuestionRequired.OPTIONAL,
        )
    client.force_login(user)
    data = {
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
    }

    response = client.post(
        event.orga_urls.new_submission,
        data={**data, "speaker-speaker": "not-an-email", "speaker-name": "Name"},
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert event.submissions.count() == 0
    assert (
        '<option value="not-an-email" selected>not-an-email</option>' in response.text
    )

    response = client.post(
        event.orga_urls.new_submission,
        data={**data, f"question_{question.pk}": "Hello"},
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        sub = event.submissions.get()
        assert sub.title == "Talk Without Speaker"
        assert sub.speakers.count() == 0
        answer = sub.answers.get(question=question)
        assert answer.answer == "Hello"
        QuestionFactory(
            event=event,
            target="submission",
            variant=QuestionVariant.STRING,
            question_required=QuestionRequired.REQUIRED,
        )

    response = client.post(event.orga_urls.new_submission, data=data, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert event.submissions.count() == 1


def test_submission_content_query_count(client, event, django_assert_num_queries):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    with django_assert_num_queries(23):
        response = client.get(submission.orga_urls.base, follow=True)

    assert response.status_code == 200
    assert submission.title in response.content.decode()

    response = client.get(submission.orga_urls.base + "JJ", follow=True)
    assert response.status_code == 404


def test_submission_speakers_query_count(client, event, django_assert_num_queries):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    with django_assert_num_queries(19):
        response = client.get(submission.orga_urls.speakers, follow=True)

    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_submission_state_change_handles_submission_error(
    client, event, register_signal_handler
):
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


def test_submission_apply_pending_handles_submission_error(
    client, event, register_signal_handler
):
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

    response = client.post(sub_blocked.orga_urls.apply_pending)
    assert response.status_code == 302
    assert _states(sub_blocked) == (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
    )

    response = client.post(event.orga_urls.apply_pending, follow=True)
    assert response.status_code == 200
    assert _states(sub_ok) == (SubmissionStates.REJECTED, None)
    assert _states(sub_blocked) == (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
    )


@pytest.mark.parametrize(
    "signup_required", (True, False), ids=("required", "not_required")
)
def test_submission_content_signup_tab_and_dropdown_visibility(client, signup_required):
    event = EventFactory(
        feature_flags={"attendee_signup": True} if signup_required else {}
    )
    if signup_required:
        sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
        submission = SubmissionFactory(event=event, submission_type=sub_type)
    else:
        submission = SubmissionFactory(event=event)
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(submission.orga_urls.base, follow=True)

    content = response.content.decode()
    assert (submission.orga_urls.signup in content) is signup_required
    assert ("id_attendee_signup_required" in content) is signup_required


def test_submission_signup_page(client):
    event = EventFactory(feature_flags={"attendee_signup": True})
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(
        event=event, submission_type=sub_type, attendee_signup_capacity=4
    )
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        confirmed = AttendeeSignupFactory(submission=submission)
        AttendeeSignupFactory(submission=submission)
        confirmed_email = confirmed.attendee.user.email
    client.force_login(user)

    response = client.get(submission.orga_urls.signup, follow=True)
    content = response.content.decode()
    assert "Attendees" in content
    assert "Attendee capacity" in content
    assert "--progress-width: 50%" in content

    with scopes_disabled():
        canceled = AttendeeSignupFactory(submission=submission, state="canceled")
        canceled_email = canceled.attendee.user.email

    response = client.get(submission.orga_urls.signup + "?state=confirmed", follow=True)
    content = response.content.decode()
    assert confirmed_email in content
    assert canceled_email not in content

    response = client.post(
        submission.orga_urls.signup, data={"attendee_signup_capacity": "0"}
    )
    assert b"id_attendee_signup_capacity" in response.content
    with scopes_disabled():
        submission.refresh_from_db(fields=["attendee_signup_capacity"])
    assert submission.attendee_signup_capacity == 4

    for new_capacity, expected in ((1, 1), (42, 42)):
        response = client.post(
            submission.orga_urls.signup,
            data={"attendee_signup_capacity": str(new_capacity)},
            follow=True,
        )
        assert response.status_code == 200
        with scopes_disabled():
            submission.refresh_from_db(fields=["attendee_signup_capacity"])
        assert submission.attendee_signup_capacity == expected


def test_submission_signup_get_404_when_signup_not_required(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    response = client.get(submission.orga_urls.signup, follow=True)

    assert response.status_code == 404


def test_submission_signup_reviewer_returns_404(client):
    event = EventFactory(feature_flags={"attendee_signup": True})
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(event=event, submission_type=sub_type)
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
    client.force_login(reviewer)

    response = client.get(submission.orga_urls.signup, follow=True)

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("has_signup", "expected"),
    ((False, False), (True, None)),
    ids=("clears_when_empty", "blocked_with_signups"),
)
def test_submission_content_post_attendee_signup_required(client, has_signup, expected):
    event = EventFactory(feature_flags={"attendee_signup": True})
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(event=event, submission_type=sub_type)
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        if has_signup:
            AttendeeSignupFactory(submission=submission)
    client.force_login(user)

    client.post(
        submission.orga_urls.base,
        data={
            "title": submission.title,
            "submission_type": submission.submission_type.pk,
            "content_locale": "en",
            "abstract": submission.abstract or "x",
            "description": submission.description or "x",
            "notes": submission.notes or "x",
            "internal_notes": "",
            "duration": "",
            "slot_count": "1",
            "attendee_signup_required": "false",
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
        },
        follow=True,
    )

    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.attendee_signup_required is expected
