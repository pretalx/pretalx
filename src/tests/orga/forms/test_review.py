# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

import pytest
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile

from pretalx.orga.forms.review import (
    BulkTagForm,
    DirectionForm,
    ProposalForReviewerForm,
    ReviewAssignImportForm,
    ReviewAssignmentForm,
    ReviewerForProposalForm,
)
from tests.factories import (
    EventFactory,
    SubmissionFactory,
    TagFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_direction_form_choices():
    """DirectionForm has 'reviewer' and 'submission' choices."""
    form = DirectionForm()
    choice_values = [c[0] for c in form.fields["direction"].choices]
    assert choice_values == ["reviewer", "submission"]
    assert form.fields["direction"].required is False


def test_review_assignment_form_init_with_provided_data():
    """ReviewAssignmentForm uses provided reviewers and submissions."""
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


def test_review_assignment_form_reviewers_by_track():
    """reviewers_by_track groups reviewers correctly by track limits."""
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


def test_reviewer_for_proposal_form_creates_fields_per_submission():
    """Creates one MultipleChoiceField per submission."""
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


def test_reviewer_for_proposal_form_initial_assignments():
    """Fields have correct initial values from review_mapping."""
    event = EventFactory()
    reviewer = UserFactory()
    team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    team.members.add(reviewer)
    team.limit_events.add(event)
    sub = SubmissionFactory(event=event)

    form = ReviewerForProposalForm(
        event=event,
        review_mapping={"submission_to_assigned_reviewers": {sub.id: [reviewer.id]}},
    )

    assert form.fields[sub.code].initial == [reviewer.id]


def test_reviewer_for_proposal_form_get_review_choices_by_track_caches():
    """get_review_choices_by_track caches results per track."""
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


def test_reviewer_for_proposal_form_save():
    """save() sets assigned_reviewers on each submission."""
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

    assert list(sub.assigned_reviewers.all()) == [reviewer]


def test_proposal_for_reviewer_form_creates_fields_per_reviewer():
    """Creates one MultipleChoiceField per reviewer."""
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


def test_proposal_for_reviewer_form_track_limited_choices():
    """Reviewers limited to a track only see submissions from that track."""
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


def test_proposal_for_reviewer_form_unlimited_reviewer_sees_all():
    """Reviewers without track limits see all submissions."""
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


def test_proposal_for_reviewer_form_get_submission_choices_no_limit():
    """get_submission_choices_by_tracks with no limit returns all submissions."""
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


def test_proposal_for_reviewer_form_get_submission_choices_caches_by_tracks():
    """get_submission_choices_by_tracks caches results by track combination."""
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


def test_proposal_for_reviewer_form_save():
    """save() sets assigned_reviews on each reviewer."""
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

    assert list(reviewer.assigned_reviews.all()) == [sub]


def test_bulk_tag_form_init():
    """BulkTagForm sets tags queryset to event's tags."""
    event = EventFactory()
    tag1 = TagFactory(event=event)
    tag2 = TagFactory(event=event)
    TagFactory()  # different event

    form = BulkTagForm(event=event)

    assert set(form.fields["tags"].queryset) == {tag1, tag2}


def test_bulk_tag_form_action_choices():
    """BulkTagForm has 'add' and 'remove' action choices."""
    event = EventFactory()
    form = BulkTagForm(event=event)

    choice_values = [c[0] for c in form.fields["action"].choices]
    assert choice_values == ["add", "remove"]


def test_bulk_tag_form_valid():
    event = EventFactory()
    tag = TagFactory(event=event)

    form = BulkTagForm(event=event, data={"tags": [tag.pk], "action": "add"})

    assert form.is_valid()
    assert list(form.cleaned_data["tags"]) == [tag]
    assert form.cleaned_data["action"] == "add"


def test_review_assign_import_form_init():
    """Direction field becomes required in ReviewAssignImportForm."""
    event = EventFactory()
    form = ReviewAssignImportForm(event=event)

    assert form.fields["direction"].required is True


@pytest.mark.parametrize("lookup_attr", ("email", "code"))
def test_review_assign_import_form_get_user(lookup_attr):
    """_get_user resolves a reviewer by email or code."""
    event = EventFactory()
    reviewer = UserFactory()
    team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    team.members.add(reviewer)
    team.limit_events.add(event)

    form = ReviewAssignImportForm(event=event)
    result = form._get_user(getattr(reviewer, lookup_attr))

    assert result == reviewer


def test_review_assign_import_form_get_user_cached():
    """_get_user caches results."""
    event = EventFactory()
    reviewer = UserFactory()
    team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    team.members.add(reviewer)
    team.limit_events.add(event)

    form = ReviewAssignImportForm(event=event)
    result1 = form._get_user(reviewer.email)
    result2 = form._get_user(reviewer.email)

    assert result1 is result2


def test_review_assign_import_form_get_user_not_found():
    """_get_user raises ValidationError for unknown user."""
    event = EventFactory()

    form = ReviewAssignImportForm(event=event)

    with pytest.raises(forms.ValidationError):
        form._get_user("nonexistent@example.com")


def test_review_assign_import_form_get_submission_found():
    """_get_submission returns the submission when found by code."""
    event = EventFactory()
    sub = SubmissionFactory(event=event)

    form = ReviewAssignImportForm(event=event)
    result = form._get_submission(sub.code)

    assert result == sub


def test_review_assign_import_form_get_submission_case_insensitive():
    """_get_submission normalises the code to uppercase."""
    event = EventFactory()
    sub = SubmissionFactory(event=event)

    form = ReviewAssignImportForm(event=event)
    result = form._get_submission(sub.code.lower())

    assert result == sub


def test_review_assign_import_form_get_submission_not_found():
    """_get_submission raises ValidationError for unknown code."""
    event = EventFactory()

    form = ReviewAssignImportForm(event=event)

    with pytest.raises(forms.ValidationError):
        form._get_submission("ZZZZZ")


def test_review_assign_import_form_get_submission_cached():
    """_get_submission uses cache on second call."""
    event = EventFactory()
    sub = SubmissionFactory(event=event)

    form = ReviewAssignImportForm(event=event)
    result1 = form._get_submission(sub.code)
    result2 = form._get_submission(sub.code)

    assert result1 == sub
    assert result1 is result2


def test_review_assign_import_form_clean_import_file_valid_json():
    """clean_import_file parses valid JSON."""
    event = EventFactory()
    data = {"key": ["val1", "val2"]}
    uploaded = SimpleUploadedFile(
        "assignments.json", json.dumps(data).encode(), content_type="application/json"
    )

    form = ReviewAssignImportForm(
        event=event,
        data={"direction": "reviewer", "replace_assignments": "0"},
        files={"import_file": uploaded},
    )
    form.is_valid()

    # clean() may fail resolving users, but the JSON parsing itself succeeded
    assert "import_file" not in form.errors


def test_review_assign_import_form_clean_import_file_invalid_json():
    """clean_import_file raises ValidationError for invalid JSON."""
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


def test_review_assign_import_form_clean_import_file_binary():
    """clean_import_file raises ValidationError for non-UTF8 binary data."""
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


def test_review_assign_import_form_clean_reviewer_direction():
    """clean() resolves users as keys and submissions as values for 'reviewer' direction."""
    event = EventFactory()
    reviewer = UserFactory()
    team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    team.members.add(reviewer)
    team.limit_events.add(event)
    sub = SubmissionFactory(event=event)
    data = {reviewer.email: [sub.code]}
    uploaded = SimpleUploadedFile(
        "assignments.json", json.dumps(data).encode(), content_type="application/json"
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


def test_review_assign_import_form_clean_submission_direction():
    """clean() resolves submissions as keys and users as values for 'submission' direction."""
    event = EventFactory()
    reviewer = UserFactory()
    team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    team.members.add(reviewer)
    team.limit_events.add(event)
    sub = SubmissionFactory(event=event)
    data = {sub.code: [reviewer.email]}
    uploaded = SimpleUploadedFile(
        "assignments.json", json.dumps(data).encode(), content_type="application/json"
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


def test_review_assign_import_form_save_reviewer_direction():
    """save() with 'reviewer' direction assigns proposals to reviewers."""
    event = EventFactory()
    reviewer = UserFactory()
    team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    team.members.add(reviewer)
    team.limit_events.add(event)
    sub = SubmissionFactory(event=event)
    data = {reviewer.email: [sub.code]}
    uploaded = SimpleUploadedFile(
        "assignments.json", json.dumps(data).encode(), content_type="application/json"
    )

    form = ReviewAssignImportForm(
        event=event,
        data={"direction": "reviewer", "replace_assignments": "0"},
        files={"import_file": uploaded},
    )
    assert form.is_valid(), form.errors
    form.save()

    assert list(reviewer.assigned_reviews.all()) == [sub]


def test_review_assign_import_form_save_submission_direction():
    """save() with 'submission' direction assigns reviewers to proposals."""
    event = EventFactory()
    reviewer = UserFactory()
    team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    team.members.add(reviewer)
    team.limit_events.add(event)
    sub = SubmissionFactory(event=event)
    data = {sub.code: [reviewer.email]}
    uploaded = SimpleUploadedFile(
        "assignments.json", json.dumps(data).encode(), content_type="application/json"
    )

    form = ReviewAssignImportForm(
        event=event,
        data={"direction": "submission", "replace_assignments": "0"},
        files={"import_file": uploaded},
    )
    assert form.is_valid(), form.errors
    form.save()

    assert list(sub.assigned_reviewers.all()) == [reviewer]


def test_review_assign_import_form_save_replace_assignments():
    """save() with replace_assignments=1 clears existing assignments first."""
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
        "assignments.json", json.dumps(data).encode(), content_type="application/json"
    )

    form = ReviewAssignImportForm(
        event=event,
        data={"direction": "reviewer", "replace_assignments": "1"},
        files={"import_file": uploaded},
    )
    assert form.is_valid(), form.errors
    form.save()

    # reviewer1's assignment was cleared
    assert list(reviewer1.assigned_reviews.all()) == []
    # reviewer2 got the new assignment
    assert list(reviewer2.assigned_reviews.all()) == [sub]


def test_review_assign_import_form_clean_unknown_user():
    """clean() with unknown user in import data shows a validation error."""
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    data = {"unknown@example.com": [sub.code]}
    uploaded = SimpleUploadedFile(
        "assignments.json", json.dumps(data).encode(), content_type="application/json"
    )

    form = ReviewAssignImportForm(
        event=event,
        data={"direction": "reviewer", "replace_assignments": "0"},
        files={"import_file": uploaded},
    )
    valid = form.is_valid()

    assert valid is False


def test_review_assign_import_form_clean_unknown_submission():
    """clean() with unknown submission code in import data shows a validation error."""
    event = EventFactory()
    reviewer = UserFactory()
    team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    team.members.add(reviewer)
    team.limit_events.add(event)
    data = {reviewer.email: ["ZZZZZ"]}
    uploaded = SimpleUploadedFile(
        "assignments.json", json.dumps(data).encode(), content_type="application/json"
    )

    form = ReviewAssignImportForm(
        event=event,
        data={"direction": "reviewer", "replace_assignments": "0"},
        files={"import_file": uploaded},
    )
    valid = form.is_valid()

    assert valid is False
