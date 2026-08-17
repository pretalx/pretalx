# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.http import QueryDict

from pretalx.common.tables.filters import FilterContext, TableFilterSet
from pretalx.submission.domain.queries.review import annotate_review_count
from pretalx.submission.enums import (
    AttendeeSignupStates,
    QuestionTarget,
    QuestionVariant,
    SubmissionStates,
)
from pretalx.submission.interfaces.filters import (
    CUSTOM_FIELD_SECTION,
    QuestionAnswerFilter,
    question_scope_filters,
    review_filters,
    signup_filters,
    submission_filters,
    submission_question_filters,
)
from tests.factories.event import EventFactory
from tests.factories.person import SpeakerFactory
from tests.factories.submission import (
    AnswerFactory,
    AnswerOptionFactory,
    AttendeeSignupFactory,
    QuestionFactory,
    ReviewFactory,
    SubmissionFactory,
    SubmissionInvitationFactory,
    SubmissionTypeFactory,
    TagFactory,
    TrackFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def build(filters, query="", **options):
    context = FilterContext(**options)
    if callable(filters):
        filters = filters(context)
    return TableFilterSet(filters, data=QueryDict(query), context=context)


def signup_set(submission, query=""):
    return build(signup_filters, query=query, submission=submission)


def submission_set(event, query="", **options):
    return build(submission_filters, query=query, event=event, **options)


def test_signup_state_counts_reflect_signups():
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event)
    AttendeeSignupFactory(submission=submission)
    AttendeeSignupFactory(submission=submission)
    AttendeeSignupFactory(submission=submission, state=AttendeeSignupStates.CANCELED)

    choices = {
        c.value: c.count for c in signup_set(submission).filters["state"].choices
    }

    assert choices[AttendeeSignupStates.CONFIRMED] == 2
    assert choices[AttendeeSignupStates.CANCELED] == 1


def test_signup_state_counts_are_zero_without_submission():
    choices = {c.value: c.count for c in signup_set(None).filters["state"].choices}

    assert choices[AttendeeSignupStates.CONFIRMED] == 0


def test_signup_filter_by_state():
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event)
    confirmed = AttendeeSignupFactory(submission=submission)
    AttendeeSignupFactory(submission=submission, state=AttendeeSignupStates.CANCELED)

    filterset = signup_set(submission, f"state={AttendeeSignupStates.CONFIRMED}")

    assert list(filterset.filter(submission.attendee_signups.all())) == [confirmed]


def test_signup_without_state_returns_all():
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event)
    AttendeeSignupFactory(submission=submission)
    AttendeeSignupFactory(submission=submission)

    filterset = signup_set(submission)

    assert filterset.filter(submission.attendee_signups.all()).count() == 2


def test_submission_state_filter_splits_pending():
    event = EventFactory()
    accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    pending = SubmissionFactory(
        event=event,
        state=SubmissionStates.SUBMITTED,
        pending_state=SubmissionStates.ACCEPTED,
    )

    plain = submission_set(event, "state=accepted")
    synthetic = submission_set(event, "state=pending_state__accepted")

    assert list(plain.filter(event.submissions.all())) == [accepted]
    assert list(synthetic.filter(event.submissions.all())) == [pending]


def test_submission_default_states_apply_only_without_filters():
    event = EventFactory()
    SubmissionFactory(event=event, state=SubmissionStates.WITHDRAWN)
    active = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    defaults = submission_set(event, default_states=SubmissionStates.active_states)
    explicit = submission_set(
        event, "state=withdrawn", default_states=SubmissionStates.active_states
    )

    assert list(defaults.filter(event.submissions.all())) == [active]
    assert [s.state for s in explicit.filter(event.submissions.all())] == ["withdrawn"]


def facet_names(filterset):
    return [f.name for f in filterset.facets]


def test_submission_track_filter_dropped_when_single_and_required():
    event = EventFactory()
    event.cfp.fields["track"] = {"visibility": "required", "min_length": None}
    event.cfp.save()
    TrackFactory(event=event)

    assert "track" not in facet_names(submission_set(event))


