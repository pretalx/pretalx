# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.person.domain.queries.profile import (
    annotate_speaker_submission_counts,
    annotate_user_submission_counts,
)
from pretalx.person.interfaces.forms import SpeakerFilterForm, UserSpeakerFilterForm
from pretalx.person.models import SpeakerProfile, User
from tests.factories import (
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_speaker_filter_form_init_sets_question_queryset():
    event = EventFactory()
    question = QuestionFactory(event=event)
    QuestionFactory()  # different event

    form = SpeakerFilterForm(event=event)

    assert list(form.fields["question"].queryset) == [question]


@pytest.mark.parametrize(
    ("filter_arrival", "expect_present"), ((False, False), (True, True))
)
def test_speaker_filter_form_init_arrived_field_presence(
    filter_arrival, expect_present
):
    event = EventFactory()

    form = SpeakerFilterForm(event=event, filter_arrival=filter_arrival)

    assert ("arrived" in form.fields) is expect_present


def test_speaker_filter_form_filter_queryset_speaker_role_filters_accepted():
    event = EventFactory()
    speaker_with_accepted = SpeakerFactory(event=event)
    accepted_sub = SubmissionFactory(event=event, state="accepted")
    accepted_sub.speakers.add(speaker_with_accepted)
    speaker_without = SpeakerFactory(event=event)
    rejected_sub = SubmissionFactory(event=event, state="rejected")
    rejected_sub.speakers.add(speaker_without)

    form = SpeakerFilterForm(data={"role": "speaker"}, event=event)
    assert form.is_valid(), form.errors

    qs = annotate_speaker_submission_counts(
        SpeakerProfile.objects.filter(event=event), event=event
    )
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {speaker_with_accepted}


def test_speaker_filter_form_filter_queryset_submitter_role_excludes_accepted():
    event = EventFactory()
    speaker_accepted = SpeakerFactory(event=event)
    accepted_sub = SubmissionFactory(event=event, state="accepted")
    accepted_sub.speakers.add(speaker_accepted)
    speaker_rejected = SpeakerFactory(event=event)
    rejected_sub = SubmissionFactory(event=event, state="rejected")
    rejected_sub.speakers.add(speaker_rejected)

    form = SpeakerFilterForm(data={"role": "submitter"}, event=event)
    assert form.is_valid(), form.errors

    qs = annotate_speaker_submission_counts(
        SpeakerProfile.objects.filter(event=event), event=event
    )
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {speaker_rejected}


@pytest.mark.parametrize(
    ("filter_value", "expect_arrived"), (("true", True), ("false", False))
)
def test_speaker_filter_form_filter_queryset_arrived(filter_value, expect_arrived):
    event = EventFactory()
    arrived = SpeakerFactory(event=event, has_arrived=True)
    not_arrived = SpeakerFactory(event=event, has_arrived=False)

    form = SpeakerFilterForm(
        data={"arrived": filter_value}, event=event, filter_arrival=True
    )
    assert form.is_valid(), form.errors

    qs = annotate_speaker_submission_counts(
        SpeakerProfile.objects.filter(event=event), event=event
    )
    filtered = form.filter_queryset(qs)

    expected = {arrived} if expect_arrived else {not_arrived}
    assert set(filtered) == expected


def test_speaker_filter_form_filter_queryset_no_filters():
    event = EventFactory()
    speaker1 = SpeakerFactory(event=event)
    speaker2 = SpeakerFactory(event=event)

    form = SpeakerFilterForm(data={}, event=event)
    assert form.is_valid(), form.errors

    qs = annotate_speaker_submission_counts(
        SpeakerProfile.objects.filter(event=event), event=event
    )
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {speaker1, speaker2}


def test_user_speaker_filter_form_init_shows_events_field_for_multiple_events():
    event1 = EventFactory()
    event2 = EventFactory()
    events = EventFactory._meta.model.objects.filter(pk__in=[event1.pk, event2.pk])

    form = UserSpeakerFilterForm(events=events)

    assert "events" in form.fields


def test_user_speaker_filter_form_init_hides_events_field_for_single_event():
    event = EventFactory()
    events = EventFactory._meta.model.objects.filter(pk=event.pk)

    form = UserSpeakerFilterForm(events=events)

    assert "events" not in form.fields


@pytest.mark.parametrize(
    ("role", "expect_speaker", "expect_submitter"),
    (("speaker", True, False), ("submitter", False, True)),
)
def test_user_speaker_filter_form_filter_queryset_by_role(
    role, expect_speaker, expect_submitter
):
    event = EventFactory()
    speaker_user = UserFactory()
    SpeakerFactory(user=speaker_user, event=event)
    accepted_sub = SubmissionFactory(event=event, state="accepted")
    accepted_sub.speakers.add(speaker_user.profiles.first())

    submitter_user = UserFactory()
    SpeakerFactory(user=submitter_user, event=event)
    rejected_sub = SubmissionFactory(event=event, state="rejected")
    rejected_sub.speakers.add(submitter_user.profiles.first())

    events = EventFactory._meta.model.objects.filter(pk=event.pk)
    form = UserSpeakerFilterForm(data={"role": role}, events=events)
    assert form.is_valid(), form.errors

    qs = annotate_user_submission_counts(
        User.objects.filter(profiles__event=event), events=[event]
    )
    filtered = form.filter_queryset(qs)

    expected = set()
    if expect_speaker:
        expected.add(speaker_user)
    if expect_submitter:
        expected.add(submitter_user)
    assert set(filtered) == expected


def test_user_speaker_filter_form_filter_queryset_all_role():
    event = EventFactory()
    speaker_user = UserFactory()
    SpeakerFactory(user=speaker_user, event=event)
    accepted_sub = SubmissionFactory(event=event, state="accepted")
    accepted_sub.speakers.add(speaker_user.profiles.first())

    submitter_user = UserFactory()
    SpeakerFactory(user=submitter_user, event=event)

    events = EventFactory._meta.model.objects.filter(pk=event.pk)
    form = UserSpeakerFilterForm(data={"role": "all"}, events=events)
    assert form.is_valid(), form.errors

    qs = annotate_user_submission_counts(
        User.objects.filter(profiles__event=event), events=[event]
    )
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {speaker_user, submitter_user}


def test_user_speaker_filter_form_filter_queryset_filters_by_events():
    event1 = EventFactory()
    event2 = EventFactory()
    user1 = UserFactory()
    SpeakerFactory(user=user1, event=event1)
    user2 = UserFactory()
    SpeakerFactory(user=user2, event=event2)

    events = EventFactory._meta.model.objects.filter(pk__in=[event1.pk, event2.pk])
    form = UserSpeakerFilterForm(
        data={"role": "all", "events": [event1.pk]}, events=events
    )
    assert form.is_valid(), form.errors

    qs = annotate_user_submission_counts(
        User.objects.filter(profiles__event__in=[event1, event2]),
        events=[event1, event2],
    )
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {user1}
