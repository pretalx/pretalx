import json
from operator import attrgetter

import pytest
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django_scopes import scopes_disabled

from pretalx.orga.forms.review import (
    BulkTagForm,
    DirectionForm,
    ProposalForReviewerForm,
    ReviewAssignImportForm,
    ReviewAssignmentForm,
    ReviewerForProposalForm,
    ReviewExportForm,
    ReviewForm,
    TagsForm,
)
from pretalx.submission.models import Answer, QuestionTarget, SubmissionStates
from tests.factories import (
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    SpeakerFactory,
    SubmissionFactory,
    TagFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_tags_form_init_with_tags():
    """When the event has tags, the tags field is present with the correct queryset."""
    with scopes_disabled():
        event = EventFactory()
        tag1 = TagFactory(event=event)
        tag2 = TagFactory(event=event)
        TagFactory()  # different event, should not appear

        submission = SubmissionFactory(event=event)
        form = TagsForm(event=event, instance=submission)

    assert "tags" in form.fields
    assert set(form.fields["tags"].queryset) == {tag1, tag2}
    assert form.fields["tags"].required is False


@pytest.mark.django_db
def test_tags_form_init_without_tags():
    """When the event has no tags, the tags field is removed."""
    with scopes_disabled():
        event = EventFactory()
        submission = SubmissionFactory(event=event)

        form = TagsForm(event=event, instance=submission)

    assert "tags" not in form.fields


@pytest.mark.django_db
def test_tags_form_save():
    with scopes_disabled():
        event = EventFactory()
        tag = TagFactory(event=event)
        submission = SubmissionFactory(event=event)

        form = TagsForm(event=event, instance=submission, data={"tags": [tag.pk]})

    assert form.is_valid()
    with scopes_disabled():
        form.save()
        assert list(submission.tags.all()) == [tag]


@pytest.mark.django_db
def test_tags_form_read_only():
    """In read-only mode, all fields are disabled and clean raises an error."""
    with scopes_disabled():
        event = EventFactory()
        TagFactory(event=event)
        submission = SubmissionFactory(event=event)

        form = TagsForm(event=event, instance=submission, read_only=True, data={})

    assert form.fields["tags"].disabled is True
    assert form.is_valid() is False


def _make_review_form_context(event, *, num_categories=1, **category_kwargs):
    """Helper: create categories+scores for ReviewForm tests.

    Returns (categories, scores_by_category) where scores_by_category
    maps category → list of ReviewScore objects."""
    categories = []
    scores_by_cat = {}
    for _i in range(num_categories):
        cat = ReviewScoreCategoryFactory(event=event, **category_kwargs)
        scores = [
            ReviewScoreFactory(category=cat, value=v, label=label)
            for v, label in [(0, "No"), (1, "Maybe"), (2, "Yes")]
        ]
        categories.append(cat)
        scores_by_cat[cat] = scores
    return categories, scores_by_cat


@pytest.mark.django_db
def test_review_form_init_creates_score_fields():
    """ReviewForm creates one score field per category."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, _ = _make_review_form_context(event, num_categories=2)

        form = ReviewForm(
            event=event, user=user, categories=categories, submission=submission
        )

    for cat in categories:
        field_name = f"score_{cat.id}"
        assert field_name in form.fields
        assert isinstance(form.fields[field_name], forms.ChoiceField)


@pytest.mark.django_db
@pytest.mark.parametrize("text_mandatory", (True, False))
def test_review_form_init_text_required(text_mandatory):
    """text field required reflects event.review_settings['text_mandatory']."""
    with scopes_disabled():
        event = EventFactory()
        if text_mandatory:
            event.review_settings["text_mandatory"] = True
            event.save()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, _ = _make_review_form_context(event)

        form = ReviewForm(
            event=event, user=user, categories=categories, submission=submission
        )

    assert form.fields["text"].required is text_mandatory


@pytest.mark.django_db
def test_review_form_build_score_field_required_category():
    """Required categories don't get a 'No score' choice."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, scores = _make_review_form_context(event, required=True)
        cat = categories[0]

        form = ReviewForm(
            event=event, user=user, categories=categories, submission=submission
        )

    field = form.fields[f"score_{cat.id}"]
    assert field.required is True
    choice_values = [c[0] for c in field.choices]
    assert "-" not in choice_values
    assert len(field.choices) == 3  # Only the three score values


@pytest.mark.django_db
def test_review_form_build_score_field_optional_category():
    """Optional categories include a 'No score' ('-') choice."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, _ = _make_review_form_context(event, required=False)
        cat = categories[0]

        form = ReviewForm(
            event=event, user=user, categories=categories, submission=submission
        )

    field = form.fields[f"score_{cat.id}"]
    assert field.required is False
    choice_values = [c[0] for c in field.choices]
    assert choice_values[0] == "-"


@pytest.mark.django_db
def test_review_form_build_score_field_read_only():
    """When read_only=True, score fields are disabled."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, _ = _make_review_form_context(event)
        cat = categories[0]

        form = ReviewForm(
            event=event,
            user=user,
            categories=categories,
            submission=submission,
            read_only=True,
        )

    assert form.fields[f"score_{cat.id}"].disabled is True


@pytest.mark.django_db
def test_review_form_build_score_field_hide_optional():
    """When score_mandatory is True, score fields get the 'hide-optional' class."""
    with scopes_disabled():
        event = EventFactory()
        event.review_settings["score_mandatory"] = True
        event.save()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, _ = _make_review_form_context(event)
        cat = categories[0]

        form = ReviewForm(
            event=event, user=user, categories=categories, submission=submission
        )

    assert "hide-optional" in form.fields[f"score_{cat.id}"].widget.attrs.get(
        "class", ""
    )


@pytest.mark.django_db
def test_review_form_build_score_field_existing_review():
    """When editing an existing review, score fields get the correct initial value."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, scores = _make_review_form_context(event)
        cat = categories[0]
        review = ReviewFactory(submission=submission, user=user)
        chosen_score = scores[cat][2]  # "Yes"
        review.scores.add(chosen_score)

        form = ReviewForm(
            event=event,
            user=user,
            categories=categories,
            submission=submission,
            instance=review,
        )

    assert form.fields[f"score_{cat.id}"].initial == chosen_score.id


@pytest.mark.django_db
def test_review_form_get_score_fields():
    """get_score_fields yields bound fields for each category in order."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, _ = _make_review_form_context(event, num_categories=2)

        form = ReviewForm(
            event=event, user=user, categories=categories, submission=submission
        )

    score_fields = list(form.get_score_fields())
    assert len(score_fields) == 2
    assert score_fields[0].name == f"score_{categories[0].id}"
    assert score_fields[1].name == f"score_{categories[1].id}"


@pytest.mark.django_db
def test_review_form_get_score_field_existing():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, _ = _make_review_form_context(event)
        cat = categories[0]

        form = ReviewForm(
            event=event, user=user, categories=categories, submission=submission
        )

    field = form.get_score_field(cat)
    assert field is not None
    assert field.name == f"score_{cat.id}"


@pytest.mark.django_db
def test_review_form_get_score_field_missing():
    """get_score_field returns None for a category not in the form."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, _ = _make_review_form_context(event)
        other_cat = ReviewScoreCategoryFactory(event=event)

        form = ReviewForm(
            event=event, user=user, categories=categories, submission=submission
        )

    assert form.get_score_field(other_cat) is None


@pytest.mark.django_db
def test_review_form_clean_converts_dash_to_empty():
    """The '-' (no score) choice is converted to '' in cleaned_data."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, scores = _make_review_form_context(event, required=False)
        cat = categories[0]

        form = ReviewForm(
            event=event,
            user=user,
            categories=categories,
            submission=submission,
            data={"text": "Good talk", f"score_{cat.id}": "-"},
        )

    assert form.is_valid()
    assert form.cleaned_data[f"score_{cat.id}"] == ""


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("provide_score", "expected_valid"), ((True, True), (False, False))
)
def test_review_form_clean_score_mandatory(provide_score, expected_valid):
    """When score_mandatory is set, at least one score must be provided."""
    with scopes_disabled():
        event = EventFactory()
        event.review_settings["score_mandatory"] = True
        event.save()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, scores = _make_review_form_context(event, required=False)
        cat = categories[0]
        score_value = str(scores[cat][1].id) if provide_score else "-"

        form = ReviewForm(
            event=event,
            user=user,
            categories=categories,
            submission=submission,
            data={"text": "Good talk", f"score_{cat.id}": score_value},
        )

    assert form.is_valid() is expected_valid
    if not expected_valid:
        assert form.errors["__all__"]


