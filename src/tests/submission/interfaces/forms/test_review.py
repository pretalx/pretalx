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


def _phase_data(**overrides):
    return {
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
        **overrides,
    }


def test_reviewphaseform_validates_dates_and_follows_speaker_edit_flag():
    event = EventFactory(feature_flags={"speakers_can_edit_submissions": False})

    form = ReviewPhaseForm(data=_phase_data(), event=event, locales=event.locales)
    assert form.is_valid(), form.errors

    form = ReviewPhaseForm(
        data=_phase_data(start="2024-06-20 10:00", end="2024-06-15 10:00"),
        event=event,
        locales=event.locales,
    )
    assert not form.is_valid()
    assert list(form.errors) == ["end"]

    form = ReviewPhaseForm(event=event, locales=event.locales)
    assert form.fields["speakers_can_change_submissions"].disabled is True
    assert form.fields["speakers_can_change_submissions"].initial is False

    event = EventFactory(feature_flags={"speakers_can_edit_submissions": True})
    form = ReviewPhaseForm(event=event, locales=event.locales)
    assert form.fields["speakers_can_change_submissions"].disabled is False


def _category_form(category, data=None, **kwargs):
    event = category.event
    return ReviewScoreCategoryForm(
        data=data if data is not None else {},
        instance=category,
        event=event,
        locales=event.locales,
        prefix="cat",
        **kwargs,
    )


def _build_category_form_data(category, prefix="cat", overrides=None):
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


def test_reviewscorecategoryform_init_tracks_and_score_fields():
    event = EventFactory(feature_flags={"use_tracks": False})
    form = ReviewScoreCategoryForm(
        data={}, event=event, locales=event.locales, prefix="cat"
    )

    assert "limit_tracks" not in form.fields
    assert form.label_fields == []

    event = EventFactory(feature_flags={"use_tracks": True})
    track = TrackFactory(event=event)
    TrackFactory()
    category = ReviewScoreCategoryFactory(event=event)
    bad = ReviewScoreFactory(category=category, value=1, label="Bad")
    good = ReviewScoreFactory(category=category, value=3, label="Good")

    form = _category_form(category)

    assert list(form.fields["limit_tracks"].queryset) == [track]
    assert [(value.name, label.name) for value, label in form.get_label_fields()] == [
        (f"value_{bad.id}", f"label_{bad.id}"),
        (f"value_{good.id}", f"label_{good.id}"),
    ]


def test_reviewscorecategoryform_save_creates_updates_and_deletes_scores():
    category = ReviewScoreCategoryFactory()
    data = _build_category_form_data(
        category,
        overrides={
            "name_0": "Updated",
            "new_scores": "new1,new2",
            "value_new1": "5",
            "label_new1": "Excellent",
            "value_new2": "4",
            "label_new2": "",
        },
    )
    form = _category_form(category, data=data)
    assert form.is_valid(), form.errors
    form.save()

    score = category.scores.get()
    assert (score.value, score.label) == (Decimal(5), "Excellent")

    data = _build_category_form_data(
        category, overrides={f"value_{score.id}": "4", f"label_{score.id}": "Great"}
    )
    form = _category_form(category, data=data)
    assert form.is_valid(), form.errors
    form.save()

    score.refresh_from_db()
    assert (score.value, score.label) == (Decimal(4), "Great")

    form = _category_form(category, data=_build_category_form_data(category))
    assert form.is_valid(), form.errors
    form.save()

    score.refresh_from_db()
    assert (score.value, score.label) == (Decimal(4), "Great")

    data = _build_category_form_data(category, overrides={f"value_{score.id}": ""})
    form = _category_form(category, data=data)
    assert form.is_valid(), form.errors
    form.save()

    assert not ReviewScore.objects.filter(id=score.id).exists()


