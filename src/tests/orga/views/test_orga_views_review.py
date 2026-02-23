# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json
import tempfile

import pytest
from django_scopes import scope

from pretalx.mail.models import QueuedMailStates
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import Submission
from pretalx.submission.models.question import QuestionRequired


@pytest.mark.parametrize("assigned", (True, False))
@pytest.mark.parametrize("item_count", (1, 2))
@pytest.mark.django_db
def test_reviewer_can_add_review(
    review_client,
    review_user,
    submission,
    speaker_profile,
    django_assert_num_queries,
    assigned,
    item_count,
):
    with scope(event=submission.event):
        category = submission.event.score_categories.first()
        score = category.scores.filter(value=1).first()
        if assigned:
            submission.assigned_reviewers.add(review_user)
        if item_count == 2:
            second = Submission.objects.create(
                title="Second Talk",
                event=submission.event,
                submission_type=submission.event.cfp.default_type,
                content_locale="en",
            )
            second.speakers.add(speaker_profile)
    response = review_client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
    )
    assert response.status_code == 200
    with scope(event=submission.event):
        assert submission.reviews.count() == 1
        assert submission.reviews.first().score == 1
        assert submission.reviews.first().text == "LGTM"
    with django_assert_num_queries(40):
        response = review_client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 200
    if item_count == 2:
        assert "Second Talk" in response.text


@pytest.mark.django_db
def test_reviewer_can_add_review_with_tags(review_client, review_user, submission, tag):
    with scope(event=submission.event):
        submission.event.active_review_phase.can_tag_submissions = "use_tags"
        submission.event.active_review_phase.save()
        assert not submission.tags.count()
        category = submission.event.score_categories.first()
        score = category.scores.filter(value=1).first()
    response = review_client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM", "tags": str(tag.id)},
    )
    assert response.status_code == 200
    assert str(tag.tag) in response.text
    with scope(event=submission.event):
        assert submission.reviews.count() == 1
        assert submission.reviews.first().score == 1
        assert submission.reviews.first().text == "LGTM"
        assert submission.tags.first() == tag


@pytest.mark.django_db
def test_reviewer_cannot_tag_when_tagging_disabled(
    review_client, review_user, submission, tag
):
    with scope(event=submission.event):
        assert submission.event.active_review_phase.can_tag_submissions == "never"
        assert not submission.tags.count()
        category = submission.event.score_categories.first()
        score = category.scores.filter(value=1).first()
    response = review_client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM", "tags": str(tag.id)},
    )
    assert response.status_code == 200
    with scope(event=submission.event):
        assert submission.reviews.count() == 1
        assert submission.tags.count() == 0


@pytest.mark.django_db
def test_reviewer_cannot_add_review_when_unassigned(review_client, submission):
    with scope(event=submission.event):
        category = submission.event.score_categories.first()
        score = category.scores.filter(value=1).first()
        submission.event.active_review_phase.proposal_visibility = "assigned"
        submission.event.active_review_phase.save()
    response = review_client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
    )
    assert response.status_code == 404
    with scope(event=submission.event):
        assert submission.reviews.count() == 0
    response = review_client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 404


@pytest.mark.django_db
def test_reviewer_can_add_review_when_assigned(review_client, review_user, submission):
    with scope(event=submission.event):
        category = submission.event.score_categories.first()
        score = category.scores.filter(value=1).first()
        submission.event.active_review_phase.proposal_visibility = "assigned"
        submission.event.active_review_phase.save()
        submission.assigned_reviewers.add(review_user)
    response = review_client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
    )
    assert response.status_code == 200
    with scope(event=submission.event):
        assert submission.reviews.count() == 1
        assert submission.reviews.first().score == 1
        assert submission.reviews.first().text == "LGTM"
    response = review_client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 200


@pytest.mark.django_db
def test_reviewer_can_add_review_with_redirect(
    review_client, submission, other_submission
):
    with scope(event=submission.event):
        category = submission.event.score_categories.first()
        score = category.scores.filter(value=1).first()
    response = review_client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM", "show_next": "1"},
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_reviewer_can_add_review_with_redirect_finished(review_client, submission):
    with scope(event=submission.event):
        category = submission.event.score_categories.first()
        score = category.scores.filter(value=1).first()
    response = review_client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM", "show_next": "1"},
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_reviewer_can_add_review_without_score(review_client, submission):
    with scope(event=submission.event):
        category = submission.event.score_categories.first()
    response = review_client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": "", "text": "LGTM"},
    )
    assert response.status_code == 200
    with scope(event=submission.event):
        assert submission.reviews.count() == 1
        assert submission.reviews.first().score is None
        assert submission.reviews.first().text == "LGTM"
    response = review_client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 200