@pytest.mark.django_db
def test_review_form_save_creates_review():
    """save() creates a Review with correct submission, user, and scores."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, scores = _make_review_form_context(event)
        cat = categories[0]
        chosen_score = scores[cat][2]  # "Yes"

        form = ReviewForm(
            event=event,
            user=user,
            categories=categories,
            submission=submission,
            data={"text": "Great talk!", f"score_{cat.id}": str(chosen_score.id)},
        )
        assert form.is_valid(), form.errors
        review = form.save()

    with scopes_disabled():
        assert review.submission == submission
        assert review.user == user
        assert review.text == "Great talk!"
        assert list(review.scores.all()) == [chosen_score]


@pytest.mark.django_db
def test_review_form_save_updates_existing_review():
    """save() on an existing review updates text and scores."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, scores = _make_review_form_context(event)
        cat = categories[0]
        old_score = scores[cat][0]
        new_score = scores[cat][2]
        review = ReviewFactory(submission=submission, user=user)
        review.scores.add(old_score)

        form = ReviewForm(
            event=event,
            user=user,
            categories=categories,
            submission=submission,
            instance=review,
            data={"text": "Updated review", f"score_{cat.id}": str(new_score.id)},
        )
        assert form.is_valid(), form.errors
        updated = form.save()

    with scopes_disabled():
        assert updated.pk == review.pk
        assert updated.text == "Updated review"
        assert list(updated.scores.all()) == [new_score]


