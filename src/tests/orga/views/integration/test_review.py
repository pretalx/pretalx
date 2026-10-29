# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json
import tempfile

import pytest
from django.contrib.messages import constants as message_constants
from django.contrib.messages import get_messages
from django.core.cache import cache
from django_scopes import scopes_disabled

from pretalx.mail.enums import QueuedMailStates
from pretalx.submission.models import SubmissionStates
from pretalx.submission.models.question import QuestionRequired, QuestionVariant
from tests.factories import (
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TagFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _make_reviewer(event, **extra_kwargs):
    return make_orga_user(
        event,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_organiser_settings=False,
        **extra_kwargs,
    )


def _get_category_and_score(event, value=1):
    with scopes_disabled():
        category = event.score_categories.first()
        score = category.scores.filter(value=value).first()
    return category, score


def _review_count(submission):
    with scopes_disabled():
        return submission.reviews.count()


def _assigned_count(submission):
    with scopes_disabled():
        return submission.assigned_reviewers.count()


def test_review_dashboard_denied_for_unprivileged_user(client, event):
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.orga_urls.reviews)

    assert response.status_code == 404


@pytest.mark.parametrize("item_count", (1, 3))
def test_review_dashboard_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submissions = SubmissionFactory.create_batch(item_count, event=event)
        for sub in submissions:
            sub.speakers.add(SpeakerFactory(event=event))
        ReviewFactory(submission=submissions[0], user=reviewer)
    client.force_login(reviewer)

    with django_assert_num_queries(28):
        response = client.get(event.orga_urls.reviews)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(sub.title in content for sub in submissions)


@pytest.mark.parametrize("sort", ("count", "-count", "score", "-score"))
def test_review_dashboard_sort_query_count(
    client, event, sort, django_assert_num_queries
):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        ReviewFactory(submission=submission, user=reviewer)
    client.force_login(reviewer)

    with django_assert_num_queries(28):
        response = client.get(event.orga_urls.reviews + "?sort=" + sort)

    assert response.status_code == 200
    assert submission.title in response.content.decode()


@pytest.mark.parametrize("item_count", (1, 3))
def test_review_dashboard_with_track_limit_query_count(
    client, item_count, django_assert_num_queries
):
    event = EventFactory(
        feature_flags={"use_tracks": True}, review_phase__can_tag_submissions="use_tags"
    )
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        track = TrackFactory(event=event)
        reviewer.teams.first().limit_tracks.add(track)
        tag = TagFactory(event=event)
        submissions = SubmissionFactory.create_batch(
            item_count, event=event, track=track
        )
        for sub in submissions:
            sub.speakers.add(SpeakerFactory(event=event))
            sub.tags.add(tag)
        ReviewFactory(submission=submissions[0], user=reviewer)
    client.force_login(reviewer)

    with django_assert_num_queries(29):
        response = client.get(event.orga_urls.reviews)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(sub.title in content for sub in submissions)
    assert tag.tag in content


@pytest.mark.parametrize("item_count", (1, 3))
def test_review_dashboard_with_tag_filter_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        tag = TagFactory(event=event)
        submissions = SubmissionFactory.create_batch(item_count, event=event)
        for sub in submissions:
            sub.speakers.add(SpeakerFactory(event=event))
            sub.tags.add(tag)
    client.force_login(reviewer)

    with django_assert_num_queries(30):
        response = client.get(f"{event.orga_urls.reviews}?tags={tag.pk}")

    assert response.status_code == 200
    content = response.content.decode()
    assert all(sub.title in content for sub in submissions)
    assert tag.tag in content


@pytest.mark.parametrize("item_count", (1, 3))
def test_review_submission_post_creates_review(
    client, event, django_assert_num_queries, item_count
):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        category, score = _get_category_and_score(event)
        extra = SubmissionFactory.create_batch(item_count - 1, event=event)
        for sub in extra:
            sub.speakers.add(SpeakerFactory(event=event))
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.reviews.count() == 1
        review = submission.reviews.first()
        assert review.score == 1
        assert review.text == "LGTM"

    cache.clear()
    with django_assert_num_queries(31):
        response = client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 200
    assert "LGTM" in response.content.decode()