@pytest.mark.parametrize(
    ("build_overrides", "build_error_fields"),
    (
        (
            lambda bad, good: {f"value_{bad.id}": "1", f"value_{good.id}": "1"},
            lambda bad, good: [f"value_{bad.id}", f"value_{good.id}"],
        ),
        (
            lambda bad, good: {f"value_{bad.id}": "1", f"value_{good.id}": "1.00"},
            lambda bad, good: [f"value_{bad.id}", f"value_{good.id}"],
        ),
        (
            lambda bad, good: {
                "new_scores": "new1",
                "value_new1": "1",
                "label_new1": "Also bad",
            },
            lambda bad, good: [f"value_{bad.id}", "value_new1"],
        ),
        (
            lambda bad, good: {
                "new_scores": "new1,new2",
                "value_new1": "4",
                "label_new1": "Also bad",
                "value_new2": "4",
                "label_new2": "Even worse",
            },
            lambda bad, good: ["value_new1", "value_new2"],
        ),
        (
            lambda bad, good: {f"value_{bad.id}": "", f"value_{good.id}": "1"},
            lambda bad, good: [],
        ),
        (
            lambda bad, good: {
                "new_scores": "new1",
                "value_new1": "1",
                "label_new1": "",
            },
            lambda bad, good: [],
        ),
    ),
    ids=(
        "two_existing_scores",
        "two_existing_scores_differing_precision",
        "existing_and_new_score",
        "two_new_scores",
        "duplicate_of_deleted_score",
        "new_score_without_label",
    ),
)
def test_reviewscorecategoryform_duplicate_score_values(
    build_overrides, build_error_fields
):
    category = ReviewScoreCategoryFactory()
    bad = ReviewScoreFactory(category=category, value=1, label="Bad")
    good = ReviewScoreFactory(category=category, value=3, label="Good")
    data = _build_category_form_data(category, overrides=build_overrides(bad, good))

    form = _category_form(category, data=data)

    error_fields = build_error_fields(bad, good)
    message = "A score cannot be used twice in the same review category."
    expected = {field: [message] for field in error_fields}
    if error_fields:
        expected["__all__"] = [message]

    assert form.is_valid() is not bool(error_fields)
    assert form.errors == expected
    assert form.non_field_errors() == ([message] if error_fields else [])


def test_reviewscorecategoryform_affects_review_scores():
    category = ReviewScoreCategoryFactory(is_independent=False)
    score = ReviewScoreFactory(category=category, value=3, label="Good")

    def affects(overrides=None, delete=False):
        form = _category_form(
            category, data=_build_category_form_data(category, overrides=overrides)
        )
        assert form.is_valid(), form.errors
        if delete:
            form.cleaned_data["DELETE"] = True  # set by the formset when can_delete
        return form.affects_review_scores

    assert affects({f"value_{score.id}": "4"}) is True
    assert affects({f"label_{score.id}": "Excellent"}) is False
    assert affects() is False
    assert affects(delete=True) is True

    independent = ReviewScoreCategoryFactory(
        event=category.event, is_independent=True, weight=Decimal(0)
    )
    form = _category_form(independent, data=_build_category_form_data(independent))
    assert form.is_valid(), form.errors
    form.cleaned_data["DELETE"] = True

    assert form.affects_review_scores is False


def _make_review_form_context(event, *, num_categories=1, **category_kwargs):
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