@pytest.mark.django_db
def test_review_form_save_without_score():
    """save() with no score selected sets empty scores M2M."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, _ = _make_review_form_context(event, required=False)
        cat = categories[0]

        form = ReviewForm(
            event=event,
            user=user,
            categories=categories,
            submission=submission,
            data={"text": "No score", f"score_{cat.id}": "-"},
        )
        assert form.is_valid(), form.errors
        review = form.save()

    with scopes_disabled():
        assert list(review.scores.all()) == []


@pytest.mark.django_db
def test_review_form_clean_invalid_score_choice():
    """A score value not in the category's choices is rejected."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, _ = _make_review_form_context(event)
        cat = categories[0]

        form = ReviewForm(
            event=event,
            user=user,
            categories=categories,
            submission=submission,
            data={"text": "LGTM", f"score_{cat.id}": "99999"},
        )

    assert form.is_valid() is False
    assert f"score_{cat.id}" in form.errors


@pytest.mark.django_db
def test_review_form_save_multiple_categories_partial_scores():
    """save() with multiple categories sets only the scored ones."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event)
        categories, scores = _make_review_form_context(
            event, num_categories=2, required=False
        )
        cat1, cat2 = categories
        chosen_score = scores[cat1][1]

        form = ReviewForm(
            event=event,
            user=user,
            categories=categories,
            submission=submission,
            data={
                "text": "Partial review",
                f"score_{cat1.id}": str(chosen_score.id),
                f"score_{cat2.id}": "-",
            },
        )
        assert form.is_valid(), form.errors
        review = form.save()

    with scopes_disabled():
        assert list(review.scores.all()) == [chosen_score]


def test_direction_form_choices():
    """DirectionForm has 'reviewer' and 'submission' choices."""
    form = DirectionForm()
    choice_values = [c[0] for c in form.fields["direction"].choices]
    assert choice_values == ["reviewer", "submission"]
    assert form.fields["direction"].required is False


@pytest.mark.django_db
def test_review_assignment_form_init_with_provided_data():
    """ReviewAssignmentForm uses provided reviewers and submissions."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        submission = SubmissionFactory(event=event)

        form = ReviewAssignmentForm(
            event=event, reviewers=event.reviewers, submissions=event.submissions.all()
        )

        assert reviewer in form.reviewers
        assert submission in form.submissions


@pytest.mark.django_db
def test_review_assignment_form_reviewers_by_track():
    """reviewers_by_track groups reviewers correctly by track limits."""
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event)
        reviewer_limited = UserFactory()
        reviewer_all = UserFactory()

        team_limited = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team_limited.members.add(reviewer_limited)
        team_limited.limit_events.add(event)
        team_limited.limit_tracks.add(track)

        team_all = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team_all.members.add(reviewer_all)
        team_all.limit_events.add(event)

        form = ReviewAssignmentForm(event=event)

    assert reviewer_limited in form.reviewers_by_track[track]
    assert reviewer_all in form.reviewers_by_track[None]
    assert reviewer_limited not in form.reviewers_by_track[None]


@pytest.mark.django_db
def test_reviewer_for_proposal_form_creates_fields_per_submission():
    """Creates one MultipleChoiceField per submission."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)

        form = ReviewerForProposalForm(
            event=event, review_mapping={"submission_to_assigned_reviewers": {}}
        )

    assert sub1.code in form.fields
    assert sub2.code in form.fields
    assert isinstance(form.fields[sub1.code], forms.MultipleChoiceField)


@pytest.mark.django_db
def test_reviewer_for_proposal_form_initial_assignments():
    """Fields have correct initial values from review_mapping."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        sub = SubmissionFactory(event=event)

        form = ReviewerForProposalForm(
            event=event,
            review_mapping={
                "submission_to_assigned_reviewers": {sub.id: [reviewer.id]}
            },
        )

    assert form.fields[sub.code].initial == [reviewer.id]


