# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from decimal import Decimal

import pytest
from django import forms

from pretalx.submission.interfaces.forms import (
    ReviewForm,
    ReviewPhaseForm,
    ReviewScoreCategoryForm,
    ReviewSettingsForm,
)
from pretalx.submission.interfaces.forms.review import strip_zeroes
from pretalx.submission.models import ReviewScore
from tests.factories import (
    EventFactory,
    ReviewFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    SubmissionFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (Decimal("3.00"), Decimal("3.")),
        (Decimal("3.10"), Decimal("3.1")),
        (Decimal("3.14"), Decimal("3.14")),
        (Decimal("0.00"), Decimal("0.")),
        ("not_a_decimal", "not_a_decimal"),
        (42, 42),
        (None, None),
    ),
    ids=(
        "trailing_zeroes",
        "one_trailing_zero",
        "no_trailing_zeroes",
        "zero_value",
        "string_passthrough",
        "int_passthrough",
        "none_passthrough",
    ),
)
def test_strip_zeroes(value, expected):
    assert strip_zeroes(value) == expected


def test_reviewsettingsform_valid_defaults():
    event = EventFactory()
    data = {
        "score_mandatory": False,
        "text_mandatory": False,
        "score_format": "words_numbers",
        "aggregate_method": "median",
        "review_help_text_0": "",
        "use_submission_comments": True,
    }
    form = ReviewSettingsForm(data=data, obj=event, initial={})

    assert form.is_valid(), form.errors


def test_reviewsettingsform_all_score_formats():
    event = EventFactory()
    for fmt in ("words_numbers", "numbers_words", "numbers", "words"):
        data = {
            "score_mandatory": False,
            "text_mandatory": False,
            "score_format": fmt,
            "aggregate_method": "median",
            "review_help_text_0": "",
            "use_submission_comments": True,
        }
        form = ReviewSettingsForm(data=data, obj=event, initial={})
        assert form.is_valid(), f"Format {fmt} failed: {form.errors}"


def test_reviewphaseform_valid_data():
    event = EventFactory()
    data = {
        "name": "Phase 1",
        "start": "",
        "end": "",
        "can_review": True,
        "proposal_visibility": "all",
        "can_see_speaker_names": True,
        "can_see_reviewer_names": True,
        "can_change_submission_state": False,
        "can_see_other_reviews": "always",
        "can_tag_submissions": "never",
        "speakers_can_change_submissions": False,
    }
    form = ReviewPhaseForm(data=data, event=event, locales=event.locales)

    assert form.is_valid(), form.errors


def test_reviewphaseform_start_after_end_invalid():
    event = EventFactory()
    data = {
        "name": "Phase 1",
        "start": "2024-06-20 10:00",
        "end": "2024-06-15 10:00",
        "can_review": True,
        "proposal_visibility": "all",
        "can_see_speaker_names": True,
        "can_see_reviewer_names": True,
        "can_change_submission_state": False,
        "can_see_other_reviews": "always",
        "can_tag_submissions": "never",
        "speakers_can_change_submissions": False,
    }
    form = ReviewPhaseForm(data=data, event=event, locales=event.locales)

    assert not form.is_valid()
    assert "end" in form.errors


def test_reviewphaseform_speakers_edit_disabled_when_event_flag_off():
    event = EventFactory(feature_flags={"speakers_can_edit_submissions": False})
    form = ReviewPhaseForm(event=event, locales=event.locales)

    assert form.fields["speakers_can_change_submissions"].disabled is True
    assert form.fields["speakers_can_change_submissions"].initial is False


def test_reviewphaseform_speakers_edit_enabled_when_event_flag_on():
    event = EventFactory(feature_flags={"speakers_can_edit_submissions": True})
    form = ReviewPhaseForm(event=event, locales=event.locales)

    assert form.fields["speakers_can_change_submissions"].disabled is False