@pytest.mark.django_db
def test_reviewer_cannot_add_review_without_score_when_mandatory(
    review_client, submission
):
    with scope(event=submission.event):
        category = submission.event.score_categories.first()
        submission.event.review_settings["score_mandatory"] = True
        submission.event.save()
    response = review_client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": "", "text": "LGTM"},
    )
    assert response.status_code == 200
    with scope(event=submission.event):
        assert submission.reviews.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("action", ("skip_for_now", "abstain"))
def test_reviewer_can_skip_review_with_required_fields(
    review_client, submission, action
):
    with scope(event=submission.event):
        category = submission.event.score_categories.first()
        category.required = True
        category.save()
        submission.event.review_settings["text_mandatory"] = True
        submission.event.save()
    response = review_client.post(
        submission.orga_urls.reviews,
        data={f"score_{category.id}": "", "text": "", "review_submit": action},
    )
    assert response.status_code == 302
    with scope(event=submission.event):
        if action == "abstain":
            assert submission.reviews.count() == 1
            assert submission.reviews.first().score is None
        else:
            assert submission.reviews.count() == 0


@pytest.mark.django_db
def test_reviewer_cannot_use_wrong_score(review_client, submission):
    with scope(event=submission.event):
        category = submission.event.score_categories.first()
    response = review_client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": "100", "text": "LGTM"},
    )
    assert response.status_code == 200
    with scope(event=submission.event):
        assert submission.reviews.count() == 0


@pytest.mark.django_db
def test_reviewer_cannot_ignore_required_question(
    review_client, submission, review_question
):
    with scope(event=submission.event):
        category = submission.event.score_categories.first()
        score = category.scores.filter(value=1).first()
        review_question.question_required = QuestionRequired.REQUIRED
        review_question.save()
    response = review_client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
    )
    assert response.status_code == 200
    with scope(event=submission.event):
        assert submission.reviews.count() == 0
    response = review_client.get(submission.orga_urls.reviews, follow=True)
    assert response.status_code == 200


@pytest.mark.django_db
def test_reviewer_cannot_review_own_submission(review_user, review_client, submission):
    with scope(event=submission.event):
        category = submission.event.score_categories.first()
        score = category.scores.filter(value=1).first()
        review_profile, _ = SpeakerProfile.objects.get_or_create(
            user=review_user, event=submission.event
        )
        submission.speakers.add(review_profile)
        submission.save()
        assert submission.reviews.count() == 0
    response = review_client.post(
        submission.orga_urls.reviews,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
    )
    assert response.status_code == 200, response.text
    with scope(event=submission.event):
        assert submission.reviews.count() == 0


@pytest.mark.django_db
def test_reviewer_cannot_review_accepted_submission(
    review_user, review_client, submission
):
    with scope(event=submission.event):
        category = submission.event.score_categories.first()
        score = category.scores.filter(value=1).first()
        submission.accept()
    response = review_client.post(
        submission.orga_urls.reviews,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=submission.event):
        assert submission.reviews.count() == 0


@pytest.mark.django_db
def test_reviewer_can_edit_review(review_client, review, review_user):
    with scope(event=review.event):
        category = review.event.score_categories.first()
        score = category.scores.filter(value=2).first()
        count = review.submission.reviews.count()
        assert review.score != score.value
        assert review.user == review_user
    response = review_client.post(
        review.urls.base,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "My mistake."},
    )
    assert response.status_code == 200
    with scope(event=review.event):
        review.refresh_from_db()
        assert review.submission.reviews.count() == count
    assert review.score == score.value
    assert review.text == "My mistake."


@pytest.mark.django_db
def test_reviewer_cannot_edit_review_after_accept(review_client, review):
    with scope(event=review.event):
        category = review.event.score_categories.first()
        score = category.scores.filter(value=2).first()
        review.submission.accept()
        assert review.score != score.value
    response = review_client.post(
        review.urls.base,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "My mistake."},
    )
    assert response.status_code == 200
    with scope(event=review.event):
        review.refresh_from_db()
        assert review.submission.reviews.count() == 1
    assert review.score != score.value
    assert review.text != "My mistake."


@pytest.mark.django_db
def test_cannot_see_other_review_before_own(other_review_client, review):
    with scope(event=review.event):
        category = review.event.score_categories.first()
        score = category.scores.filter(value=1).first()

    response = other_review_client.get(review.urls.base, follow=True)
    assert response.status_code == 200
    assert review.text not in response.text

    response = other_review_client.post(
        review.urls.base,
        follow=True,
        data={
            f"score_{category.id}": score.id,
            "text": "My mistake.",
            "review_submit": "save",
        },
    )
    assert response.status_code == 200
    with scope(event=review.event):
        review.refresh_from_db()
        assert review.submission.reviews.count() == 2
    assert review.score != 0
    assert review.text != "My mistake."
    assert review.text in response.text
    assert "My mistake" in response.text


