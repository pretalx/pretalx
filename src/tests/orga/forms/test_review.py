# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

import pytest
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile

from pretalx.orga.forms.review import (
    BulkTagForm,
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


def make_reviewer(event, *, tracks=(), **user_kwargs):
    reviewer = UserFactory(**user_kwargs)
    team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    team.members.add(reviewer)
    team.limit_events.add(event)
    team.limit_tracks.add(*tracks)
    return reviewer


def upload(payload):
    return SimpleUploadedFile(
        "assignments.json",
        payload if isinstance(payload, bytes) else json.dumps(payload).encode(),
        content_type="application/json",
    )


def test_review_assignment_form_init():
    event = EventFactory()
    track = TrackFactory(event=event)
    reviewer_limited = make_reviewer(event, tracks=[track])
    reviewer_all = make_reviewer(event)
    submission = SubmissionFactory(event=event)

    form = ReviewAssignmentForm(
        event=event, reviewers=event.reviewers, submissions=event.submissions.all()
    )

    assert set(form.reviewers) == {reviewer_limited, reviewer_all}
    assert list(form.submissions) == [submission]
    assert form.reviewers_by_track == {track: {reviewer_limited}, None: {reviewer_all}}


def test_reviewer_for_proposal_form_fields_and_save():
    event = EventFactory()
    reviewer = make_reviewer(event, name="Reviewer")
    sub1 = SubmissionFactory(event=event, title="A talk")
    sub2 = SubmissionFactory(event=event, title="B talk")

    form = ReviewerForProposalForm(
        event=event,
        review_mapping={"submission_to_assigned_reviewers": {sub1.id: [reviewer.id]}},
        data={sub1.code: [str(reviewer.id)]},
    )

    assert list(form.fields) == [sub1.code, sub2.code]
    assert isinstance(form.fields[sub1.code], forms.MultipleChoiceField)
    assert form.fields[sub1.code].initial == [reviewer.id]
    assert form.fields[sub2.code].initial == []
    assert form.fields[sub1.code].choices == [(reviewer.id, "Reviewer")]
    assert form.get_review_choices_by_track(None) is form.get_review_choices_by_track(
        None
    )

    assert form.is_valid(), form.errors
    form.save()

    assert list(sub1.assigned_reviewers.all()) == [reviewer]
    assert list(sub2.assigned_reviewers.all()) == []


def test_proposal_for_reviewer_form_fields_and_save():
    event = EventFactory()
    track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    reviewer_limited = make_reviewer(event, tracks=[track], name="Alice")
    reviewer_all = make_reviewer(event, name="Bob")
    sub_in_track = SubmissionFactory(event=event, track=track, title="In track")
    sub_other = SubmissionFactory(event=event, track=other_track, title="Other")

    form = ProposalForReviewerForm(
        event=event,
        review_mapping={
            "reviewer_to_assigned_submissions": {reviewer_all.id: [sub_other.id]}
        },
        data={
            reviewer_limited.code: [str(sub_in_track.id)],
            reviewer_all.code: [str(sub_other.id)],
        },
    )

    assert list(form.fields) == [reviewer_limited.code, reviewer_all.code]
    assert form.fields[reviewer_limited.code].choices == [(sub_in_track.id, "In track")]
    assert form.fields[reviewer_all.code].choices == [
        (sub_in_track.id, "In track"),
        (sub_other.id, "Other"),
    ]
    assert form.fields[reviewer_all.code].initial == [sub_other.id]
    assert form.get_submission_choices_by_tracks([]) is form.all_submission_choices
    assert form.get_submission_choices_by_tracks(
        [track.id]
    ) is form.get_submission_choices_by_tracks([track.id])

    assert form.is_valid(), form.errors
    form.save()

    assert list(reviewer_limited.assigned_reviews.all()) == [sub_in_track]
    assert list(reviewer_all.assigned_reviews.all()) == [sub_other]


def test_bulk_tag_form_limits_tags_to_event():
    event = EventFactory()
    tag1 = TagFactory(event=event)
    tag2 = TagFactory(event=event)
    TagFactory()

    form = BulkTagForm(event=event, data={"tags": [tag1.pk], "action": "add"})

    assert set(form.fields["tags"].queryset) == {tag1, tag2}
    assert form.is_valid(), form.errors
    assert list(form.cleaned_data["tags"]) == [tag1]
    assert form.cleaned_data["action"] == "add"


def test_review_assign_import_form_get_user():
    event = EventFactory()
    reviewer = make_reviewer(event)

    form = ReviewAssignImportForm(event=event)

    assert form._get_user(reviewer.email) == reviewer
    assert form._get_user(reviewer.code) == reviewer
    assert form._get_user(reviewer.email) is form._get_user(reviewer.email)
    with pytest.raises(forms.ValidationError) as excinfo:
        form._get_user("nonexistent@example.com")
    assert excinfo.value.messages == ["Unknown user: nonexistent@example.com"]


def test_review_assign_import_form_get_submission():
    event = EventFactory()
    sub = SubmissionFactory(event=event)

    form = ReviewAssignImportForm(event=event)

    assert form._get_submission(sub.code) == sub
    assert form._get_submission(sub.code.lower()) == sub
    assert form._get_submission(sub.code) is form._get_submission(sub.code)
    with pytest.raises(forms.ValidationError) as excinfo:
        form._get_submission("ZZZZZ")
    assert excinfo.value.messages == ["Unknown proposal: ZZZZZ"]


@pytest.mark.parametrize(
    ("data", "payload", "errors"),
    (
        (
            {"replace_assignments": "0"},
            {},
            {
                "direction": ["This field is required."],
                "__all__": ["Cannot parse JSON file."],
            },
        ),
        (
            {"direction": "reviewer", "replace_assignments": "0"},
            b"not json at all",
            {
                "import_file": ["Cannot parse JSON file."],
                "__all__": ["Cannot parse JSON file."],
            },
        ),
        (
            {"direction": "reviewer", "replace_assignments": "0"},
            b"\xff\xfe\x00\x01",
            {
                "import_file": ["Cannot parse JSON file."],
                "__all__": ["Cannot parse JSON file."],
            },
        ),
        *(
            (
                {"direction": "reviewer", "replace_assignments": "0"},
                payload,
                {
                    "__all__": [
                        "The uploaded file must contain a JSON object mapping reviewers to lists of proposals, or proposals to lists of reviewers."
                    ]
                },
            )
            for payload in (
                123,
                "hello",
                True,
                [1, 2, 3],
                {"reviewer@example.com": "not-a-list"},
            )
        ),
        (
            {"direction": "reviewer", "replace_assignments": "0"},
            {"unknown@example.com": ["ABCDE"]},
            {"__all__": ["Unknown user: unknown@example.com"]},
        ),
        (
            {"direction": "reviewer", "replace_assignments": "0"},
            {"reviewer@example.com": ["ZZZZZ"]},
            {"__all__": ["Unknown proposal: ZZZZZ"]},
        ),
    ),
    ids=[
        "missing-direction",
        "invalid-json",
        "binary",
        "int",
        "str",
        "bool",
        "list",
        "non-list-values",
        "unknown-user",
        "unknown-submission",
    ],
)
def test_review_assign_import_form_clean_rejects(data, payload, errors):
    event = EventFactory()
    make_reviewer(event, email="reviewer@example.com")
    SubmissionFactory(event=event, code="ABCDE")

    form = ReviewAssignImportForm(
        event=event, data=data, files={"import_file": upload(payload)}
    )

    assert not form.is_valid()
    assert form.errors == errors


@pytest.mark.parametrize(
    ("direction", "payload", "replace", "reviewer1_after"),
    (
        ("reviewer", {"reviewer2@example.com": ["ABCDE"]}, "0", ["ABCDE"]),
        ("submission", {"ABCDE": ["reviewer2@example.com"]}, "0", ["ABCDE"]),
        ("reviewer", {"reviewer2@example.com": ["ABCDE"]}, "1", []),
    ),
    ids=["reviewer-direction", "submission-direction", "replace"],
)
def test_review_assign_import_form_save(direction, payload, replace, reviewer1_after):
    event = EventFactory()
    reviewer1 = make_reviewer(event, email="reviewer1@example.com")
    reviewer2 = make_reviewer(event, email="reviewer2@example.com")
    sub = SubmissionFactory(event=event, code="ABCDE")
    reviewer1.assigned_reviews.add(sub)

    form = ReviewAssignImportForm(
        event=event,
        data={"direction": direction, "replace_assignments": replace},
        files={"import_file": upload(payload)},
    )
    assert form.is_valid(), form.errors
    form.save()

    assert [s.code for s in reviewer1.assigned_reviews.all()] == reviewer1_after
    assert list(reviewer2.assigned_reviews.all()) == [sub]