@pytest.mark.django_db
def test_reviewer_for_proposal_form_get_review_choices_by_track_caches():
    """get_review_choices_by_track caches results per track."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        SubmissionFactory(event=event)

        form = ReviewerForProposalForm(
            event=event, review_mapping={"submission_to_assigned_reviewers": {}}
        )

    # Second call should return cached result (same object)
    result1 = form.get_review_choices_by_track(None)
    result2 = form.get_review_choices_by_track(None)
    assert result1 is result2


@pytest.mark.django_db
def test_reviewer_for_proposal_form_save():
    """save() sets assigned_reviewers on each submission."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        sub = SubmissionFactory(event=event)

        form = ReviewerForProposalForm(
            event=event,
            review_mapping={"submission_to_assigned_reviewers": {}},
            data={sub.code: [str(reviewer.id)]},
        )
        assert form.is_valid(), form.errors
        form.save()

    with scopes_disabled():
        assert list(sub.assigned_reviewers.all()) == [reviewer]


@pytest.mark.django_db
def test_proposal_for_reviewer_form_creates_fields_per_reviewer():
    """Creates one MultipleChoiceField per reviewer."""
    with scopes_disabled():
        event = EventFactory()
        reviewer1 = UserFactory()
        reviewer2 = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer1, reviewer2)
        team.limit_events.add(event)
        SubmissionFactory(event=event)

        form = ProposalForReviewerForm(
            event=event, review_mapping={"reviewer_to_assigned_submissions": {}}
        )

    assert reviewer1.code in form.fields
    assert reviewer2.code in form.fields


@pytest.mark.django_db
def test_proposal_for_reviewer_form_track_limited_choices():
    """Reviewers limited to a track only see submissions from that track."""
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event)
        other_track = TrackFactory(event=event)
        reviewer = UserFactory()

        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        team.limit_tracks.add(track)

        sub_in_track = SubmissionFactory(event=event, track=track)
        sub_other = SubmissionFactory(event=event, track=other_track)

        form = ProposalForReviewerForm(
            event=event, review_mapping={"reviewer_to_assigned_submissions": {}}
        )

    field = form.fields[reviewer.code]
    choice_ids = {int(c[0]) for c in field.choices}
    assert sub_in_track.id in choice_ids
    assert sub_other.id not in choice_ids


@pytest.mark.django_db
def test_proposal_for_reviewer_form_unlimited_reviewer_sees_all():
    """Reviewers without track limits see all submissions."""
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event)
        reviewer = UserFactory()

        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        # No limit_tracks set

        sub1 = SubmissionFactory(event=event, track=track)
        sub2 = SubmissionFactory(event=event)

        form = ProposalForReviewerForm(
            event=event, review_mapping={"reviewer_to_assigned_submissions": {}}
        )

    field = form.fields[reviewer.code]
    choice_ids = {int(c[0]) for c in field.choices}
    assert sub1.id in choice_ids
    assert sub2.id in choice_ids


@pytest.mark.django_db
def test_proposal_for_reviewer_form_get_submission_choices_no_limit():
    """get_submission_choices_by_tracks with no limit returns all submissions."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        sub = SubmissionFactory(event=event)

        form = ProposalForReviewerForm(
            event=event, review_mapping={"reviewer_to_assigned_submissions": {}}
        )

    result = form.get_submission_choices_by_tracks([])
    assert result is form.all_submission_choices
    assert any(c[0] == sub.id for c in result)


@pytest.mark.django_db
def test_proposal_for_reviewer_form_get_submission_choices_caches_by_tracks():
    """get_submission_choices_by_tracks caches results by track combination."""
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event)
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        team.limit_tracks.add(track)
        SubmissionFactory(event=event, track=track)

        form = ProposalForReviewerForm(
            event=event, review_mapping={"reviewer_to_assigned_submissions": {}}
        )

    result1 = form.get_submission_choices_by_tracks([track.id])
    result2 = form.get_submission_choices_by_tracks([track.id])
    assert result1 is result2


@pytest.mark.django_db
def test_proposal_for_reviewer_form_save():
    """save() sets assigned_reviews on each reviewer."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        sub = SubmissionFactory(event=event)

        form = ProposalForReviewerForm(
            event=event,
            review_mapping={"reviewer_to_assigned_submissions": {}},
            data={reviewer.code: [str(sub.id)]},
        )
        assert form.is_valid(), form.errors
        form.save()

    with scopes_disabled():
        assert list(reviewer.assigned_reviews.all()) == [sub]