def test_review_form_init_builds_score_fields_per_category():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    (required_cat,), scores = _make_review_form_context(event, required=True)
    (optional_cat,), _ = _make_review_form_context(event, required=False)
    categories = [required_cat, optional_cat]
    other_cat = ReviewScoreCategoryFactory(event=event)
    review = ReviewFactory(submission=submission, user=user)
    chosen_score = scores[required_cat][2]
    review.scores.add(chosen_score)

    form = ReviewForm(
        event=event, user=user, categories=categories, submission=submission
    )

    assert form.fields["text"].required is False
    required_field = form.fields[f"score_{required_cat.id}"]
    assert isinstance(required_field, forms.ChoiceField)
    assert required_field.required is True
    assert [choice for choice, _ in required_field.choices] == [
        score.id for score in scores[required_cat]
    ]
    optional_field = form.fields[f"score_{optional_cat.id}"]
    assert optional_field.required is False
    assert [choice for choice, _ in optional_field.choices][0] == "-"
    assert "hide-optional" not in optional_field.widget.attrs.get("class", "")
    assert [field.name for field in form.get_score_fields()] == [
        f"score_{required_cat.id}",
        f"score_{optional_cat.id}",
    ]
    assert form.get_score_field(required_cat).name == f"score_{required_cat.id}"
    assert form.get_score_field(other_cat) is None

    form = ReviewForm(
        event=event,
        user=user,
        categories=categories,
        submission=submission,
        instance=review,
        read_only=True,
    )

    assert form.fields[f"score_{required_cat.id}"].initial == str(chosen_score.id)
    assert form.fields[f"score_{optional_cat.id}"].initial is None
    assert all(form.fields[f"score_{cat.id}"].disabled for cat in categories)

    event = EventFactory(
        review_settings={"text_mandatory": True, "score_mandatory": True}
    )
    categories, _ = _make_review_form_context(event)
    form = ReviewForm(
        event=event,
        user=user,
        categories=categories,
        submission=SubmissionFactory(event=event),
    )

    assert form.fields["text"].required is True
    assert (
        form.fields[f"score_{categories[0].id}"].widget.attrs["class"]
        == "hide-optional"
    )


def test_review_form_clean_enforces_mandatory_and_valid_scores():
    event = EventFactory(review_settings={"score_mandatory": True})
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    categories, scores = _make_review_form_context(event, required=False)
    cat = categories[0]

    def build(score_value):
        return ReviewForm(
            event=event,
            user=user,
            categories=categories,
            submission=submission,
            data={"text": "Good talk", f"score_{cat.id}": score_value},
        )

    form = build(str(scores[cat][1].id))
    assert form.is_valid(), form.errors
    assert form.cleaned_data[f"score_{cat.id}"] == str(scores[cat][1].id)

    form = build("-")
    assert not form.is_valid()
    assert list(form.errors) == ["__all__"]
    assert form.cleaned_data[f"score_{cat.id}"] == ""

    form = build("99999")
    assert not form.is_valid()
    assert list(form.errors) == [f"score_{cat.id}", "__all__"]


def test_review_form_save_creates_updates_and_clears_scores():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    categories, scores = _make_review_form_context(
        event, num_categories=2, required=False
    )
    cat1, cat2 = categories
    chosen_score = scores[cat1][2]

    def build(text, score1, score2="-", instance=None):
        return ReviewForm(
            event=event,
            user=user,
            categories=categories,
            submission=submission,
            instance=instance,
            data={"text": text, f"score_{cat1.id}": score1, f"score_{cat2.id}": score2},
        )

    form = build("Second save", str(chosen_score.id))
    assert form.is_valid(), form.errors
    concurrent_review = ReviewFactory(
        submission=submission, user=user, text="First save"
    )

    review = form.save()

    assert review.pk == concurrent_review.pk
    assert review.created == concurrent_review.created
    assert review.user_id == user.pk
    assert review.text == "Second save"
    assert list(review.scores.all()) == [chosen_score]
    assert list(submission.reviews.all()) == [review]

    new_score = scores[cat1][0]
    form = build("Updated review", str(new_score.id), str(scores[cat2][1].id), review)
    assert form.is_valid(), form.errors
    updated = form.save()

    assert updated.pk == review.pk
    assert updated.text == "Updated review"
    assert set(updated.scores.all()) == {new_score, scores[cat2][1]}

    form = build("No score", "-", "-", review)
    assert form.is_valid(), form.errors
    cleared = form.save()

    assert cleared.pk == review.pk
    assert list(cleared.scores.all()) == []
