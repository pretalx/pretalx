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


def state_counts(filterset):
    return {c.value: c.count for c in filterset.filters["state"].choices}


def test_signup_state_filter_counts_and_narrows():
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event)
    confirmed = [
        AttendeeSignupFactory(submission=submission),
        AttendeeSignupFactory(submission=submission),
    ]
    canceled = AttendeeSignupFactory(
        submission=submission, state=AttendeeSignupStates.CANCELED
    )
    signups = submission.attendee_signups.all()

    assert state_counts(signup_set(submission)) == {
        AttendeeSignupStates.CONFIRMED: 2,
        AttendeeSignupStates.CANCELED: 1,
    }
    assert state_counts(signup_set(None)) == {
        AttendeeSignupStates.CONFIRMED: 0,
        AttendeeSignupStates.CANCELED: 0,
    }
    assert set(signup_set(submission).filter(signups)) == {*confirmed, canceled}
    assert (
        list(
            signup_set(submission, f"state={AttendeeSignupStates.CONFIRMED}").filter(
                signups
            )
        )
        == confirmed
    )


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
    other = TrackFactory(event=event)

    def track_choices(filterset):
        return [c.value for c in filterset.filters["track"].choices]

    assert track_choices(submission_set(event, limit_tracks=[mine.pk])) == [
        str(mine.pk)
    ]
    assert track_choices(submission_set(event, limit_tracks=[])) == [
        str(mine.pk),
        str(other.pk),
    ]
    assert track_choices(submission_set(event)) == [str(mine.pk), str(other.pk)]


def test_submission_state_choices_and_values_scoped_to_usable_states():
    event = EventFactory()
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, state=SubmissionStates.WITHDRAWN)
    usable = [SubmissionStates.SUBMITTED, SubmissionStates.ACCEPTED]

    filterset = submission_set(event, usable_states=usable)
    explicit = submission_set(event, "state=withdrawn", usable_states=usable)

    assert state_counts(filterset) == {
        SubmissionStates.SUBMITTED: 1,
        SubmissionStates.ACCEPTED: 0,
        "pending_state__submitted": 0,
        "pending_state__accepted": 0,
    }
    assert explicit.values["state"] == []


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

    assert counts == {str(event.cfp.default_type.pk): 1, str(sub_type.pk): 1}


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


def test_submission_tags_filter_returns_a_multiply_tagged_proposal_once():
    event = EventFactory()
    tags = [TagFactory(event=event), TagFactory(event=event)]
    submission = SubmissionFactory(event=event)
    submission.tags.set(tags)

    filterset = submission_set(event, f"tags={tags[0].pk}&tags={tags[1].pk}")

    assert [c.value for c in filterset.filters["tags"].choices] == [
        str(tags[0].pk),
        str(tags[1].pk),
    ]
    assert list(filterset.filter(event.submissions.all())) == [submission]


def test_submission_boolean_filters_narrow_both_ways():
    event = EventFactory()
    marked = SubmissionFactory(event=event, is_featured=True, do_not_record=True)
    plain = SubmissionFactory(event=event, is_featured=False, do_not_record=False)
    SubmissionInvitationFactory(submission=plain)
    submissions = event.submissions.all()

    assert list(submission_set(event, "is_featured=true").filter(submissions)) == [
        marked
    ]
    assert list(submission_set(event, "is_featured=false").filter(submissions)) == [
        plain
    ]
    assert list(submission_set(event, "do_not_record=true").filter(submissions)) == [
        marked
    ]
    assert list(
        submission_set(event, "has_pending_invitations=true").filter(submissions)
    ) == [plain]
    assert list(
        submission_set(event, "has_pending_invitations=false").filter(submissions)
    ) == [marked]


def test_requires_signup_filter_needs_the_feature_flag():
    plain = EventFactory()
    event = EventFactory(feature_flags={"attendee_signup": True})
    required = SubmissionFactory(event=event, attendee_signup_required=True)
    SubmissionFactory(event=event, attendee_signup_required=False)

    filterset = submission_set(event, "requires_signup=true")

    assert "requires_signup" not in facet_names(submission_set(plain))
    assert "requires_signup" in facet_names(filterset)
    assert list(filterset.filter(event.submissions.all())) == [required]


def test_custom_field_filters_are_grouped_under_their_own_heading():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)

    filters = submission_question_filters(
        FilterContext(
            event=event, user=make_orga_user(event, can_change_submissions=True)
        )
    )

    assert [str(f.section) for f in filters] == ["Custom fields"]
    assert filters[0].question == question
    assert submission_question_filters(FilterContext()) == []