@pytest.mark.django_db
def test_review_export_form_init():
    """ReviewExportForm creates expected fields from model_fields."""
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)

        form = ReviewExportForm(event=event, user=user)

    assert "score" in form.fields
    assert "text" in form.fields
    assert "created" in form.fields
    assert "updated" in form.fields
    assert "target" in form.fields
    assert "submission_id" in form.fields
    assert "submission_title" in form.fields
    assert "user_name" in form.fields
    assert "user_email" in form.fields
    # data_delimiter is set to None so should be removed
    assert "data_delimiter" not in form.fields


@pytest.mark.django_db
def test_review_export_form_score_categories_single():
    """With only one score category (default), score_categories returns empty."""
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)

        form = ReviewExportForm(event=event, user=user)

    assert form.score_categories == []


@pytest.mark.django_db
def test_review_export_form_score_categories_multiple():
    """With multiple active categories, score_categories returns all of them."""
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)
        cat2 = ReviewScoreCategoryFactory(event=event, active=True)

        form = ReviewExportForm(event=event, user=user)

    # Default category from build_initial_data + cat2
    assert len(form.score_categories) == 2
    assert cat2 in form.score_categories


@pytest.mark.django_db
def test_review_export_form_score_categories_excludes_inactive():
    """Inactive categories are not included in score_categories."""
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)
        ReviewScoreCategoryFactory(event=event, active=False)

        form = ReviewExportForm(event=event, user=user)

    # Only the default one (from build_initial_data), which is active
    assert form.score_categories == []


@pytest.mark.django_db
def test_review_export_form_builds_score_fields():
    """When there are multiple score categories, score fields are created."""
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)
        default_cat = event.score_categories.first()
        cat2 = ReviewScoreCategoryFactory(event=event, active=True)

        form = ReviewExportForm(event=event, user=user)

    assert f"score_{default_cat.pk}" in form.fields
    assert f"score_{cat2.pk}" in form.fields


@pytest.mark.django_db
def test_review_export_form_filename():
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)

        form = ReviewExportForm(event=event, user=user)

    assert form.filename == f"{event.slug}_reviews"


@pytest.mark.django_db
def test_review_export_form_export_field_names():
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)

        form = ReviewExportForm(event=event, user=user)

    expected = [
        "score",
        "text",
        "submission_id",
        "submission_title",
        "created",
        "updated",
        "user_name",
        "user_email",
    ]
    assert form.export_field_names == expected


@pytest.mark.django_db
def test_review_export_form_export_field_names_with_score_categories():
    """score_field_names appear in export_field_names when multiple categories exist."""
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)
        cat2 = ReviewScoreCategoryFactory(event=event, active=True)

        form = ReviewExportForm(event=event, user=user)

    assert f"score_{cat2.pk}" in form.export_field_names


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "attr_path"),
    (
        ("_get_submission_id_value", "submission.code"),
        ("_get_submission_title_value", "submission.title"),
        ("_get_user_name_value", "user.name"),
        ("_get_user_email_value", "user.email"),
    ),
)
def test_review_export_form_value_getter(method, attr_path):
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)
        review = ReviewFactory(submission__event=event)

        form = ReviewExportForm(event=event, user=user)

    assert getattr(form, method)(review) == attrgetter(attr_path)(review)


@pytest.mark.django_db
def test_review_export_form_get_additional_data():
    """get_additional_data returns score values keyed by category name."""
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)
        cat2 = ReviewScoreCategoryFactory(event=event, active=True)
        score = ReviewScoreFactory(category=cat2, value=5)
        review = ReviewFactory(submission__event=event)
        review.scores.add(score)

        form = ReviewExportForm(event=event, user=user)

        data = form.get_additional_data(review)

    assert str(cat2.name) in data
    assert data[str(cat2.name)] == score.value