def test_review_submission_post_with_tags(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        tag = TagFactory(event=event)
        event.active_review_phase.can_tag_submissions = "use_tags"
        event.active_review_phase.save()
        assert not submission.tags.count()
        category, score = _get_category_and_score(event)
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM", "tags": "99999"},
    )
    assert response.status_code == 200
    assert _review_count(submission) == 0

    response = client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM", "tags": str(tag.id)},
    )
    assert response.status_code == 200
    assert str(tag.tag) in response.content.decode()
    with scopes_disabled():
        review = submission.reviews.get()
        assert review.score == 1
        assert review.text == "LGTM"
        assert list(submission.tags.all()) == [tag]


def test_review_submission_post_tagging_disabled(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        tag = TagFactory(event=event)
        assert event.active_review_phase.can_tag_submissions == "never"
        assert not submission.tags.count()
        category, score = _get_category_and_score(event)
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM", "tags": str(tag.id)},
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.reviews.count() == 1
        assert submission.tags.count() == 0


def test_review_submission_restricted_visibility_requires_assignment(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        category, score = _get_category_and_score(event)
        event.active_review_phase.proposal_visibility = "assigned"
        event.active_review_phase.save()
    client.force_login(reviewer)
    data = {f"score_{category.id}": score.id, "text": "LGTM"}

    response = client.post(submission.orga_urls.reviews, follow=True, data=data)
    assert response.status_code == 404
    assert _review_count(submission) == 0

    response = client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 404

    with scopes_disabled():
        submission.assigned_reviewers.add(reviewer)

    response = client.post(submission.orga_urls.reviews, follow=True, data=data)
    assert response.status_code == 200
    with scopes_disabled():
        review = submission.reviews.get()
        assert review.score == 1
        assert review.text == "LGTM"

    response = client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 200


def test_review_submission_blanked_field_not_leaked_to_restricted_reviewer(
    client, event
):
    identity_revealing = "Hi, I am Jane Doe from BigCorp."
    with scopes_disabled():
        reviewer = _make_reviewer(event, force_hide_speaker_names=True)
        submission = SubmissionFactory(event=event, abstract=identity_revealing)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        # Organiser redacted the abstract by blanking it.
        submission.anonymised = {"_anonymised": True, "abstract": ""}
        submission.save(update_fields=["anonymised"])
    client.force_login(reviewer)

    response = client.get(submission.orga_urls.reviews)

    assert response.status_code == 200
    assert identity_revealing not in response.content.decode()


def test_review_submission_shows_actual_duration_not_type_default(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        sub_type = SubmissionTypeFactory(
            event=event, name="Keynote", default_duration=30
        )
        submission = SubmissionFactory(
            event=event, submission_type=sub_type, duration=70
        )
        submission.speakers.add(SpeakerFactory(event=event))
    client.force_login(reviewer)

    response = client.get(submission.orga_urls.reviews)

    content = response.content.decode()
    assert "1\xa0hour, 10\xa0minutes" in content
    assert "Keynote" in content
    assert "30 minutes" not in content


def test_review_submission_save_and_next(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        other_submission = SubmissionFactory(event=event)
        other_speaker = SpeakerFactory(event=event)
        other_submission.speakers.add(other_speaker)
        category, score = _get_category_and_score(event)
    client.force_login(reviewer)
    data = {
        f"score_{category.id}": score.id,
        "text": "LGTM",
        "review_submit": "save_and_next",
    }

    response = client.post(submission.orga_urls.reviews, data=data)
    assert response.status_code == 302
    assert other_submission.code in response.url
    assert _review_count(submission) == 1

    response = client.post(other_submission.orga_urls.reviews, data=data)
    assert response.status_code == 302
    assert response.url == event.orga_urls.reviews
    assert _review_count(other_submission) == 1


def test_review_submission_post_without_score(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        category = event.score_categories.first()
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": "", "text": "LGTM"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.reviews.count() == 1
        review = submission.reviews.first()
        assert review.score is None
        assert review.text == "LGTM"

    response = client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 200


def test_review_submission_post_without_score_when_mandatory(client):
    event = EventFactory(review_settings={"score_mandatory": True})
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        category = event.score_categories.first()
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": "", "text": "LGTM"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.reviews.count() == 0


@pytest.mark.parametrize("action", ("skip_for_now", "abstain"))
def test_review_submission_skip_with_required_fields(client, action):
    event = EventFactory(
        review_settings={"text_mandatory": True}, score_category__required=True
    )
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        category = event.score_categories.first()
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        data={f"score_{category.id}": "", "text": "", "review_submit": action},
    )

    assert response.status_code == 302
    with scopes_disabled():
        if action == "abstain":
            assert submission.reviews.count() == 1
            assert submission.reviews.first().score is None
        else:
            assert submission.reviews.count() == 0


def test_review_submission_post_invalid_review_rejected(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        category, score = _get_category_and_score(event)
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": "100", "text": "LGTM"},
    )
    assert response.status_code == 200
    assert _review_count(submission) == 0

    with scopes_disabled():
        QuestionFactory(
            event=event,
            variant=QuestionVariant.STRING,
            target="reviewer",
            question_required=QuestionRequired.REQUIRED,
        )

    response = client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
    )
    assert response.status_code == 200
    assert _review_count(submission) == 0

    response = client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 200


def test_review_submission_speaker_cannot_review_own(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        review_profile = SpeakerFactory(user=reviewer, event=event)
        submission.speakers.add(review_profile)
        category, score = _get_category_and_score(event)
        assert submission.reviews.count() == 0
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.reviews.count() == 0


def test_review_submission_edit_own_review_until_accepted(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        review = ReviewFactory(
            submission=submission, user=reviewer, score=1, text="Looks great!"
        )
        category = event.score_categories.first()
        old_score = category.scores.filter(value=1).first()
        new_score = category.scores.filter(value=2).first()
        assert review.score != new_score.value
    client.force_login(reviewer)

    response = client.get(review.urls.base, follow=True)
    assert response.status_code == 200
    assert "Looks great!" in response.content.decode()

    response = client.post(
        review.urls.base,
        follow=True,
        data={f"score_{category.id}": new_score.id, "text": "My mistake."},
    )
    assert response.status_code == 200
    with scopes_disabled():
        review.refresh_from_db(fields=["score", "text"])
        assert submission.reviews.count() == 1
    assert review.score == new_score.value
    assert review.text == "My mistake."

    with scopes_disabled():
        submission.accept()

    response = client.get(review.urls.base, follow=True)
    assert response.status_code == 200
    assert "My mistake." in response.content.decode()

    response = client.post(
        review.urls.base,
        follow=True,
        data={f"score_{category.id}": old_score.id, "text": "Changed"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        review.refresh_from_db(fields=["score", "text"])
        assert submission.reviews.count() == 1
    assert review.score == new_score.value
    assert review.text == "My mistake."

    client.force_login(_make_reviewer(event))
    response = client.post(
        submission.orga_urls.reviews,
        data={f"score_{category.id}": new_score.id, "text": "LGTM"},
        follow=True,
    )
    assert response.status_code == 200
    assert _review_count(submission) == 1


def test_review_submission_cannot_see_other_review_before_own(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        other_reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        existing_review = ReviewFactory(
            submission=submission, user=reviewer, text="Looks great!"
        )
        category, score = _get_category_and_score(event)
    client.force_login(other_reviewer)

    response = client.get(existing_review.urls.base, follow=True)
    assert response.status_code == 200
    assert existing_review.text not in response.content.decode()

    response = client.post(
        existing_review.urls.base,
        follow=True,
        data={
            f"score_{category.id}": score.id,
            "text": "My mistake.",
            "review_submit": "save",
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        existing_review.refresh_from_db()
        assert submission.reviews.count() == 2
    assert existing_review.score != 0
    assert existing_review.text != "My mistake."
    content = response.content.decode()
    assert existing_review.text in content
    assert "My mistake" in content


@pytest.mark.parametrize(
    ("is_reviewer", "force_hide_speaker_names", "phase_shows_names", "expected_count"),
    (
        (True, False, True, 1),
        (True, False, False, 0),
        (True, False, None, 1),
        (True, True, True, 0),
        (False, False, True, 1),
        (False, False, False, 1),
    ),
)
def test_review_submission_heading_speaker_names_follow_review_phase(
    client,
    event,
    is_reviewer,
    force_hide_speaker_names,
    phase_shows_names,
    expected_count,
):
    speaker_name = "Jane Realname"
    with scopes_disabled():
        if phase_shows_names is None:
            event.review_phases.update(is_active=False)
        else:
            event.active_review_phase.can_see_speaker_names = phase_shows_names
            event.active_review_phase.save()
        orga_user = make_orga_user(
            event,
            can_change_submissions=True,
            is_reviewer=is_reviewer,
            force_hide_speaker_names=force_hide_speaker_names,
        )
        submission = SubmissionFactory(event=event)
        submission.speakers.add(
            SpeakerFactory(event=event, user=None, name=speaker_name)
        )
    client.force_login(orga_user)

    response = client.get(submission.orga_urls.reviews)

    assert response.content.decode().count(speaker_name) == expected_count


def test_review_submission_orga_cannot_add_review(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        category, score = _get_category_and_score(event)
    client.force_login(orga_user)

    response = client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.reviews.count() == 0


def test_review_dashboard_post_bulk_accept_and_reject(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        other_submission = SubmissionFactory(event=event)
        other_speaker = SpeakerFactory(event=event)
        other_submission.speakers.add(other_speaker)
        accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        accepted_speaker = SpeakerFactory(event=event)
        accepted.speakers.add(accepted_speaker)
        managed_submission = SubmissionFactory(event=event)
        managed = SpeakerFactory(event=event, user=None, name="Managed Speaker")
        managed_submission.speakers.add(managed)
        mail_count = event.queued_mails.count()
    client.force_login(orga_user)

    def states(sub):
        with scopes_disabled():
            sub.refresh_from_db(fields=["state", "pending_state"])
        return sub.state, sub.pending_state

    response = client.post(
        event.orga_urls.reviews,
        {
            f"s-{submission.code}": "accept",
            f"s-{other_submission.code}": "reject",
            "pending": "on",
        },
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert event.queued_mails.count() == mail_count
    assert states(submission) == (SubmissionStates.SUBMITTED, SubmissionStates.ACCEPTED)
    assert states(other_submission) == (
        SubmissionStates.SUBMITTED,
        SubmissionStates.REJECTED,
    )

    response = client.post(
        event.orga_urls.reviews,
        {
            "foo": "bar",
            f"s-{submission.code}": "accept",
            f"s-{other_submission.code}": "reject",
            f"s-{accepted.code}": "reject",
            f"s-{managed_submission.code}": "accept",
        },
        follow=True,
    )
    assert response.status_code == 200
    body = response.content.decode()
    assert "were not emailed automatically" in body
    assert "Managed Speaker" in body
    with scopes_disabled():
        assert event.queued_mails.count() == mail_count + 2
    assert states(submission) == (SubmissionStates.ACCEPTED, None)
    assert states(other_submission) == (SubmissionStates.REJECTED, None)
    assert states(accepted) == (SubmissionStates.ACCEPTED, None)
    assert states(managed_submission) == (SubmissionStates.ACCEPTED, None)


def test_review_dashboard_post_bulk_accept_respects_track_isolation(client):
    event = EventFactory(feature_flags={"use_tracks": True})
    with scopes_disabled():
        event.review_phases.filter(is_active=True).update(
            proposal_visibility="all", can_change_submission_state=True
        )
        reviewer = _make_reviewer(event, can_change_event_settings=True)
        my_track = TrackFactory(event=event)
        other_track = TrackFactory(event=event)
        reviewer.teams.first().limit_tracks.add(my_track)
        out_of_track = SubmissionFactory(event=event, track=other_track)
        out_of_track.speakers.add(SpeakerFactory(event=event))
        mail_count = event.queued_mails.count()
    client.force_login(reviewer)

    response = client.post(
        event.orga_urls.reviews, {f"s-{out_of_track.code}": "accept"}
    )

    assert response.status_code == 200
    with scopes_disabled():
        out_of_track.refresh_from_db()
        assert out_of_track.state == SubmissionStates.SUBMITTED
        assert event.queued_mails.count() == mail_count


def test_regenerate_decision_mails_post(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        accepted_speaker = SpeakerFactory(event=event)
        accepted.speakers.add(accepted_speaker)
        rejected = SubmissionFactory(event=event)
        rejected_speaker = SpeakerFactory(event=event)
        rejected.speakers.add(rejected_speaker)
        rejected.reject()
        event.queued_mails.all().delete()
    client.force_login(orga_user)

    confirm_response = client.get(event.orga_urls.reviews + "regenerate/")
    response = client.post(event.orga_urls.reviews + "regenerate/", follow=True)

    assert confirm_response.status_code == 200
    assert "regenerate 2 acceptance" in confirm_response.content.decode()
    assert response.status_code == 200
    with scopes_disabled():
        assert event.queued_mails.filter(state=QueuedMailStates.DRAFT).count() == 2


def test_regenerate_decision_mails_denied_for_reviewer(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event, can_change_event_settings=True)
        event.review_phases.filter(is_active=True).update(
            can_change_submission_state=True
        )
        accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        accepted.speakers.add(SpeakerFactory(event=event))
        event.queued_mails.all().delete()
    client.force_login(reviewer)

    response = client.post(event.orga_urls.reviews + "regenerate/", follow=True)

    assert response.status_code == 404
    with scopes_disabled():
        assert event.queued_mails.count() == 0


def test_review_assignment(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
    client.force_login(orga_user)
    submission_url = event.orga_urls.reviews + "assign/?direction=submission"
    reviewer_url = event.orga_urls.reviews + "assign/?direction=reviewer"
    assert _assigned_count(submission) == 0

    response = client.get(event.orga_urls.reviews + "assign/import")
    assert response.status_code == 200
    content = response.content.decode()
    assert 'name="import_file"' in content
    assert 'name="direction"' in content

    response = client.post(
        submission_url, {f"submission-{submission.code}": [reviewer.id]}
    )
    assert response.status_code == 302
    assert _assigned_count(submission) == 1

    response = client.post(
        submission_url, {"_field": submission.code}, HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 204
    assert _assigned_count(submission) == 0

    response = client.post(reviewer_url, {f"reviewer-{reviewer.code}": [submission.id]})
    assert response.status_code == 302
    assert _assigned_count(submission) == 1

    response = client.post(
        submission_url, {"_field": submission.code}, HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 204
    assert _assigned_count(submission) == 0

    response = client.post(
        submission_url,
        {"_field": submission.code, f"submission-{submission.code}": [reviewer.id]},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 204
    assert _assigned_count(submission) == 1

    response = client.post(
        submission_url, {"_field": submission.code}, HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 204
    assert _assigned_count(submission) == 0

    response = client.post(
        reviewer_url,
        {"_field": reviewer.code, f"reviewer-{reviewer.code}": [submission.id]},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 204
    assert _assigned_count(submission) == 1

    invalid = {"_field": submission.code, f"submission-{submission.code}": ["99999"]}
    response = client.post(submission_url, invalid, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    response = client.post(submission_url, invalid)
    assert response.status_code == 200
    assert _assigned_count(submission) == 1


def test_review_assignment_via_import(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        other_submission = SubmissionFactory(event=event)
        other_submission.assigned_reviewers.add(reviewer)
    client.force_login(orga_user)
    assert _assigned_count(submission) == 0
    assert _assigned_count(other_submission) == 1

    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as f:
        f.write(json.dumps({reviewer.email: [submission.code]}))
        f.seek(0)
        response = client.post(
            event.orga_urls.reviews + "assign/import",
            {"import_file": f, "replace_assignments": 0, "direction": "reviewer"},
        )
    assert response.status_code == 302
    assert _assigned_count(submission) == 1
    assert _assigned_count(other_submission) == 1
    with scopes_disabled():
        assert reviewer.assigned_reviews.count() == 2

    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as f:
        f.write(json.dumps({submission.code: [reviewer.code]}))
        f.seek(0)
        response = client.post(
            event.orga_urls.reviews + "assign/import",
            {"import_file": f, "replace_assignments": 1, "direction": "submission"},
        )
    assert response.status_code == 302
    assert _assigned_count(submission) == 1
    assert _assigned_count(other_submission) == 0
    with scopes_disabled():
        assert reviewer.assigned_reviews.count() == 1


def test_review_export(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
    client.force_login(orga_user)
    export_url = event.orga_urls.reviews + "export/"

    response = client.get(export_url)
    assert response.status_code == 200
    assert "api_buttons" in response.context

    response = client.post(export_url, {"target": "all", "export_format": "json"})
    assert response.status_code == 302
    assert response.url == export_url
    messages = list(get_messages(response.wsgi_request))
    assert [message.level for message in messages] == [message_constants.WARNING]
    assert str(messages[0]) == "No data to be exported"

    with scopes_disabled():
        ReviewFactory(submission=submission, user=reviewer, text="Good talk")
    response = client.post(
        export_url,
        {
            "target": "all",
            "score": "on",
            "text": "on",
            "created": "on",
            "user_name": "on",
            "user_email": "on",
            "submission_title": "on",
            "submission_id": "on",
            "export_format": "json",
        },
    )
    assert response.status_code == 200
    assert "Good talk" in response.content.decode()


def test_bulk_review(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        bulk_url = event.orga_urls.reviews + "bulk/"
        category = event.score_categories.first()
        old_score = category.scores.filter(value=1).first()
        new_score = category.scores.filter(value=2).first()
    client.force_login(reviewer)

    response = client.get(bulk_url)
    assert response.status_code == 200
    assert submission.title in response.content.decode()

    response = client.post(
        bulk_url, data={"_submission": "INVALID"}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 404

    response = client.post(bulk_url, data={"_submission": "NONEXISTENT"})
    assert response.status_code == 302
    assert response.url == bulk_url

    data = {
        "_submission": submission.code,
        f"{submission.code}-score_{category.id}": old_score.id,
        f"{submission.code}-text": "Bulk LGTM",
    }
    response = client.post(bulk_url, data=data, headers={"HX-Request": "true"})
    assert response.status_code == 200
    with scopes_disabled():
        review = submission.reviews.select_related("user").get()
        assert review.text == "Bulk LGTM"
        assert review.user == reviewer

    response = client.post(bulk_url, data=data, headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert _review_count(submission) == 1

    response = client.post(
        bulk_url,
        data={
            **data,
            f"{submission.code}-score_{category.id}": new_score.id,
            f"{submission.code}-text": "Revised opinion",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        review = submission.reviews.get()
        assert review.text == "Revised opinion"
        assert review.score == new_score.value

    response = client.post(
        bulk_url, data={**data, f"{submission.code}-text": "Non-HTMX review"}
    )
    assert response.status_code == 302
    assert response.url == bulk_url
    with scopes_disabled():
        review = submission.reviews.get()
        assert review.text == "Non-HTMX review"
        assert review.score == old_score.value


def test_bulk_review_validates_required_fields(client):
    event = EventFactory(
        review_settings={"text_mandatory": True}, score_category__required=True
    )
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        bulk_url = event.orga_urls.reviews + "bulk/"
    client.force_login(reviewer)
    data = {"_submission": submission.code, f"{submission.code}-text": ""}

    response = client.post(bulk_url, data=data, headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "This field is required." in response.content.decode()
    assert _review_count(submission) == 0

    response = client.post(bulk_url, data=data)
    assert response.status_code == 302
    assert response.url == bulk_url
    assert _review_count(submission) == 0


def test_bulk_tag(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        other_submission = SubmissionFactory(event=event)
        tag = TagFactory(event=event)
        tag2 = TagFactory(event=event)
    client.force_login(orga_user)
    url = event.orga_urls.reviews + "bulk-tag/"

    def tags(sub):
        with scopes_disabled():
            return set(sub.tags.all())

    for data in (
        {f"s-{submission.code}": "on", "tags": ["99999"], "action": "add"},
        {"tags": [tag.id], "action": "add"},
        {"s-NONEXIST": "on", "tags": [tag.id], "action": "add"},
    ):
        response = client.post(url, data, follow=True)
        assert response.status_code == 200
    assert tags(submission) == set()
    assert tags(other_submission) == set()

    response = client.post(
        f"{url}?next={event.orga_urls.reviews}",
        {f"s-{submission.code}": "on", "tags": [tag.id], "action": "add"},
    )
    assert response.status_code == 302
    assert response.url == event.orga_urls.reviews
    assert tags(submission) == {tag}

    response = client.post(
        url,
        {
            f"s-{submission.code}": "on",
            f"s-{other_submission.code}": "on",
            "tags": [tag.id, tag2.id],
            "action": "add",
        },
        follow=True,
    )
    assert response.status_code == 200
    assert tags(submission) == {tag, tag2}
    assert tags(other_submission) == {tag, tag2}

    response = client.post(
        url,
        {
            f"s-{submission.code}": "on",
            f"s-{other_submission.code}": "on",
            "tags": [tag.id],
            "action": "remove",
        },
        follow=True,
    )
    assert response.status_code == 200
    assert tags(submission) == {tag2}
    assert tags(other_submission) == {tag2}


def test_review_delete_post(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        review = ReviewFactory(submission=submission, user=reviewer)
        delete_url = review.urls.delete
        assert submission.reviews.count() == 1
    client.force_login(reviewer)

    confirm_response = client.get(delete_url)
    response = client.post(delete_url, follow=True)

    assert confirm_response.status_code == 200
    assert "Your review" in confirm_response.content.decode()
    assert response.status_code == 200
    with scopes_disabled():
        assert submission.reviews.count() == 0


def test_review_dashboard_post_bulk_no_permission(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(reviewer)

    response = client.post(event.orga_urls.reviews, {f"s-{submission.code}": "accept"})

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.SUBMITTED


def test_bulk_review_anonymises_title_for_restricted_reviewer(client, event):
    original_title = "Secret Project at AcmeCorp"
    redacted_title = "Redacted Title"
    speaker_name = "Jane Realname"
    with scopes_disabled():
        reviewer = _make_reviewer(event, force_hide_speaker_names=True)
        submission = SubmissionFactory(event=event, title=original_title)
        speaker = SpeakerFactory(event=event, user=None, name=speaker_name)
        submission.speakers.add(speaker)
        submission.anonymised = {"_anonymised": True, "title": redacted_title}
        submission.save(update_fields=["anonymised"])
    client.force_login(reviewer)

    response = client.get(event.orga_urls.reviews + "bulk/")

    assert response.status_code == 200
    content = response.content.decode()
    # Control: anonymisation is genuinely active (speakers column hidden).
    assert speaker_name not in content
    assert redacted_title in content
    assert original_title not in content
    assert "status-dot" not in content  # Do not indicate managed status


def test_review_page_hides_other_track_proposals_from_limited_reviewer(client, event):
    with scopes_disabled():
        in_track = TrackFactory(event=event)
        other_track = TrackFactory(event=event)
        reviewer = _make_reviewer(event)
        reviewer.teams.first().limit_tracks.add(in_track)
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, track=in_track)
        submission.speakers.add(speaker)
        visible = SubmissionFactory(
            event=event, track=in_track, title="Visible sibling proposal"
        )
        visible.speakers.add(speaker)
        hidden = SubmissionFactory(
            event=event, track=other_track, title="Hidden sibling proposal"
        )
        hidden.speakers.add(speaker)
    client.force_login(reviewer)

    response = client.get(submission.orga_urls.reviews)
    content = response.content.decode()

    assert response.status_code == 200
    assert visible.title in content
    assert hidden.title not in content
    assert hidden.orga_urls.reviews not in content


def test_review_submission_skip_for_now_session(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        other_submission = SubmissionFactory(event=event)
        other_speaker = SpeakerFactory(event=event)
        other_submission.speakers.add(other_speaker)
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews, data={"review_submit": "skip_for_now"}
    )

    assert response.status_code == 302
    with scopes_disabled():
        assert submission.reviews.count() == 0
    session = client.session
    key = f"{event.slug}_ignored_reviews"
    assert submission.pk in session[key]