def review_set(event, query="", max_review_count=5):
    return build(
        review_filters, query=query, event=event, max_review_count=max_review_count
    )


def test_review_count_filter_needs_more_than_one_review_in_the_event():
    event = EventFactory()

    assert "review-count" not in facet_names(review_set(event, max_review_count=1))
    assert "review-count" in facet_names(review_set(event, max_review_count=2))


@pytest.mark.parametrize(
    ("query", "expected", "narrows"),
    (
        ("", None, False),
        ("review-count=nonsense", None, False),
        ("review-count=x,y", (None, None), False),
        ("review-count=0,", (0, None), False),
        ("review-count=,5", (None, 5), False),
        ("review-count=1,", (1, None), True),
        ("review-count=,3", (None, 3), True),
        ("review-count=1,3", (1, 3), True),
    ),
)
def test_review_count_filter_parses_its_range(query, expected, narrows):
    event = EventFactory()

    filterset = review_set(event, query)

    assert filterset.values["review-count"] == expected
    assert filterset.is_set("review-count") is narrows


def test_review_count_filter_narrows_from_both_ends():
    event = EventFactory()
    quiet = SubmissionFactory(event=event)
    ReviewFactory(submission=quiet)
    busy = SubmissionFactory(event=event)
    for _ in range(3):
        ReviewFactory(submission=busy)

    # The view annotates before filtering; the filter only narrows.
    submissions = annotate_review_count(event.submissions.all())
    at_least_two = review_set(event, "review-count=2,")

    assert list(at_least_two.filter(submissions)) == [busy]
    assert [pill.label for pill in at_least_two.pills] == ["Reviews: 2–5"]
    assert list(review_set(event, "review-count=,1").filter(submissions)) == [quiet]


def test_question_filter_offers_options_and_presence():
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
    table_filter = QuestionAnswerFilter(question=question)

    markup = table_filter.render_widget([option.pk])
    by_option = build([QuestionAnswerFilter(question=question)], f"{param}={option.pk}")
    by_absence = build(
        [QuestionAnswerFilter(question=question)], f"{param}=__unanswered__"
    )

    assert [c.value for c in by_option.filters[param].choices] == [
        str(option.pk),
        "__answered__",
        "__unanswered__",
    ]
    assert table_filter.selected_values([option.pk]) == [str(option.pk)]
    assert f'value="{option.pk}" selected' in markup
    assert 'type="radio"' not in markup
    assert list(by_option.filter(event.submissions.all())) == [answered]
    assert list(by_absence.filter(event.submissions.all())) == [unanswered]


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


def test_question_filter_matches_free_text_presence_and_absence():
    event = EventFactory()
    question = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.STRING
    )
    blue = SubmissionFactory(event=event, title="Blue talk")
    AnswerFactory(question=question, submission=blue, answer="blue")
    red = SubmissionFactory(event=event, title="Red talk")
    AnswerFactory(question=question, submission=red, answer="red")
    unanswered = SubmissionFactory(event=event)
    # An answer with no submission: its NULL key must not poison the NOT IN.
    AnswerFactory(
        question=question,
        submission=None,
        speaker=SpeakerFactory(event=event),
        answer="x",
    )
    param = f"question_{question.pk}"

    def narrow(query):
        return list(
            build([QuestionAnswerFilter(question=question)], query)
            .filter(event.submissions.all())
            .order_by("title")
        )

    combined = build(
        [QuestionAnswerFilter(question=question)],
        f"{param}=__unanswered__&{param}=blue",
    )
    free_text = build([QuestionAnswerFilter(question=question)], f"{param}=blue")

    assert narrow(f"{param}=blue") == [blue]
    assert narrow(f"{param}=__answered__") == [blue, red]
    assert narrow(f"{param}=__unanswered__") == [unanswered]
    assert [pill.label for pill in combined.pills] == [
        f"{question.question}: Not answered",
        f"{question.question}: blue",
    ]
    # "Any" stays unselected while a free-text value filters, so the
    # segments never claim a state the pill contradicts.
    bound = free_text.facets[0]
    assert bound.selected_values(bound.value) == []


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


def test_question_scope_without_tracks_or_query():
    event = EventFactory(feature_flags={"use_tracks": False})
    SubmissionFactory(event=event)
    filterset = scope_set(event)
    filterset.filter(event.submissions.all())

    assert facet_names(filterset) == ["role", "submission_type"]
    assert filterset.is_active is False