@pytest.mark.django_db
def test_review_export_form_get_additional_data_no_score():
    """get_additional_data returns None for categories without a score."""
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)
        cat2 = ReviewScoreCategoryFactory(event=event, active=True)
        review = ReviewFactory(submission__event=event)

        form = ReviewExportForm(event=event, user=user)
        data = form.get_additional_data(review)

    assert data[str(cat2.name)] is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("target", "expected_states"),
    (
        ("all", None),
        ("accepted", {SubmissionStates.ACCEPTED}),
        ("confirmed", {SubmissionStates.CONFIRMED}),
        ("rejected", {SubmissionStates.REJECTED}),
    ),
)
def test_review_export_form_get_queryset_filters_by_target(target, expected_states):
    """get_queryset filters reviews by the selected target state."""
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)
        sub_accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        sub_rejected = SubmissionFactory(event=event, state=SubmissionStates.REJECTED)
        review_accepted = ReviewFactory(submission=sub_accepted)
        review_rejected = ReviewFactory(submission=sub_rejected)

        form = ReviewExportForm(
            event=event, user=user, data={"export_format": "json", "target": target}
        )
        assert form.is_valid(), form.errors
        queryset = form.get_queryset()

        expected = set()
        for review, state in [
            (review_accepted, SubmissionStates.ACCEPTED),
            (review_rejected, SubmissionStates.REJECTED),
        ]:
            if expected_states is None or state in expected_states:
                expected.add(review)
        assert set(queryset) == expected


@pytest.mark.django_db
def test_review_export_form_get_queryset_excludes_own_submissions():
    """get_queryset excludes reviews on submissions by the requesting user."""
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)
        speaker = SpeakerFactory(event=event, user=user)
        own_sub = SubmissionFactory(event=event)
        own_sub.speakers.add(speaker)
        other_sub = SubmissionFactory(event=event)
        ReviewFactory(submission=own_sub)  # should be excluded
        review_other = ReviewFactory(submission=other_sub)

        form = ReviewExportForm(
            event=event, user=user, data={"export_format": "json", "target": "all"}
        )
        assert form.is_valid(), form.errors
        queryset = form.get_queryset()

        assert set(queryset) == {review_other}


@pytest.mark.django_db
@pytest.mark.parametrize("has_answer", (True, False))
def test_review_export_form_get_answer(has_answer):
    """get_answer returns the matching Answer or None."""
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)
        question = QuestionFactory(event=event, target=QuestionTarget.REVIEWER)
        review = ReviewFactory(submission__event=event)
        if has_answer:
            answer = Answer.objects.create(
                question=question, review=review, answer="42"
            )

        form = ReviewExportForm(event=event, user=user)
        result = form.get_answer(question, review)

    if has_answer:
        assert result == answer
    else:
        assert result is None


@pytest.mark.django_db
def test_review_export_form_questions():
    """questions property returns reviewer questions accessible to the user."""
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)
        reviewer_q = QuestionFactory(
            event=event, target=QuestionTarget.REVIEWER, active=True
        )
        QuestionFactory(event=event, target=QuestionTarget.SUBMISSION, active=True)

        form = ReviewExportForm(event=event, user=user)

    assert set(form.questions) == {reviewer_q}


@pytest.mark.django_db
def test_review_export_form_export_data_json():
    """export_data produces a JSON response covering export.py code paths
    including objects without code and get_additional_data."""
    with scopes_disabled():
        event = EventFactory()
        user = make_orga_user(event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        ReviewFactory(submission=sub)
        form = ReviewExportForm(
            event=event,
            user=user,
            data={"export_format": "json", "target": "all", "score": True},
        )
        assert form.is_valid(), form.errors
        response = form.export_data()

    assert response["Content-Type"] == "application/json; charset=utf-8"
    data = json.loads(response.content)
    assert len(data) >= 1


@pytest.mark.django_db
def test_bulk_tag_form_init():
    """BulkTagForm sets tags queryset to event's tags."""
    with scopes_disabled():
        event = EventFactory()
        tag1 = TagFactory(event=event)
        tag2 = TagFactory(event=event)
        TagFactory()  # different event

        form = BulkTagForm(event=event)

    assert set(form.fields["tags"].queryset) == {tag1, tag2}


@pytest.mark.django_db
def test_bulk_tag_form_action_choices():
    """BulkTagForm has 'add' and 'remove' action choices."""
    with scopes_disabled():
        event = EventFactory()
        form = BulkTagForm(event=event)

    choice_values = [c[0] for c in form.fields["action"].choices]
    assert choice_values == ["add", "remove"]


@pytest.mark.django_db
def test_bulk_tag_form_valid():
    with scopes_disabled():
        event = EventFactory()
        tag = TagFactory(event=event)

        form = BulkTagForm(event=event, data={"tags": [tag.pk], "action": "add"})

    assert form.is_valid()
    assert list(form.cleaned_data["tags"]) == [tag]
    assert form.cleaned_data["action"] == "add"


@pytest.mark.django_db
def test_review_assign_import_form_init():
    """Direction field becomes required in ReviewAssignImportForm."""
    with scopes_disabled():
        event = EventFactory()
        form = ReviewAssignImportForm(event=event)

    assert form.fields["direction"].required is True


@pytest.mark.django_db
@pytest.mark.parametrize("lookup_attr", ("email", "code"))
def test_review_assign_import_form_get_user(lookup_attr):
    """_get_user resolves a reviewer by email or code."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)

        form = ReviewAssignImportForm(event=event)
        result = form._get_user(getattr(reviewer, lookup_attr))

    assert result == reviewer


@pytest.mark.django_db
def test_review_assign_import_form_get_user_cached():
    """_get_user caches results."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)

        form = ReviewAssignImportForm(event=event)
        result1 = form._get_user(reviewer.email)
        result2 = form._get_user(reviewer.email)

    assert result1 is result2


@pytest.mark.django_db
def test_review_assign_import_form_get_user_not_found():
    """_get_user raises ValidationError for unknown user."""
    with scopes_disabled():
        event = EventFactory()

        form = ReviewAssignImportForm(event=event)

    with pytest.raises(forms.ValidationError):
        form._get_user("nonexistent@example.com")


@pytest.mark.django_db
def test_review_assign_import_form_get_submission_found():
    """_get_submission returns the submission when found by code."""
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)

        form = ReviewAssignImportForm(event=event)
        result = form._get_submission(sub.code)

    assert result == sub