def test_submission_track_filter_scoped_to_reviewer_tracks():
    event = EventFactory()
    mine = TrackFactory(event=event)
    TrackFactory(event=event)

    scoped = submission_set(event, limit_tracks=[mine.pk])
    unscoped = submission_set(event)

    assert [c.value for c in scoped.filters["track"].choices] == [str(mine.pk)]
    assert len(unscoped.filters["track"].choices) == 2


def test_submission_track_filter_empty_reviewer_limit_means_all_tracks():
    event = EventFactory()
    TrackFactory(event=event)
    TrackFactory(event=event)

    filterset = submission_set(event, limit_tracks=[])

    assert len(filterset.filters["track"].choices) == 2


def test_submission_state_choices_scoped_to_usable_states():
    event = EventFactory()
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, state=SubmissionStates.WITHDRAWN)

    filterset = submission_set(
        event, usable_states=[SubmissionStates.SUBMITTED, SubmissionStates.ACCEPTED]
    )
    choices = {c.value: c.count for c in filterset.filters["state"].choices}

    assert SubmissionStates.WITHDRAWN not in choices
    assert choices[SubmissionStates.SUBMITTED] == 1


def test_submission_state_values_outside_usable_states_are_ignored():
    event = EventFactory()
    SubmissionFactory(event=event, state=SubmissionStates.WITHDRAWN)

    filterset = submission_set(
        event,
        "state=withdrawn",
        usable_states=[SubmissionStates.SUBMITTED, SubmissionStates.ACCEPTED],
    )

    assert filterset.values["state"] == []


def test_submission_type_counts_honour_usable_states():
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event)
    SubmissionFactory(
        event=event, submission_type=sub_type, state=SubmissionStates.WITHDRAWN
    )
    SubmissionFactory(
        event=event, submission_type=sub_type, state=SubmissionStates.SUBMITTED
    )
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    filterset = submission_set(event, usable_states=[SubmissionStates.SUBMITTED])
    counts = {c.value: c.count for c in filterset.filters["submission_type"].choices}

    assert counts[str(sub_type.pk)] == 1


def test_locale_counts_honour_usable_states():
    event = EventFactory(
        locales=["en", "de"], content_locales=["en", "de"], locale="en"
    )
    SubmissionFactory(
        event=event, content_locale="de", state=SubmissionStates.WITHDRAWN
    )
    SubmissionFactory(event=event, content_locale="en")

    filterset = submission_set(event, usable_states=[SubmissionStates.SUBMITTED])
    counts = {c.value: c.count for c in filterset.filters["content_locale"].choices}

    assert counts == {"en": 1, "de": 0}


def test_submission_tags_filter_offers_event_tags():
    event = EventFactory()
    tag = TagFactory(event=event)

    filterset = submission_set(event)

    assert [c.value for c in filterset.filters["tags"].choices] == [str(tag.pk)]


def test_submission_tags_filter_returns_a_multiply_tagged_proposal_once():
    event = EventFactory()
    tags = [TagFactory(event=event), TagFactory(event=event)]
    submission = SubmissionFactory(event=event)
    submission.tags.set(tags)

    filterset = submission_set(event, f"tags={tags[0].pk}&tags={tags[1].pk}")

    assert list(filterset.filter(event.submissions.all())) == [submission]


def test_question_filters_need_an_event_and_a_user():
    assert submission_question_filters(FilterContext()) == []


def test_featured_filter_narrows_both_ways():
    event = EventFactory()
    featured = SubmissionFactory(event=event, is_featured=True)
    plain = SubmissionFactory(event=event, is_featured=False)

    yes = submission_set(event, "is_featured=true")
    no = submission_set(event, "is_featured=false")

    assert list(yes.filter(event.submissions.all())) == [featured]
    assert list(no.filter(event.submissions.all())) == [plain]


def test_do_not_record_filter():
    event = EventFactory()
    private = SubmissionFactory(event=event, do_not_record=True)
    SubmissionFactory(event=event, do_not_record=False)

    filterset = submission_set(event, "do_not_record=true")

    assert list(filterset.filter(event.submissions.all())) == [private]


def test_requires_signup_filter_needs_the_feature_flag():
    plain = EventFactory()
    with_signup = EventFactory(feature_flags={"attendee_signup": True})

    assert "requires_signup" not in facet_names(submission_set(plain))
    assert "requires_signup" in facet_names(submission_set(with_signup))


