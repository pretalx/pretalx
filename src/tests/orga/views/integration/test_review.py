# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json
import tempfile

import pytest
from django_scopes import scopes_disabled

from pretalx.mail.models import QueuedMailStates
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import SubmissionStates
from pretalx.submission.models.question import QuestionRequired, QuestionVariant
from tests.factories import (
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

pytestmark = pytest.mark.integration


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


@pytest.mark.django_db
def test_review_dashboard_requires_login(client, event):
    response = client.get(event.orga_urls.reviews)

    assert response.status_code == 302
    assert "/login" in response.url


@pytest.mark.django_db
def test_review_dashboard_denied_for_unprivileged_user(client, event):
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.orga_urls.reviews)

    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_review_dashboard_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submissions = []
        for _ in range(item_count):
            sub = SubmissionFactory(event=event)
            speaker = SpeakerFactory(event=event)
            sub.speakers.add(speaker)
            submissions.append(sub)
        ReviewFactory(submission=submissions[0], user=reviewer)
    client.force_login(reviewer)

    with django_assert_num_queries(42):
        response = client.get(event.orga_urls.reviews)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(sub.title in content for sub in submissions)


@pytest.mark.django_db
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

    with django_assert_num_queries(42):
        response = client.get(event.orga_urls.reviews + "?sort=" + sort)

    assert response.status_code == 200
    assert submission.title in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_review_dashboard_with_track_limit_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        event.feature_flags["use_tracks"] = True
        event.save()
        track = TrackFactory(event=event)
        reviewer.teams.first().limit_tracks.add(track)
        tag = TagFactory(event=event)
        event.active_review_phase.can_tag_submissions = "use_tags"
        event.active_review_phase.save()
        submissions = []
        for _ in range(item_count):
            sub = SubmissionFactory(event=event)
            speaker = SpeakerFactory(event=event)
            sub.speakers.add(speaker)
            sub.tags.add(tag)
            submissions.append(sub)
        ReviewFactory(submission=submissions[0], user=reviewer)
    client.force_login(reviewer)

    with django_assert_num_queries(36):
        response = client.get(event.orga_urls.reviews)

    assert response.status_code == 200
    assert tag.tag in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("assigned", (True, False))
@pytest.mark.parametrize("item_count", (1, 3))
def test_review_submission_post_creates_review(
    client, event, django_assert_num_queries, assigned, item_count
):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        category, score = _get_category_and_score(event)
        if assigned:
            submission.assigned_reviewers.add(reviewer)
        for _ in range(item_count - 1):
            extra = SubmissionFactory(event=event)
            extra_speaker = SpeakerFactory(event=event)
            extra.speakers.add(extra_speaker)
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

    with django_assert_num_queries(40):
        response = client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 200
    assert "LGTM" in response.content.decode()


@pytest.mark.django_db
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
        data={f"score_{category.id}": score.id, "text": "LGTM", "tags": str(tag.id)},
    )

    assert response.status_code == 200
    assert str(tag.tag) in response.content.decode()
    with scopes_disabled():
        assert submission.reviews.count() == 1
        review = submission.reviews.first()
        assert review.score == 1
        assert review.text == "LGTM"
        assert submission.tags.first() == tag


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_review_submission_denied_when_unassigned_and_visibility_restricted(
    client, event
):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        category, score = _get_category_and_score(event)
        event.active_review_phase.proposal_visibility = "assigned"
        event.active_review_phase.save()
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
    )

    assert response.status_code == 404
    with scopes_disabled():
        assert submission.reviews.count() == 0

    response = client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 404


@pytest.mark.django_db
def test_review_submission_allowed_when_assigned_and_visibility_restricted(
    client, event
):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        category, score = _get_category_and_score(event)
        event.active_review_phase.proposal_visibility = "assigned"
        event.active_review_phase.save()
        submission.assigned_reviewers.add(reviewer)
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

    response = client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 200


@pytest.mark.django_db
def test_review_submission_post_with_redirect_to_next(client, event):
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

    response = client.post(
        submission.orga_urls.reviews,
        data={
            f"score_{category.id}": score.id,
            "text": "LGTM",
            "review_submit": "save_and_next",
        },
    )

    assert response.status_code == 302
    assert other_submission.code in response.url
    with scopes_disabled():
        assert submission.reviews.count() == 1