def test_reviewscorecategoryform_init_no_tracks():
    """When use_tracks is disabled, limit_tracks field is removed."""
    event = EventFactory(feature_flags={"use_tracks": False})
    category = ReviewScoreCategoryFactory(event=event)
    form = ReviewScoreCategoryForm(
        data={}, instance=category, event=event, locales=event.locales, prefix="cat"
    )

    assert "limit_tracks" not in form.fields


def test_reviewscorecategoryform_init_with_tracks():
    """When use_tracks is enabled, limit_tracks shows event's tracks."""
    event = EventFactory(feature_flags={"use_tracks": True})
    track = TrackFactory(event=event)
    other_event_track = TrackFactory()
    category = ReviewScoreCategoryFactory(event=event)
    form = ReviewScoreCategoryForm(
        data={}, instance=category, event=event, locales=event.locales, prefix="cat"
    )

    assert "limit_tracks" in form.fields
    assert track in form.fields["limit_tracks"].queryset
    assert other_event_track not in form.fields["limit_tracks"].queryset


def test_reviewscorecategoryform_init_loads_existing_scores():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event)
    score = ReviewScoreFactory(category=category, value=3, label="Good")
    form = ReviewScoreCategoryForm(
        data={}, instance=category, event=event, locales=event.locales, prefix="cat"
    )

    assert f"value_{score.id}" in form.fields
    assert f"label_{score.id}" in form.fields


def test_reviewscorecategoryform_init_new_instance():
    """A new (unsaved) ReviewScoreCategory has no label_fields."""
    event = EventFactory()
    form = ReviewScoreCategoryForm(
        data={}, event=event, locales=event.locales, prefix="cat"
    )

    assert form.label_fields == []


def test_reviewscorecategoryform_get_label_fields():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event)
    ReviewScoreFactory(category=category, value=1, label="Bad")
    ReviewScoreFactory(category=category, value=3, label="Good")
    form = ReviewScoreCategoryForm(
        data={}, instance=category, event=event, locales=event.locales, prefix="cat"
    )

    label_pairs = list(form.get_label_fields())
    assert len(label_pairs) == 2


def test_reviewscorecategoryform_save_creates_new_scores():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event)
    prefix = "cat"
    data = {
        f"{prefix}-name_0": "Updated",
        f"{prefix}-is_independent": False,
        f"{prefix}-weight": "1.0",
        f"{prefix}-required": True,
        f"{prefix}-active": True,
        f"{prefix}-new_scores": "new1",
        f"{prefix}-value_new1": "5",
        f"{prefix}-label_new1": "Excellent",
    }
    form = ReviewScoreCategoryForm(
        data=data, instance=category, event=event, locales=event.locales, prefix=prefix
    )
    assert form.is_valid(), form.errors
    form.save()

    scores = list(category.scores.all())
    assert len(scores) == 1
    assert scores[0].value == Decimal(5)
    assert scores[0].label == "Excellent"


def test_reviewscorecategoryform_save_deletes_score_when_value_cleared():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event)
    score = ReviewScoreFactory(category=category, value=3, label="Good")
    prefix = "cat"
    data = {
        f"{prefix}-name_0": "Updated",
        f"{prefix}-is_independent": False,
        f"{prefix}-weight": "1.0",
        f"{prefix}-required": True,
        f"{prefix}-active": True,
        f"{prefix}-new_scores": "",
        f"{prefix}-value_{score.id}": "",
        f"{prefix}-label_{score.id}": "Good",
    }
    form = ReviewScoreCategoryForm(
        data=data, instance=category, event=event, locales=event.locales, prefix=prefix
    )
    assert form.is_valid(), form.errors
    form.save()

    assert not ReviewScore.objects.filter(id=score.id).exists()