@pytest.mark.django_db
def test_can_see_review(review_client, review):
    response = review_client.get(review.urls.base, follow=True)
    assert response.status_code == 200
    assert review.text in response.text


@pytest.mark.django_db
def test_can_see_review_after_accept(review_client, review):
    with scope(event=review.event):
        review.submission.accept()
    response = review_client.get(review.urls.base, follow=True)
    assert response.status_code == 200
    assert review.text in response.text


@pytest.mark.django_db
def test_orga_can_see_review(orga_client, review):
    response = orga_client.get(review.urls.base, follow=True)
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("sort", ("count", "-count", "score", "-score"))
def test_reviewer_can_see_dashboard(
    review_client, submission, review, sort, django_assert_num_queries, other_submission
):
    with django_assert_num_queries(43):
        response = review_client.get(
            submission.event.orga_urls.reviews + "?sort=" + sort
        )
    assert response.status_code == 200


@pytest.mark.django_db
def test_reviewer_with_track_limit_can_see_dashboard(
    review_client,
    review_user,
    track,
    submission,
    review,
    django_assert_num_queries,
    other_submission,
    tag,
):
    review_user.teams.first().limit_tracks.add(track)
    with scope(event=submission.event):
        submission.event.active_review_phase.can_tag_submissions = "use_tags"
        submission.event.active_review_phase.save()
        submission.tags.add(tag)
    with django_assert_num_queries(37):
        response = review_client.get(submission.event.orga_urls.reviews)
    assert response.status_code == 200
    assert tag.tag in response.text


@pytest.mark.django_db
def test_orga_cannot_add_review(orga_client, submission):
    with scope(event=submission.event):
        category = submission.event.score_categories.first()
        score = category.scores.filter(value=1).first()
    response = orga_client.post(
        submission.orga_urls.reviews,
        follow=True,
        data={f"score_{category.id}": score.id, "text": "LGTM"},
    )
    assert response.status_code == 200
    with scope(event=submission.event):
        assert submission.reviews.count() == 0


@pytest.mark.django_db
def test_orga_can_regenerate_emails(
    orga_client, submission, accepted_submission, rejected_submission, event
):
    with scope(event=event):
        event.queued_mails.all().delete()
    response = orga_client.get(event.orga_urls.reviews + "regenerate/")
    assert response.status_code == 200

    response = orga_client.post(event.orga_urls.reviews + "regenerate/", follow=True)
    assert response.status_code == 200

    with scope(event=event):
        assert (
            event.queued_mails.filter(state=QueuedMailStates.DRAFT).count() == 2
        )  # One for the accepted, one for the rejected, none for the submitted


@pytest.mark.django_db
def test_orga_can_bulk_accept_and_reject(
    orga_client, submission, other_submission, accepted_submission
):
    with scope(event=submission.event):
        count = submission.event.queued_mails.count()
    response = orga_client.post(
        submission.event.orga_urls.reviews,
        {
            "foo": "bar",
            f"s-{submission.code}": "accept",
            f"s-{other_submission.code}": "reject",
            f"s-{accepted_submission.code}": "reject",
        },
    )
    assert response.status_code == 200
    with scope(event=submission.event):
        assert count + 2 == submission.event.queued_mails.count()
        submission.refresh_from_db()
        assert submission.state == "accepted"
        other_submission.refresh_from_db()
        assert other_submission.state == "rejected"
        accepted_submission.refresh_from_db()
        assert accepted_submission.state == "accepted"


@pytest.mark.django_db
def test_orga_can_bulk_accept_and_reject_only_failure(orga_client, accepted_submission):
    with scope(event=accepted_submission.event):
        count = accepted_submission.event.queued_mails.count()
    response = orga_client.post(
        accepted_submission.event.orga_urls.reviews,
        {"foo": "bar", f"s-{accepted_submission.code}": "reject"},
    )
    assert response.status_code == 200
    with scope(event=accepted_submission.event):
        assert count == accepted_submission.event.queued_mails.count()
        accepted_submission.refresh_from_db()
        assert accepted_submission.state == "accepted"