def test_requires_signup_filter_covers_inherited_signup():
    event = EventFactory(feature_flags={"attendee_signup": True})
    required = SubmissionFactory(event=event, attendee_signup_required=True)
    SubmissionFactory(event=event, attendee_signup_required=False)

    filterset = submission_set(event, "requires_signup=true")

    assert list(filterset.filter(event.submissions.all())) == [required]


def test_pending_invitations_filter():
    event = EventFactory()
    invited = SubmissionFactory(event=event)
    SubmissionInvitationFactory(submission=invited)
    alone = SubmissionFactory(event=event)

    with_invites = submission_set(event, "has_pending_invitations=true")
    without = submission_set(event, "has_pending_invitations=false")

    assert list(with_invites.filter(event.submissions.all())) == [invited]
    assert list(without.filter(event.submissions.all())) == [alone]


def test_custom_field_filters_are_grouped_under_their_own_heading():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)

    filters = submission_question_filters(
        FilterContext(
            event=event, user=make_orga_user(event, can_change_submissions=True)
        )
    )

    assert [f.section for f in filters] == [CUSTOM_FIELD_SECTION]
    assert filters[0].question == question


def review_set(event, query="", max_review_count=5):
    return build(
        review_filters, query=query, event=event, max_review_count=max_review_count
    )


def test_review_count_filter_needs_more_than_one_review_in_the_event():
    event = EventFactory()

    assert "review-count" not in facet_names(review_set(event, max_review_count=1))
    assert "review-count" in facet_names(review_set(event, max_review_count=2))


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        ("", None),
        ("review-count=nonsense", None),
        ("review-count=1,", (1, None)),
        ("review-count=,3", (None, 3)),
        ("review-count=1,3", (1, 3)),
        ("review-count=x,y", (None, None)),
    ),
)
def test_review_count_filter_parses_its_range(query, expected):
    event = EventFactory()

    assert review_set(event, query).values["review-count"] == expected


@pytest.mark.parametrize(
    ("query", "narrows"),
    (
        ("", False),
        ("review-count=nonsense", False),
        ("review-count=0,", False),
        ("review-count=,5", False),
        ("review-count=2,", True),
        ("review-count=,4", True),
    ),
)
def test_review_count_filter_only_counts_as_set_when_it_narrows(query, narrows):
    event = EventFactory()

    assert review_set(event, query).is_set("review-count") is narrows


def test_review_count_filter_narrows_from_both_ends():
    event = EventFactory()
    quiet = SubmissionFactory(event=event)
    ReviewFactory(submission=quiet)
    busy = SubmissionFactory(event=event)
    for _ in range(3):
        ReviewFactory(submission=busy)

    # The view annotates before filtering; the filter only narrows.
    submissions = annotate_review_count(event.submissions.all())

    assert list(review_set(event, "review-count=2,").filter(submissions)) == [busy]
    assert list(review_set(event, "review-count=,1").filter(submissions)) == [quiet]


def test_review_count_filter_pill_names_the_range():
    event = EventFactory()

    pills = review_set(event, "review-count=2,").pills

    assert [pill.label for pill in pills] == ["Reviews: 2–5"]


def test_question_filter_offers_options_and_presence():
    event = EventFactory()
    question = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.CHOICES
    )
    option = AnswerOptionFactory(question=question, answer="green")

    values = [
        choice.value
        for choice in build([QuestionAnswerFilter(question=question)])
        .filters[f"question_{question.pk}"]
        .choices
    ]

    assert values == [str(option.pk), "__answered__", "__unanswered__"]


def test_question_filter_matches_option_and_absence():
    event = EventFactory()
    question = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.CHOICES
    )
    option = AnswerOptionFactory(question=question, answer="green")
    answered = SubmissionFactory(event=event)
    answer = AnswerFactory(question=question, submission=answered)
    answer.options.set([option])
    unanswered = SubmissionFactory(event=event)

    param = f"question_{question.pk}"
    by_option = build([QuestionAnswerFilter(question=question)], f"{param}={option.pk}")
    by_absence = build(
        [QuestionAnswerFilter(question=question)], f"{param}=__unanswered__"
    )

    assert list(by_option.filter(event.submissions.all())) == [answered]
    assert list(by_absence.filter(event.submissions.all())) == [unanswered]