def test_reviewscorecategoryform_save_updates_existing_score():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event)
    score = ReviewScoreFactory(category=category, value=3, label="Good")
    prefix = "cat"
    data = {
        f"{prefix}-name_0": "Updated",
        f"{prefix}-is_independent": False,
        f"{prefix}-weight": "1.0",
        f"{prefix}-required": True,
        f"{prefix}-active": True,
        f"{prefix}-new_scores": "",
        f"{prefix}-value_{score.id}": "4",
        f"{prefix}-label_{score.id}": "Great",
    }
    form = ReviewScoreCategoryForm(
        data=data, instance=category, event=event, locales=event.locales, prefix=prefix
    )
    assert form.is_valid(), form.errors
    form.save()

    score.refresh_from_db()
    assert score.value == Decimal(4)
    assert score.label == "Great"


def test_reviewscorecategoryform_save_unchanged_scores_preserved():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event)
    score = ReviewScoreFactory(category=category, value=3, label="Good")
    prefix = "cat"
    data = {
        f"{prefix}-name_0": str(category.name),
        f"{prefix}-is_independent": False,
        f"{prefix}-weight": "1.0",
        f"{prefix}-required": True,
        f"{prefix}-active": True,
        f"{prefix}-new_scores": "",
        f"{prefix}-value_{score.id}": "3",
        f"{prefix}-label_{score.id}": "Good",
    }
    form = ReviewScoreCategoryForm(
        data=data, instance=category, event=event, locales=event.locales, prefix=prefix
    )
    assert form.is_valid(), form.errors
    form.save()

    score.refresh_from_db()
    assert score.value == Decimal(3)
    assert score.label == "Good"


def _build_category_form_data(category, prefix="cat", overrides=None):
    """Build POST data for ReviewScoreCategoryForm that, by default, matches the
    current category state (so changed_data is empty). Pass ``overrides`` to
    introduce specific changes."""
    data = {
        f"{prefix}-name_0": str(category.name),
        f"{prefix}-is_independent": category.is_independent,
        f"{prefix}-weight": str(category.weight),
        f"{prefix}-required": category.required,
        f"{prefix}-active": category.active,
        f"{prefix}-new_scores": "",
    }
    for score in category.scores.all():
        data[f"{prefix}-value_{score.id}"] = str(score.value)
        data[f"{prefix}-label_{score.id}"] = score.label or ""
    if overrides:
        data.update({f"{prefix}-{key}": value for key, value in overrides.items()})
    return data


def test_reviewscorecategoryform_affects_review_scores_existing_score_value_change():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event)
    score = ReviewScoreFactory(category=category, value=3, label="Good")
    data = _build_category_form_data(category, overrides={f"value_{score.id}": "4"})
    form = ReviewScoreCategoryForm(
        data=data, instance=category, event=event, locales=event.locales, prefix="cat"
    )
    assert form.is_valid(), form.errors

    assert form.affects_review_scores is True


def test_reviewscorecategoryform_affects_review_scores_label_only_change():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event)
    score = ReviewScoreFactory(category=category, value=3, label="Good")
    data = _build_category_form_data(
        category, overrides={f"label_{score.id}": "Excellent"}
    )
    form = ReviewScoreCategoryForm(
        data=data, instance=category, event=event, locales=event.locales, prefix="cat"
    )
    assert form.is_valid(), form.errors

    assert form.affects_review_scores is False


def test_reviewscorecategoryform_affects_review_scores_no_changes():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event)
    ReviewScoreFactory(category=category, value=3, label="Good")
    data = _build_category_form_data(category)
    form = ReviewScoreCategoryForm(
        data=data, instance=category, event=event, locales=event.locales, prefix="cat"
    )
    assert form.is_valid(), form.errors

    assert form.affects_review_scores is False


def test_reviewscorecategoryform_affects_review_scores_delete_non_independent():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event, is_independent=False)
    data = _build_category_form_data(category)
    form = ReviewScoreCategoryForm(
        data=data, instance=category, event=event, locales=event.locales, prefix="cat"
    )
    assert form.is_valid(), form.errors
    form.cleaned_data["DELETE"] = True  # set by the formset when can_delete=True

    assert form.affects_review_scores is True