@pytest.mark.django_db
def test_review_submission_post_with_redirect_finished(client, event):
    """When all submissions are reviewed, save_and_next redirects to the dashboard."""
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        category, score = _get_category_and_score(event)
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        data={
            f"score_{category.id}": score.id,
            "text": "LGTM",
            "review_submit": "save_and_next",
        },
    )

    assert response.status_code == 302
    assert response.url == event.orga_urls.reviews
    with scopes_disabled():
        assert submission.reviews.count() == 1


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_review_submission_post_without_score_when_mandatory(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        category = event.score_categories.first()
        event.review_settings["score_mandatory"] = True
        event.save()
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": "", "text": "LGTM"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.reviews.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("action", ("skip_for_now", "abstain"))
def test_review_submission_skip_with_required_fields(client, event, action):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        category = event.score_categories.first()
        category.required = True
        category.save()
        event.review_settings["text_mandatory"] = True
        event.save()
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


@pytest.mark.django_db
def test_review_submission_post_wrong_score_rejected(client, event):
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
        data={f"score_{category.id}": "100", "text": "LGTM"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.reviews.count() == 0


@pytest.mark.django_db
def test_review_submission_post_required_question_not_answered(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        QuestionFactory(
            event=event,
            variant=QuestionVariant.STRING,
            target="reviewer",
            question_required=QuestionRequired.REQUIRED,
        )
        category, score = _get_category_and_score(event)
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.reviews.count() == 0

    response = client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 200


@pytest.mark.django_db
def test_review_submission_speaker_cannot_review_own(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        review_profile, _ = SpeakerProfile.objects.get_or_create(
            user=reviewer, event=event
        )
        submission.speakers.add(review_profile)
        submission.save()
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


@pytest.mark.django_db
def test_review_submission_cannot_review_accepted(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        submission.accept()
        category, score = _get_category_and_score(event)
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.reviews.count() == 0


@pytest.mark.django_db
def test_review_submission_edit_existing_review(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        review = ReviewFactory(submission=submission, user=reviewer, score=1)
        category = event.score_categories.first()
        new_score = category.scores.filter(value=2).first()
        count = submission.reviews.count()
        assert review.score != new_score.value
    client.force_login(reviewer)

    response = client.post(
        review.urls.base,
        follow=True,
        data={f"score_{category.id}": new_score.id, "text": "My mistake."},
    )

    assert response.status_code == 200
    with scopes_disabled():
        review.refresh_from_db()
        assert submission.reviews.count() == count
    assert review.score == new_score.value
    assert review.text == "My mistake."


@pytest.mark.django_db
def test_review_submission_cannot_edit_after_accept(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        review = ReviewFactory(submission=submission, user=reviewer, score=1)
        category = event.score_categories.first()
        new_score = category.scores.filter(value=2).first()
        submission.accept()
        assert review.score != new_score.value
    client.force_login(reviewer)

    response = client.post(
        review.urls.base,
        follow=True,
        data={f"score_{category.id}": new_score.id, "text": "My mistake."},
    )

    assert response.status_code == 200
    with scopes_disabled():
        review.refresh_from_db()
        assert submission.reviews.count() == 1
    assert review.score != new_score.value
    assert review.text != "My mistake."


@pytest.mark.django_db
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


@pytest.mark.django_db
@pytest.mark.parametrize("accepted", (False, True))
def test_review_submission_can_see_own_review(client, event, accepted):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        review = ReviewFactory(
            submission=submission, user=reviewer, text="Looks great!"
        )
        if accepted:
            submission.accept()
    client.force_login(reviewer)

    response = client.get(review.urls.base, follow=True)

    assert response.status_code == 200
    assert review.text in response.content.decode()


@pytest.mark.django_db
def test_review_submission_orga_can_see_review(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        review = ReviewFactory(submission=submission, user=reviewer)
    client.force_login(orga_user)

    response = client.get(review.urls.base, follow=True)

    assert response.status_code == 200


@pytest.mark.django_db
def test_review_submission_orga_cannot_add_review(client, event):
    """Organisers without reviewer role cannot create reviews."""
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


@pytest.mark.django_db
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
        mail_count = event.queued_mails.count()
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews,
        {
            "foo": "bar",
            f"s-{submission.code}": "accept",
            f"s-{other_submission.code}": "reject",
            f"s-{accepted.code}": "reject",
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert mail_count + 2 == event.queued_mails.count()
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.ACCEPTED
        other_submission.refresh_from_db()
        assert other_submission.state == SubmissionStates.REJECTED
        accepted.refresh_from_db()
        assert accepted.state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
def test_review_dashboard_post_bulk_only_failure(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        speaker = SpeakerFactory(event=event)
        accepted.speakers.add(speaker)
        mail_count = event.queued_mails.count()
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews, {"foo": "bar", f"s-{accepted.code}": "reject"}
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert mail_count == event.queued_mails.count()
        accepted.refresh_from_db()
        assert accepted.state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
def test_review_dashboard_post_bulk_only_success(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        mail_count = event.queued_mails.count()
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews, {"foo": "bar", f"s-{submission.code}": "reject"}
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert mail_count + 1 == event.queued_mails.count()
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.REJECTED


@pytest.mark.django_db
def test_regenerate_decision_mails_get(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
    client.force_login(orga_user)

    response = client.get(event.orga_urls.reviews + "regenerate/")

    assert response.status_code == 200


@pytest.mark.django_db
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

    response = client.post(event.orga_urls.reviews + "regenerate/", follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.queued_mails.filter(state=QueuedMailStates.DRAFT).count() == 2


@pytest.mark.django_db
def test_review_assignment_get_submission_direction(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        _make_reviewer(event)
        SubmissionFactory(event=event)
    client.force_login(orga_user)

    response = client.get(event.orga_urls.reviews + "assign/?direction=submission")

    assert response.status_code == 200


@pytest.mark.django_db
def test_review_assignment_post_reviewer_to_submission(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        assert submission.assigned_reviewers.all().count() == 0
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews + "assign/?direction=submission",
        {f"submission-{submission.code}": [reviewer.id]},
    )

    assert response.status_code == 302
    with scopes_disabled():
        assert submission.assigned_reviewers.all().count() == 1


@pytest.mark.django_db
def test_review_assignment_post_submission_to_reviewer(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        assert submission.assigned_reviewers.all().count() == 0
    client.force_login(orga_user)

    response = client.get(event.orga_urls.reviews + "assign/?direction=reviewer")
    assert response.status_code == 200

    response = client.post(
        event.orga_urls.reviews + "assign/?direction=reviewer",
        {f"reviewer-{reviewer.code}": [submission.id]},
    )

    with scopes_disabled():
        assert submission.assigned_reviewers.all().count() == 1


@pytest.mark.django_db
def test_review_assignment_via_import_reviewer_direction(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        other_submission = SubmissionFactory(event=event)
        other_submission.assigned_reviewers.add(reviewer)
        assert submission.assigned_reviewers.all().count() == 0
        assert other_submission.assigned_reviewers.all().count() == 1
        assert reviewer.assigned_reviews.all().count() == 1

    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as f:
        f.write(json.dumps({reviewer.email: [submission.code]}))
        f.seek(0)
        client.force_login(orga_user)
        response = client.post(
            event.orga_urls.reviews + "assign/import",
            {"import_file": f, "replace_assignments": 0, "direction": "reviewer"},
        )
        assert response.status_code == 302

    with scopes_disabled():
        assert submission.assigned_reviewers.all().count() == 1
        assert other_submission.assigned_reviewers.all().count() == 1
        assert reviewer.assigned_reviews.all().count() == 2


@pytest.mark.django_db
def test_review_assignment_via_import_submission_direction_replace(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        other_submission = SubmissionFactory(event=event)
        other_submission.assigned_reviewers.add(reviewer)
        assert submission.assigned_reviewers.all().count() == 0
        assert other_submission.assigned_reviewers.all().count() == 1
        assert reviewer.assigned_reviews.all().count() == 1

    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as f:
        f.write(json.dumps({submission.code: [reviewer.code]}))
        f.seek(0)
        client.force_login(orga_user)
        response = client.post(
            event.orga_urls.reviews + "assign/import",
            {"import_file": f, "replace_assignments": 1, "direction": "submission"},
        )
        assert response.status_code == 302

    with scopes_disabled():
        assert submission.assigned_reviewers.all().count() == 1
        assert other_submission.assigned_reviewers.all().count() == 0
        assert reviewer.assigned_reviews.all().count() == 1


@pytest.mark.django_db
def test_review_assignment_htmx_reviewer_to_submission(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        assert submission.assigned_reviewers.all().count() == 0
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews + "assign/?direction=submission",
        {"_field": submission.code, f"submission-{submission.code}": [reviewer.id]},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert submission.assigned_reviewers.all().count() == 1


@pytest.mark.django_db
def test_review_assignment_htmx_submission_to_reviewer(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        assert submission.assigned_reviewers.all().count() == 0
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews + "assign/?direction=reviewer",
        {"_field": reviewer.code, f"reviewer-{reviewer.code}": [submission.id]},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert submission.assigned_reviewers.all().count() == 1


@pytest.mark.django_db
def test_review_assignment_htmx_clear(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        submission.assigned_reviewers.add(reviewer)
        assert submission.assigned_reviewers.all().count() == 1
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews + "assign/?direction=submission",
        {"_field": submission.code},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert submission.assigned_reviewers.all().count() == 0


@pytest.mark.django_db
def test_review_export_get(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        ReviewFactory(submission=submission, user=reviewer, text="Good talk")
    client.force_login(orga_user)

    response = client.get(event.orga_urls.reviews + "export/")

    assert response.status_code == 200


@pytest.mark.django_db
def test_review_export_post_json(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        review = ReviewFactory(submission=submission, user=reviewer, text="Good talk")
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews + "export/",
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
    assert review.text in response.content.decode()


@pytest.mark.django_db
def test_bulk_review_htmx_post_creates_review(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        bulk_url = event.orga_urls.reviews + "bulk/"
        category, score = _get_category_and_score(event)
    client.force_login(reviewer)

    response = client.post(
        bulk_url,
        data={
            "_submission": submission.code,
            f"{submission.code}-score_{category.id}": score.id,
            f"{submission.code}-text": "Bulk LGTM",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "btn-outline-success" in response.content.decode()
    with scopes_disabled():
        assert submission.reviews.count() == 1
        review = submission.reviews.first()
        assert review.text == "Bulk LGTM"
        assert review.user == reviewer


@pytest.mark.django_db
def test_bulk_review_htmx_invalid_submission(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        bulk_url = event.orga_urls.reviews + "bulk/"
    client.force_login(reviewer)

    response = client.post(
        bulk_url, data={"_submission": "INVALID"}, headers={"HX-Request": "true"}
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_bulk_review_htmx_validates_required_fields(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        bulk_url = event.orga_urls.reviews + "bulk/"
        category = event.score_categories.first()
        category.required = True
        category.save()
        event.review_settings["text_mandatory"] = True
        event.save()
    client.force_login(reviewer)

    response = client.post(
        bulk_url,
        data={"_submission": submission.code, f"{submission.code}-text": ""},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "btn-danger" in response.content.decode()
    with scopes_disabled():
        assert submission.reviews.count() == 0


@pytest.mark.django_db
def test_bulk_review_without_htmx(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        bulk_url = event.orga_urls.reviews + "bulk/"
        category, score = _get_category_and_score(event)
    client.force_login(reviewer)

    response = client.post(
        bulk_url,
        data={
            "_submission": submission.code,
            f"{submission.code}-score_{category.id}": score.id,
            f"{submission.code}-text": "Non-HTMX review",
        },
    )

    assert response.status_code == 302
    assert response.url == bulk_url
    with scopes_disabled():
        assert submission.reviews.count() == 1
        assert submission.reviews.first().text == "Non-HTMX review"


@pytest.mark.django_db
def test_bulk_review_update_existing(client, event):
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

    client.post(
        bulk_url,
        data={
            "_submission": submission.code,
            f"{submission.code}-score_{category.id}": old_score.id,
            f"{submission.code}-text": "First pass",
        },
        headers={"HX-Request": "true"},
    )
    with scopes_disabled():
        assert submission.reviews.count() == 1

    response = client.post(
        bulk_url,
        data={
            "_submission": submission.code,
            f"{submission.code}-score_{category.id}": new_score.id,
            f"{submission.code}-text": "Revised opinion",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "btn-outline-success" in response.content.decode()
    with scopes_disabled():
        assert submission.reviews.count() == 1
        review = submission.reviews.first()
        assert review.text == "Revised opinion"
        assert review.score == new_score.value


@pytest.mark.django_db
def test_bulk_tag_add_and_remove(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        other_submission = SubmissionFactory(event=event)
        tag = TagFactory(event=event)
        tag2 = TagFactory(event=event)
        assert submission.tags.count() == 0
        assert other_submission.tags.count() == 0
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews + "bulk-tag/",
        {
            f"s-{submission.code}": "on",
            f"s-{other_submission.code}": "on",
            "tags": [tag.id, tag2.id],
            "action": "add",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        other_submission.refresh_from_db()
        assert submission.tags.count() == 2
        assert set(submission.tags.all()) == {tag, tag2}
        assert other_submission.tags.count() == 2
        assert set(other_submission.tags.all()) == {tag, tag2}

    response = client.post(
        event.orga_urls.reviews + "bulk-tag/",
        {
            f"s-{submission.code}": "on",
            f"s-{other_submission.code}": "on",
            "tags": [tag.id],
            "action": "remove",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        other_submission.refresh_from_db()
        assert submission.tags.count() == 1
        assert submission.tags.first() == tag2
        assert other_submission.tags.count() == 1
        assert other_submission.tags.first() == tag2


@pytest.mark.django_db
def test_bulk_tag_no_submissions_selected(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        tag = TagFactory(event=event)
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews + "bulk-tag/",
        {"tags": [tag.id], "action": "add"},
        follow=True,
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_bulk_tag_denied_for_reviewer(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
    client.force_login(reviewer)

    response = client.get(event.orga_urls.reviews + "bulk-tag/")

    assert response.status_code == 404


@pytest.mark.django_db
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

    response = client.post(delete_url, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.reviews.count() == 0


@pytest.mark.django_db
def test_review_delete_get_shows_confirmation(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        review = ReviewFactory(submission=submission, user=reviewer)
    client.force_login(reviewer)

    response = client.get(review.urls.delete)

    assert response.status_code == 200


@pytest.mark.django_db
def test_review_dashboard_post_bulk_accept_with_pending(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        other_submission = SubmissionFactory(event=event)
        other_speaker = SpeakerFactory(event=event)
        other_submission.speakers.add(other_speaker)
        mail_count = event.queued_mails.count()
    client.force_login(orga_user)

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
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.SUBMITTED
        assert submission.pending_state == SubmissionStates.ACCEPTED
        other_submission.refresh_from_db()
        assert other_submission.state == SubmissionStates.SUBMITTED
        assert other_submission.pending_state == SubmissionStates.REJECTED


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_review_dashboard_with_tags_filter(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        tag = TagFactory(event=event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        submission.tags.add(tag)
    client.force_login(reviewer)

    response = client.get(event.orga_urls.reviews + f"?tags={tag.pk}")

    assert response.status_code == 200


@pytest.mark.django_db
def test_bulk_review_get(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(reviewer)

    response = client.get(event.orga_urls.reviews + "bulk/")

    assert response.status_code == 200
    content = response.content.decode()
    assert submission.title in content


@pytest.mark.django_db
def test_bulk_review_non_htmx_invalid_submission(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        bulk_url = event.orga_urls.reviews + "bulk/"
    client.force_login(reviewer)

    response = client.post(bulk_url, data={"_submission": "NONEXISTENT"})

    assert response.status_code == 302
    assert response.url == bulk_url


@pytest.mark.django_db
def test_bulk_review_non_htmx_invalid_form(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        bulk_url = event.orga_urls.reviews + "bulk/"
        category = event.score_categories.first()
        category.required = True
        category.save()
        event.review_settings["text_mandatory"] = True
        event.save()
    client.force_login(reviewer)

    response = client.post(
        bulk_url, data={"_submission": submission.code, f"{submission.code}-text": ""}
    )

    assert response.status_code == 302
    assert response.url == bulk_url
    with scopes_disabled():
        assert submission.reviews.count() == 0


@pytest.mark.django_db
def test_bulk_tag_invalid_form(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews + "bulk-tag/",
        {f"s-{submission.code}": "on", "action": "add"},
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_bulk_tag_with_next_url(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        tag = TagFactory(event=event)
    client.force_login(orga_user)
    next_url = event.orga_urls.reviews

    response = client.post(
        event.orga_urls.reviews + f"bulk-tag/?next={next_url}",
        {f"s-{submission.code}": "on", "tags": [tag.id], "action": "add"},
    )

    assert response.status_code == 302
    assert response.url == next_url
    with scopes_disabled():
        assert tag in submission.tags.all()


@pytest.mark.django_db
def test_review_submission_post_with_invalid_tags(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        TagFactory(event=event)
        event.active_review_phase.can_tag_submissions = "use_tags"
        event.active_review_phase.save()
        category, score = _get_category_and_score(event)
    client.force_login(reviewer)

    response = client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM", "tags": "99999"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.reviews.count() == 0


@pytest.mark.django_db
def test_review_assignment_htmx_form_invalid(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        _make_reviewer(event)
        submission = SubmissionFactory(event=event)
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews + "assign/?direction=submission",
        {"_field": submission.code, f"submission-{submission.code}": ["99999"]},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_review_export_post_no_data(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews + "export/", {"target": "all", "export_format": "json"}
    )

    assert response.status_code == 302
    assert response.url == event.orga_urls.reviews + "export/"


@pytest.mark.django_db
def test_bulk_review_get_with_track_categories(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        event.feature_flags["use_tracks"] = True
        event.save()
        track = TrackFactory(event=event)
        category = event.score_categories.first()
        category.limit_tracks.add(track)
        submission = SubmissionFactory(event=event, track=track)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(reviewer)

    response = client.get(event.orga_urls.reviews + "bulk/")

    assert response.status_code == 200


@pytest.mark.django_db
def test_review_dashboard_with_tracks_and_types(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        event.feature_flags["use_tracks"] = True
        event.save()
        TrackFactory(event=event)
        TrackFactory(event=event)
        SubmissionTypeFactory(event=event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(reviewer)

    response = client.get(event.orga_urls.reviews)

    assert response.status_code == 200


@pytest.mark.django_db
def test_review_assignment_non_htmx_form_invalid(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_event_settings=True)
        _make_reviewer(event)
        submission = SubmissionFactory(event=event)
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews + "assign/?direction=submission",
        {f"submission-{submission.code}": ["99999"]},
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_bulk_tag_remove_with_submissions(client, event):
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        tag = TagFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.tags.add(tag)
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews + "bulk-tag/",
        {f"s-{submission.code}": "on", "tags": [tag.id], "action": "remove"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.tags.count() == 0


@pytest.mark.django_db
def test_review_dashboard_filter_range_zero_min(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(reviewer)

    response = client.get(event.orga_urls.reviews + "?review-count=0,")

    assert response.status_code == 200


@pytest.mark.django_db
def test_bulk_review_htmx_resubmit_unchanged(client, event):
    """Bulk review POST with unchanged data still returns saved state."""
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        bulk_url = event.orga_urls.reviews + "bulk/"
        category, score = _get_category_and_score(event)
    client.force_login(reviewer)

    client.post(
        bulk_url,
        data={
            "_submission": submission.code,
            f"{submission.code}-score_{category.id}": score.id,
            f"{submission.code}-text": "Review text",
        },
        headers={"HX-Request": "true"},
    )

    response = client.post(
        bulk_url,
        data={
            "_submission": submission.code,
            f"{submission.code}-score_{category.id}": score.id,
            f"{submission.code}-text": "Review text",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "btn-outline-success" in response.content.decode()
    with scopes_disabled():
        assert submission.reviews.count() == 1


@pytest.mark.django_db
def test_bulk_review_non_htmx_unchanged(client, event):
    """Bulk review non-HTMX POST with unchanged data redirects with success."""
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        bulk_url = event.orga_urls.reviews + "bulk/"
        category, score = _get_category_and_score(event)
    client.force_login(reviewer)

    client.post(
        bulk_url,
        data={
            "_submission": submission.code,
            f"{submission.code}-score_{category.id}": score.id,
            f"{submission.code}-text": "Review text",
        },
        headers={"HX-Request": "true"},
    )

    response = client.post(
        bulk_url,
        data={
            "_submission": submission.code,
            f"{submission.code}-score_{category.id}": score.id,
            f"{submission.code}-text": "Review text",
        },
    )

    assert response.status_code == 302
    assert response.url == bulk_url


@pytest.mark.django_db
def test_bulk_tag_nonexistent_submission_codes(client, event):
    """When selected submission codes don't match any submissions, count stays 0."""
    with scopes_disabled():
        orga_user = make_orga_user(event, can_change_submissions=True)
        tag = TagFactory(event=event)
    client.force_login(orga_user)

    response = client.post(
        event.orga_urls.reviews + "bulk-tag/",
        {"s-NONEXISTENT": "on", "tags": [tag.id], "action": "add"},
        follow=True,
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_bulk_review_get_with_filter(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(reviewer)

    response = client.get(event.orga_urls.reviews + "bulk/?filter-state=submitted")

    assert response.status_code == 200


@pytest.mark.django_db
def test_bulk_review_get_with_invalid_filter(client, event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(reviewer)

    response = client.get(event.orga_urls.reviews + "bulk/?filter-state=INVALID_STATE")

    assert response.status_code == 200


@pytest.mark.django_db
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