@pytest.mark.django_db
def test_review_assign_import_form_get_submission_case_insensitive():
    """_get_submission normalises the code to uppercase."""
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)

        form = ReviewAssignImportForm(event=event)
        result = form._get_submission(sub.code.lower())

    assert result == sub


@pytest.mark.django_db
def test_review_assign_import_form_get_submission_not_found():
    """_get_submission raises ValidationError for unknown code."""
    with scopes_disabled():
        event = EventFactory()

        form = ReviewAssignImportForm(event=event)

        with pytest.raises(forms.ValidationError):
            form._get_submission("ZZZZZ")


@pytest.mark.django_db
def test_review_assign_import_form_get_submission_cached():
    """_get_submission uses cache on second call."""
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)

        form = ReviewAssignImportForm(event=event)
        result1 = form._get_submission(sub.code)
        result2 = form._get_submission(sub.code)

    assert result1 == sub
    assert result1 is result2


@pytest.mark.django_db
def test_review_assign_import_form_clean_import_file_valid_json():
    """clean_import_file parses valid JSON."""
    with scopes_disabled():
        event = EventFactory()
        data = {"key": ["val1", "val2"]}
        uploaded = SimpleUploadedFile(
            "assignments.json",
            json.dumps(data).encode(),
            content_type="application/json",
        )

        form = ReviewAssignImportForm(
            event=event,
            data={"direction": "reviewer", "replace_assignments": "0"},
            files={"import_file": uploaded},
        )
        form.is_valid()

    # clean() may fail resolving users, but the JSON parsing itself succeeded
    assert "import_file" not in form.errors


@pytest.mark.django_db
def test_review_assign_import_form_clean_import_file_invalid_json():
    """clean_import_file raises ValidationError for invalid JSON."""
    with scopes_disabled():
        event = EventFactory()
        uploaded = SimpleUploadedFile(
            "bad.json", b"not json at all", content_type="application/json"
        )

        form = ReviewAssignImportForm(
            event=event,
            data={"direction": "reviewer", "replace_assignments": "0"},
            files={"import_file": uploaded},
        )
        form.is_valid()

    assert "import_file" in form.errors


@pytest.mark.django_db
def test_review_assign_import_form_clean_import_file_binary():
    """clean_import_file raises ValidationError for non-UTF8 binary data."""
    with scopes_disabled():
        event = EventFactory()
        uploaded = SimpleUploadedFile(
            "bad.bin", b"\xff\xfe\x00\x01", content_type="application/json"
        )

        form = ReviewAssignImportForm(
            event=event,
            data={"direction": "reviewer", "replace_assignments": "0"},
            files={"import_file": uploaded},
        )
        form.is_valid()

    assert "import_file" in form.errors