@pytest.mark.django_db
def test_orga_can_bulk_accept_and_reject_only_success(orga_client, submission):
    with scope(event=submission.event):
        count = submission.event.queued_mails.count()
    response = orga_client.post(
        submission.event.orga_urls.reviews,
        {"foo": "bar", f"s-{submission.code}": "reject"},
    )
    assert response.status_code == 200
    with scope(event=submission.event):
        assert count + 1 == submission.event.queued_mails.count()
        submission.refresh_from_db()
        assert submission.state == "rejected"


@pytest.mark.django_db
def test_orga_can_assign_reviewer_to_submission(orga_client, review_user, submission):
    with scope(event=submission.event):
        assert submission.assigned_reviewers.all().count() == 0
    response = orga_client.get(
        submission.event.orga_urls.reviews + "assign/?direction=submission"
    )
    assert response.status_code == 200
    response = orga_client.post(
        submission.event.orga_urls.reviews + "assign/?direction=submission",
        {f"submission-{submission.code}": [review_user.id]},
    )
    with scope(event=submission.event):
        assert submission.assigned_reviewers.all().count() == 1


@pytest.mark.django_db
def test_orga_can_assign_reviewer_to_submission_via_import(
    orga_client, review_user, submission, other_submission
):
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as f:
        f.write(json.dumps({review_user.email: [submission.code]}))
        f.seek(0)
        with scope(event=submission.event):
            other_submission.assigned_reviewers.add(review_user)
            assert submission.assigned_reviewers.all().count() == 0
            assert other_submission.assigned_reviewers.all().count() == 1
            assert review_user.assigned_reviews.all().count() == 1
        response = orga_client.post(
            submission.event.orga_urls.reviews + "assign/import",
            {"import_file": f, "replace_assignments": 0, "direction": "reviewer"},
        )
        assert response.status_code == 302
    with scope(event=submission.event):
        assert submission.assigned_reviewers.all().count() == 1
        assert other_submission.assigned_reviewers.all().count() == 1
        assert review_user.assigned_reviews.all().count() == 2


@pytest.mark.django_db
def test_orga_can_assign_submission_to_reviewer_via_import_and_replace(
    orga_client, review_user, submission, other_submission
):
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as f:
        f.write(json.dumps({submission.code: [review_user.code]}))
        f.seek(0)
        with scope(event=submission.event):
            other_submission.assigned_reviewers.add(review_user)
            assert submission.assigned_reviewers.all().count() == 0
            assert other_submission.assigned_reviewers.all().count() == 1
            assert review_user.assigned_reviews.all().count() == 1
        response = orga_client.post(
            submission.event.orga_urls.reviews + "assign/import",
            {"import_file": f, "replace_assignments": 1, "direction": "submission"},
        )
        assert response.status_code == 302
    with scope(event=submission.event):
        assert submission.assigned_reviewers.all().count() == 1
        assert other_submission.assigned_reviewers.all().count() == 0
        assert review_user.assigned_reviews.all().count() == 1


@pytest.mark.django_db
def test_orga_can_assign_submission_to_reviewer(orga_client, review_user, submission):
    with scope(event=submission.event):
        assert submission.assigned_reviewers.all().count() == 0
    response = orga_client.get(
        submission.event.orga_urls.reviews + "assign/?direction=reviewer"
    )
    assert response.status_code == 200
    response = orga_client.post(
        submission.event.orga_urls.reviews + "assign/?direction=reviewer",
        {f"reviewer-{review_user.code}": [submission.id]},
    )
    with scope(event=submission.event):
        assert submission.assigned_reviewers.all().count() == 1