def test_reviewscorecategoryform_affects_review_scores_delete_independent():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(
        event=event, is_independent=True, weight=Decimal(0)
    )
    data = _build_category_form_data(category)
    form = ReviewScoreCategoryForm(
        data=data, instance=category, event=event, locales=event.locales, prefix="cat"
    )
    assert form.is_valid(), form.errors
    form.cleaned_data["DELETE"] = True

    assert form.affects_review_scores is False


def test_reviewscorecategoryform_save_new_score_without_label_skipped():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event)
    prefix = "cat"
    data = {
        f"{prefix}-name_0": "Updated",
        f"{prefix}-is_independent": False,
        f"{prefix}-weight": "1.0",
        f"{prefix}-required": True,
        f"{prefix}-active": True,
        f"{prefix}-new_scores": "new1",
        f"{prefix}-value_new1": "5",
        f"{prefix}-label_new1": "",
    }
    form = ReviewScoreCategoryForm(
        data=data, instance=category, event=event, locales=event.locales, prefix=prefix
    )
    assert form.is_valid(), form.errors
    form.save()

    assert category.scores.count() == 0


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


def test_review_form_init_creates_score_fields():
    """ReviewForm creates one score field per category."""
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


@pytest.mark.parametrize("text_mandatory", (True, False))
def test_review_form_init_text_required(text_mandatory):
    """text field required reflects event.review_settings['text_mandatory']."""
    event = EventFactory(
        review_settings={"text_mandatory": True} if text_mandatory else {}
    )
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    categories, _ = _make_review_form_context(event)

    form = ReviewForm(
        event=event, user=user, categories=categories, submission=submission
    )

    assert form.fields["text"].required is text_mandatory


def test_review_form_build_score_field_required_category():
    """Required categories don't get a 'No score' choice."""
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


def test_review_form_build_score_field_optional_category():
    """Optional categories include a 'No score' ('-') choice."""
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


def test_review_form_build_score_field_read_only():
    """When read_only=True, score fields are disabled."""
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


def test_review_form_build_score_field_hide_optional():
    """When score_mandatory is True, score fields get the 'hide-optional' class."""
    event = EventFactory(review_settings={"score_mandatory": True})
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


def test_review_form_build_score_field_existing_review():
    """When editing an existing review, score fields get the correct initial value."""
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

    assert form.fields[f"score_{cat.id}"].initial == str(chosen_score.id)


def test_review_form_get_score_fields():
    """get_score_fields yields bound fields for each category in order."""
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


def test_review_form_get_score_field_existing():
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


def test_review_form_get_score_field_missing():
    """get_score_field returns None for a category not in the form."""
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    categories, _ = _make_review_form_context(event)
    other_cat = ReviewScoreCategoryFactory(event=event)

    form = ReviewForm(
        event=event, user=user, categories=categories, submission=submission
    )

    assert form.get_score_field(other_cat) is None


def test_review_form_clean_converts_dash_to_empty():
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


@pytest.mark.parametrize(
    ("provide_score", "expected_valid"), ((True, True), (False, False))
)
def test_review_form_clean_score_mandatory(provide_score, expected_valid):
    """When score_mandatory is set, at least one score must be provided."""
    event = EventFactory(review_settings={"score_mandatory": True})
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


def test_review_form_save_creates_review():
    """save() creates a Review with correct submission, user, and scores."""
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

    assert review.submission == submission
    assert review.user == user
    assert review.text == "Great talk!"
    assert list(review.scores.all()) == [chosen_score]


def test_review_form_save_updates_existing_review():
    """save() on an existing review updates text and scores."""
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

    assert updated.pk == review.pk
    assert updated.text == "Updated review"
    assert list(updated.scores.all()) == [new_score]


def test_review_form_save_without_score():
    """save() with no score selected sets empty scores M2M."""
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

    assert list(review.scores.all()) == []


def test_review_form_clean_invalid_score_choice():
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


def test_review_form_save_multiple_categories_partial_scores():
    """save() with multiple categories sets only the scored ones."""
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

    assert list(review.scores.all()) == [chosen_score]