@pytest.mark.django_db
def test_review_assign_import_form_clean_reviewer_direction():
    """clean() resolves users as keys and submissions as values for 'reviewer' direction."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        sub = SubmissionFactory(event=event)
        data = {reviewer.email: [sub.code]}
        uploaded = SimpleUploadedFile(
            "assignments.json",
            json.dumps(data).encode(),
            content_type="application/json",
        )

        form = ReviewAssignImportForm(
            event=event,
            data={"direction": "reviewer", "replace_assignments": "0"},
            files={"import_file": uploaded},
        )
        valid = form.is_valid()

    assert valid, form.errors
    # Keys are User objects, values are lists of Submission objects
    resolved = form.cleaned_data["import_file"]
    assert reviewer in resolved
    assert resolved[reviewer] == [sub]


@pytest.mark.django_db
def test_review_assign_import_form_clean_submission_direction():
    """clean() resolves submissions as keys and users as values for 'submission' direction."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        sub = SubmissionFactory(event=event)
        data = {sub.code: [reviewer.email]}
        uploaded = SimpleUploadedFile(
            "assignments.json",
            json.dumps(data).encode(),
            content_type="application/json",
        )

        form = ReviewAssignImportForm(
            event=event,
            data={"direction": "submission", "replace_assignments": "0"},
            files={"import_file": uploaded},
        )
        valid = form.is_valid()

    assert valid, form.errors
    resolved = form.cleaned_data["import_file"]
    assert sub in resolved
    assert resolved[sub] == [reviewer]


@pytest.mark.django_db
def test_review_assign_import_form_save_reviewer_direction():
    """save() with 'reviewer' direction assigns proposals to reviewers."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        sub = SubmissionFactory(event=event)
        data = {reviewer.email: [sub.code]}
        uploaded = SimpleUploadedFile(
            "assignments.json",
            json.dumps(data).encode(),
            content_type="application/json",
        )

        form = ReviewAssignImportForm(
            event=event,
            data={"direction": "reviewer", "replace_assignments": "0"},
            files={"import_file": uploaded},
        )
        assert form.is_valid(), form.errors
        form.save()

    with scopes_disabled():
        assert list(reviewer.assigned_reviews.all()) == [sub]


@pytest.mark.django_db
def test_review_assign_import_form_save_submission_direction():
    """save() with 'submission' direction assigns reviewers to proposals."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        sub = SubmissionFactory(event=event)
        data = {sub.code: [reviewer.email]}
        uploaded = SimpleUploadedFile(
            "assignments.json",
            json.dumps(data).encode(),
            content_type="application/json",
        )

        form = ReviewAssignImportForm(
            event=event,
            data={"direction": "submission", "replace_assignments": "0"},
            files={"import_file": uploaded},
        )
        assert form.is_valid(), form.errors
        form.save()

    with scopes_disabled():
        assert list(sub.assigned_reviewers.all()) == [reviewer]


@pytest.mark.django_db
def test_review_assign_import_form_save_replace_assignments():
    """save() with replace_assignments=1 clears existing assignments first."""
    with scopes_disabled():
        event = EventFactory()
        reviewer1 = UserFactory()
        reviewer2 = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer1, reviewer2)
        team.limit_events.add(event)
        sub = SubmissionFactory(event=event)
        # Pre-existing assignment
        reviewer1.assigned_reviews.add(sub)

        data = {reviewer2.email: [sub.code]}
        uploaded = SimpleUploadedFile(
            "assignments.json",
            json.dumps(data).encode(),
            content_type="application/json",
        )

        form = ReviewAssignImportForm(
            event=event,
            data={"direction": "reviewer", "replace_assignments": "1"},
            files={"import_file": uploaded},
        )
        assert form.is_valid(), form.errors
        form.save()

    with scopes_disabled():
        # reviewer1's assignment was cleared
        assert list(reviewer1.assigned_reviews.all()) == []
        # reviewer2 got the new assignment
        assert list(reviewer2.assigned_reviews.all()) == [sub]


@pytest.mark.django_db
def test_review_assign_import_form_clean_unknown_user():
    """clean() with unknown user in import data shows a validation error."""
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        data = {"unknown@example.com": [sub.code]}
        uploaded = SimpleUploadedFile(
            "assignments.json",
            json.dumps(data).encode(),
            content_type="application/json",
        )

        form = ReviewAssignImportForm(
            event=event,
            data={"direction": "reviewer", "replace_assignments": "0"},
            files={"import_file": uploaded},
        )
        valid = form.is_valid()

    assert valid is False


@pytest.mark.django_db
def test_review_assign_import_form_clean_unknown_submission():
    """clean() with unknown submission code in import data shows a validation error."""
    with scopes_disabled():
        event = EventFactory()
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True)
        team.members.add(reviewer)
        team.limit_events.add(event)
        data = {reviewer.email: ["ZZZZZ"]}
        uploaded = SimpleUploadedFile(
            "assignments.json",
            json.dumps(data).encode(),
            content_type="application/json",
        )

        form = ReviewAssignImportForm(
            event=event,
            data={"direction": "reviewer", "replace_assignments": "0"},
            files={"import_file": uploaded},
        )
        valid = form.is_valid()

    assert valid is False