@pytest.mark.django_db
def test_orga_can_assign_reviewer_to_submission_htmx(
    orga_client, review_user, submission
):
    with scope(event=submission.event):
        assert submission.assigned_reviewers.all().count() == 0
    response = orga_client.post(
        submission.event.orga_urls.reviews + "assign/?direction=submission",
        {"_field": submission.code, f"submission-{submission.code}": [review_user.id]},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 204
    with scope(event=submission.event):
        assert submission.assigned_reviewers.all().count() == 1


@pytest.mark.django_db
def test_orga_can_assign_submission_to_reviewer_htmx(
    orga_client, review_user, submission
):
    with scope(event=submission.event):
        assert submission.assigned_reviewers.all().count() == 0
    response = orga_client.post(
        submission.event.orga_urls.reviews + "assign/?direction=reviewer",
        {"_field": review_user.code, f"reviewer-{review_user.code}": [submission.id]},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 204
    with scope(event=submission.event):
        assert submission.assigned_reviewers.all().count() == 1


@pytest.mark.django_db
def test_orga_can_clear_assignment_htmx(orga_client, review_user, submission):
    with scope(event=submission.event):
        submission.assigned_reviewers.add(review_user)
        assert submission.assigned_reviewers.all().count() == 1
    response = orga_client.post(
        submission.event.orga_urls.reviews + "assign/?direction=submission",
        {"_field": submission.code},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 204
    with scope(event=submission.event):
        assert submission.assigned_reviewers.all().count() == 0


@pytest.mark.django_db
def test_orga_can_export_reviews(review, orga_client):
    response = orga_client.get(review.event.orga_urls.reviews + "export/")
    assert response.status_code == 200

    response = orga_client.post(
        review.event.orga_urls.reviews + "export/",
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
    assert review.text in response.text


@pytest.mark.django_db
def test_reviewer_can_bulk_review_via_htmx(review_client, review_user, submission):
    with scope(event=submission.event):
        bulk_url = submission.event.orga_urls.reviews + "bulk/"
        category = submission.event.score_categories.first()
        score = category.scores.filter(value=1).first()

    response = review_client.post(
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
    with scope(event=submission.event):
        assert submission.reviews.count() == 1
        review = submission.reviews.first()
        assert review.text == "Bulk LGTM"
        assert review.user == review_user


@pytest.mark.django_db
def test_reviewer_bulk_review_htmx_invalid_submission(review_client, submission):
    with scope(event=submission.event):
        bulk_url = submission.event.orga_urls.reviews + "bulk/"

    response = review_client.post(
        bulk_url, data={"_submission": "INVALID"}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_reviewer_bulk_review_htmx_validates_required_fields(
    review_client, review_user, submission
):
    with scope(event=submission.event):
        bulk_url = submission.event.orga_urls.reviews + "bulk/"
        category = submission.event.score_categories.first()
        category.required = True
        category.save()
        submission.event.review_settings["text_mandatory"] = True
        submission.event.save()

    response = review_client.post(
        bulk_url,
        data={"_submission": submission.code, f"{submission.code}-text": ""},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "btn-danger" in response.content.decode()
    with scope(event=submission.event):
        assert submission.reviews.count() == 0


@pytest.mark.django_db
def test_reviewer_can_bulk_review_without_htmx(review_client, review_user, submission):
    with scope(event=submission.event):
        bulk_url = submission.event.orga_urls.reviews + "bulk/"
        category = submission.event.score_categories.first()
        score = category.scores.filter(value=1).first()

    response = review_client.post(
        bulk_url,
        data={
            "_submission": submission.code,
            f"{submission.code}-score_{category.id}": score.id,
            f"{submission.code}-text": "Non-HTMX review",
        },
    )
    assert response.status_code == 302
    assert response.url == bulk_url
    with scope(event=submission.event):
        assert submission.reviews.count() == 1
        assert submission.reviews.first().text == "Non-HTMX review"


@pytest.mark.django_db
def test_reviewer_can_update_existing_bulk_review(
    review_client, review_user, submission
):
    with scope(event=submission.event):
        bulk_url = submission.event.orga_urls.reviews + "bulk/"
        category = submission.event.score_categories.first()
        old_score = category.scores.filter(value=1).first()
        new_score = category.scores.filter(value=2).first()

    # Create the initial review
    review_client.post(
        bulk_url,
        data={
            "_submission": submission.code,
            f"{submission.code}-score_{category.id}": old_score.id,
            f"{submission.code}-text": "First pass",
        },
        headers={"HX-Request": "true"},
    )
    with scope(event=submission.event):
        assert submission.reviews.count() == 1

    # Update the existing review
    response = review_client.post(
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
    with scope(event=submission.event):
        assert submission.reviews.count() == 1
        review = submission.reviews.first()
        assert review.text == "Revised opinion"
        assert review.score == new_score.value


@pytest.mark.django_db
def test_orga_can_bulk_tag_submissions(
    orga_client, submission, other_submission, tag, event
):
    with scope(event=event):
        tag2 = event.tags.create(tag="anothertag", color="#ff0000")
        assert submission.tags.count() == 0
        assert other_submission.tags.count() == 0

    # Add tags to submissions
    response = orga_client.post(
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

    with scope(event=event):
        submission.refresh_from_db()
        other_submission.refresh_from_db()
        assert submission.tags.count() == 2
        assert set(submission.tags.all()) == {tag, tag2}
        assert other_submission.tags.count() == 2
        assert set(other_submission.tags.all()) == {tag, tag2}

    # Remove tags from submissions
    response = orga_client.post(
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

    with scope(event=event):
        submission.refresh_from_db()
        other_submission.refresh_from_db()
        assert submission.tags.count() == 1
        assert submission.tags.first() == tag2
        assert other_submission.tags.count() == 1
        assert other_submission.tags.first() == tag2