def test_question_filter_accepts_a_free_text_value():
    event = EventFactory()
    question = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.STRING
    )
    match = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=match, answer="blue")
    other = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=other, answer="red")

    filterset = build(
        [QuestionAnswerFilter(question=question)], f"question_{question.pk}=blue"
    )

    assert list(filterset.filter(event.submissions.all())) == [match]


def test_question_filter_offers_both_answers_for_a_boolean_field():
    event = EventFactory()
    question = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.BOOLEAN
    )

    values = [
        choice.value
        for choice in build([QuestionAnswerFilter(question=question)])
        .filters[f"question_{question.pk}"]
        .choices
    ]

    assert values == ["True", "False", "__answered__", "__unanswered__"]


def test_question_filter_matches_any_answer():
    event = EventFactory()
    question = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.STRING
    )
    answered = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=answered, answer="blue")
    SubmissionFactory(event=event)

    filterset = build(
        [QuestionAnswerFilter(question=question)],
        f"question_{question.pk}=__answered__",
    )

    assert list(filterset.filter(event.submissions.all())) == [answered]


def test_question_pills_name_the_field_they_belong_to():
    event = EventFactory()
    question = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.STRING
    )

    filterset = build(
        [QuestionAnswerFilter(question=question)],
        f"question_{question.pk}=__unanswered__&question_{question.pk}=blue",
    )
    labels = [pill.label for pill in filterset.pills]

    assert labels == [
        f"{question.question}: Not answered",
        f"{question.question}: blue",
    ]


def test_question_filter_keeps_free_text_out_of_the_segments():
    event = EventFactory()
    question = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.STRING
    )

    bound = build(
        [QuestionAnswerFilter(question=question)], f"question_{question.pk}=blue"
    ).facets[0]

    # "Any" stays unselected while a free-text value filters, so the
    # segments never claim a state the pill contradicts.
    assert bound.selected_values(bound.value) == []


def test_question_filter_absence_ignores_answers_of_other_target_types():
    event = EventFactory()
    question = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.STRING
    )
    answered = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=answered, answer="blue")
    unanswered = SubmissionFactory(event=event)
    # An answer with no submission: its NULL key must not poison the NOT IN.
    speaker = SpeakerFactory(event=event)
    AnswerFactory(question=question, submission=None, speaker=speaker, answer="x")

    filterset = build(
        [QuestionAnswerFilter(question=question)],
        f"question_{question.pk}=__unanswered__",
    )

    assert list(filterset.filter(event.submissions.all())) == [unanswered]


def scope_set(event, query=""):
    return build(question_scope_filters, query=query, event=event)


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        ("", {SubmissionStates.SUBMITTED, SubmissionStates.CONFIRMED}),
        ("role=accepted", {SubmissionStates.CONFIRMED}),
        ("role=confirmed", {SubmissionStates.CONFIRMED}),
    ),
    ids=("no_role", "accepted", "confirmed"),
)
def test_question_scope_role_narrows_submissions(query, expected):
    event = EventFactory()
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    filterset = scope_set(event, query=query)

    states = {talk.state for talk in filterset.filter(event.submissions.all())}

    assert states == expected


def test_question_scope_track_and_type_narrow_submissions():
    event = EventFactory(feature_flags={"use_tracks": True})
    track = TrackFactory(event=event)
    stype = SubmissionTypeFactory(event=event)
    match = SubmissionFactory(event=event, track=track, submission_type=stype)
    SubmissionFactory(event=event, track=track)
    filterset = scope_set(event, query=f"track={track.pk}&submission_type={stype.pk}")

    assert list(filterset.filter(event.submissions.all())) == [match]


def test_question_scope_hides_the_track_filter_without_tracks():
    event = EventFactory(feature_flags={"use_tracks": False})

    facets = {facet.name for facet in scope_set(event).facets}

    assert "track" not in facets
    assert "role" in facets


def test_question_scope_is_inactive_without_query():
    event = EventFactory()
    SubmissionFactory(event=event)
    filterset = scope_set(event)
    filterset.filter(event.submissions.all())

    assert filterset.is_active is False
