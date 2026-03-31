# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now

from pretalx.submission.forms.submission import InfoForm, SubmissionFilterForm
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TagFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_info_form_init_sets_default_submission_type():
    event = EventFactory()

    form = InfoForm(event=event)

    assert form.initial["submission_type"] == event.cfp.default_type


def test_info_form_init_sets_default_content_locale():
    event = EventFactory()

    form = InfoForm(event=event)

    assert form.initial["content_locale"] == event.locale


def test_info_form_init_preserves_existing_submission_type():
    event = EventFactory()
    extra_type = SubmissionTypeFactory(event=event)
    submission = SubmissionFactory(event=event, submission_type=extra_type)

    form = InfoForm(event=event, instance=submission)

    assert form.initial["submission_type"] == extra_type.pk


@pytest.mark.parametrize(
    ("remove", "expect_present"),
    ((True, False), (False, True)),
    ids=["removed_when_requested", "kept_by_default"],
)
def test_info_form_init_additional_speaker_presence(remove, expect_present):
    event = EventFactory()

    form = InfoForm(event=event, remove_additional_speaker=remove)

    assert ("additional_speaker" in form.fields) is expect_present


def test_info_form_init_readonly_disables_all_fields():
    event = EventFactory()

    form = InfoForm(event=event, readonly=True)

    for field in form.fields.values():
        assert field.disabled is True


def test_info_form_init_abstract_do_not_ask_removes_field():
    event = EventFactory(cfp__fields={"abstract": {"visibility": "do_not_ask"}})

    form = InfoForm(event=event)

    assert "abstract" not in form.fields


def test_info_form_init_field_configuration_reorders_fields():
    event = EventFactory()
    field_config = [{"key": "notes"}, {"key": "title"}, {"key": "abstract"}]

    form = InfoForm(event=event, field_configuration=field_config)

    keys = list(form.fields.keys())
    assert keys.index("notes") < keys.index("title") < keys.index("abstract")


def _tracks_event(visibility="required"):
    return EventFactory(
        feature_flags={"use_tracks": True},
        cfp__fields={"track": {"visibility": visibility}},
    )


def test_info_form_set_track_removes_field_when_tracks_disabled():
    event = EventFactory(
        feature_flags={"use_tracks": False},
        cfp__fields={"track": {"visibility": "required"}},
    )

    form = InfoForm(event=event)

    assert "track" not in form.fields


def test_info_form_set_track_removes_field_when_instance_not_submitted():
    event = _tracks_event()
    TrackFactory(event=event)
    TrackFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    form = InfoForm(event=event, instance=submission)

    assert "track" not in form.fields


def test_info_form_set_track_excludes_access_code_tracks():
    event = _tracks_event()
    public1 = TrackFactory(event=event, requires_access_code=False)
    public2 = TrackFactory(event=event, requires_access_code=False)
    TrackFactory(event=event, requires_access_code=True)

    form = InfoForm(event=event)

    assert set(form.fields["track"].queryset) == {public1, public2}


def test_info_form_set_track_single_required_track_becomes_default():
    event = _tracks_event()
    track = TrackFactory(event=event, requires_access_code=False)

    form = InfoForm(event=event)

    assert "track" not in form.fields
    assert form.default_values.get("track") == track


def test_info_form_set_track_with_access_code_tracks():
    event = _tracks_event()
    code_track1 = TrackFactory(event=event)
    code_track2 = TrackFactory(event=event)
    TrackFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.tracks.add(code_track1, code_track2)

    form = InfoForm(event=event, access_code=access_code)

    assert set(form.fields["track"].queryset) == {code_track1, code_track2}


def test_info_form_init_access_code_sets_initial_track():
    event = _tracks_event()
    code_track = TrackFactory(event=event)
    TrackFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.tracks.add(code_track)

    form = InfoForm(event=event, access_code=access_code)

    assert form.initial.get("track") == code_track


def test_info_form_set_track_preserves_restricted_track_on_instance():
    event = _tracks_event()
    restricted_track = TrackFactory(event=event, requires_access_code=True)
    public_track = TrackFactory(event=event, requires_access_code=False)
    submission = SubmissionFactory(
        event=event, track=restricted_track, state=SubmissionStates.SUBMITTED
    )

    form = InfoForm(event=event, instance=submission)

    assert set(form.fields["track"].queryset) == {restricted_track, public_track}


def test_info_form_set_submission_types_locks_for_non_submitted_existing():
    submission = SubmissionFactory(state=SubmissionStates.ACCEPTED)

    form = InfoForm(event=submission.event, instance=submission)

    assert form.fields["submission_type"].disabled is True
    assert list(form.fields["submission_type"].queryset) == [submission.submission_type]


def test_info_form_set_submission_types_single_type_becomes_default():
    event = EventFactory()

    form = InfoForm(event=event)

    assert "submission_type" not in form.fields
    assert form.default_values["submission_type"] == event.cfp.default_type


def test_info_form_set_submission_types_access_code_with_types():
    event = EventFactory()
    code_type1 = SubmissionTypeFactory(event=event)
    code_type2 = SubmissionTypeFactory(event=event)
    SubmissionTypeFactory(event=event)  # not in the access code
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.submission_types.add(code_type1, code_type2)

    form = InfoForm(event=event, access_code=access_code)

    assert set(form.fields["submission_type"].queryset) == {code_type1, code_type2}


def test_info_form_set_submission_types_access_code_without_types():
    event = EventFactory()
    SubmissionTypeFactory(event=event, requires_access_code=True)
    access_code = SubmitterAccessCodeFactory(event=event)

    form = InfoForm(event=event, access_code=access_code)

    assert "submission_type" not in form.fields
    assert form.default_values["submission_type"] == event.cfp.default_type


def test_info_form_set_submission_types_after_deadline_only_type_specific():
    past = now() - dt.timedelta(days=1)
    future = now() + dt.timedelta(days=1)
    event = EventFactory(cfp__deadline=past)
    future_type1 = SubmissionTypeFactory(event=event, deadline=future)
    future_type2 = SubmissionTypeFactory(event=event, deadline=future)
    SubmissionTypeFactory(event=event, deadline=past)

    form = InfoForm(event=event)

    assert set(form.fields["submission_type"].queryset) == {future_type1, future_type2}


def test_info_form_set_submission_types_duration_help_text():
    event = EventFactory(cfp__fields={"duration": {"visibility": "optional"}})
    SubmissionTypeFactory(event=event)

    form = InfoForm(event=event)

    assert "duration" in form.fields
    assert "default duration" in str(form.fields["duration"].help_text)


def test_info_form_set_submission_types_multiple_types_shown():
    event = EventFactory()
    SubmissionTypeFactory(event=event)

    form = InfoForm(event=event)

    assert "submission_type" in form.fields
    assert form.fields["submission_type"].queryset.count() == 2


def test_info_form_set_locales_do_not_ask_skips():
    event = EventFactory(cfp__fields={"content_locale": {"visibility": "do_not_ask"}})

    form = InfoForm(event=event)

    assert "content_locale" not in form.fields


def test_info_form_set_locales_single_locale_becomes_default():
    event = EventFactory()

    form = InfoForm(event=event)

    assert "content_locale" not in form.fields
    assert form.default_values["content_locale"] == event.content_locales[0]


def test_info_form_set_locales_multiple_locales_shows_field():
    event = EventFactory(content_locale_array="en,de")

    form = InfoForm(event=event)

    assert "content_locale" in form.fields
    locale_codes = [code for code, _ in form.fields["content_locale"].choices]
    assert "en" in locale_codes
    assert "de" in locale_codes


def test_info_form_set_slot_count_removed_when_feature_disabled():
    event = EventFactory()

    form = InfoForm(event=event)

    assert "slot_count" not in form.fields


@pytest.mark.parametrize(
    ("state", "expect_disabled"),
    ((SubmissionStates.ACCEPTED, True), (SubmissionStates.SUBMITTED, False)),
    ids=["disabled_for_accepted", "enabled_for_submitted"],
)
def test_info_form_set_slot_count_disabled_by_state(state, expect_disabled):
    event = EventFactory(feature_flags={"present_multiple_times": True})
    submission = SubmissionFactory(event=event, state=state)

    form = InfoForm(event=event, instance=submission)

    assert "slot_count" in form.fields
    assert form.fields["slot_count"].disabled is expect_disabled


def _tags_event(visibility="optional"):
    return EventFactory(
        cfp__fields={"tags": {"visibility": visibility, "min": None, "max": None}}
    )


def test_info_form_set_tags_removed_when_no_public_tags():
    event = _tags_event()
    TagFactory(event=event, is_public=False)

    form = InfoForm(event=event)

    assert "tags" not in form.fields


def test_info_form_set_tags_shows_public_tags():
    event = _tags_event()
    public_tag = TagFactory(event=event, is_public=True)
    TagFactory(event=event, is_public=False)

    form = InfoForm(event=event)

    assert "tags" in form.fields
    assert list(form.fields["tags"].queryset) == [public_tag]


def test_info_form_set_tags_initial_from_instance():
    event = _tags_event()
    public_tag = TagFactory(event=event, is_public=True)
    private_tag = TagFactory(event=event, is_public=False)
    submission = SubmissionFactory(event=event)
    submission.tags.add(public_tag, private_tag)

    form = InfoForm(event=event, instance=submission)

    assert set(form.initial["tags"]) == {public_tag}


def test_info_form_clean_additional_speaker_empty_returns_empty_list():
    event = EventFactory()
    data = {"title": "Talk", "additional_speaker": ""}

    form = InfoForm(event=event, data=data)
    form.is_valid()

    assert form.cleaned_data.get("additional_speaker") == []


def test_info_form_clean_additional_speaker_valid_emails():
    event = EventFactory()
    data = {"title": "Talk", "additional_speaker": "a@example.com, b@example.com"}

    form = InfoForm(event=event, data=data)
    form.is_valid()

    emails = form.cleaned_data.get("additional_speaker", [])
    assert set(emails) == {"a@example.com", "b@example.com"}


def test_info_form_clean_additional_speaker_invalid_email_raises_error():
    event = EventFactory()
    data = {"title": "Talk", "additional_speaker": "valid@example.com, not-an-email"}

    form = InfoForm(event=event, data=data)

    assert not form.is_valid()
    assert "additional_speaker" in form.errors


def test_info_form_clean_additional_speaker_skips_empty_between_commas():
    """Empty strings from splitting (e.g. trailing comma) are skipped."""
    event = EventFactory()
    data = {"title": "Talk", "additional_speaker": "a@example.com,,b@example.com,"}

    form = InfoForm(event=event, data=data)
    form.is_valid()

    assert set(form.cleaned_data.get("additional_speaker", [])) == {
        "a@example.com",
        "b@example.com",
    }


def test_info_form_clean_additional_speaker_max_speakers_exceeded():
    """For new submissions, existing_speakers defaults to 1 (the submitter)."""
    event = EventFactory(
        cfp__fields={"additional_speaker": {"visibility": "optional", "max": 2}}
    )
    data = {"title": "Talk", "additional_speaker": "a@example.com, b@example.com"}

    form = InfoForm(event=event, data=data)

    # 1 (submitter) + 2 emails = 3 > max 2
    assert not form.is_valid()
    assert "additional_speaker" in form.errors


def test_info_form_clean_additional_speaker_deduplicates():
    event = EventFactory()
    data = {"title": "Talk", "additional_speaker": "a@example.com\na@example.com"}

    form = InfoForm(event=event, data=data)
    form.is_valid()

    assert form.cleaned_data.get("additional_speaker") == ["a@example.com"]


def test_info_form_clean_additional_speaker_lowercases():
    event = EventFactory()
    data = {"title": "Talk", "additional_speaker": "A@Example.COM"}

    form = InfoForm(event=event, data=data)
    form.is_valid()

    assert form.cleaned_data.get("additional_speaker") == ["a@example.com"]


def test_info_form_clean_additional_speaker_within_max_speakers_limit():
    event = EventFactory(
        cfp__fields={"additional_speaker": {"visibility": "optional", "max": 3}}
    )
    data = {
        "title": "Talk",
        "abstract": "An abstract",
        "additional_speaker": "a@example.com",
    }

    form = InfoForm(event=event, data=data)

    assert form.is_valid(), form.errors
    assert form.cleaned_data["additional_speaker"] == ["a@example.com"]


def test_info_form_clean_additional_speaker_max_speakers_with_existing_instance():
    """max_speakers counts existing speakers on a saved submission instance."""
    event = EventFactory(
        cfp__fields={"additional_speaker": {"visibility": "optional", "max": 2}}
    )
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    data = {
        "title": "Talk",
        "abstract": "An abstract",
        "additional_speaker": "new@example.com",
    }

    form = InfoForm(event=event, instance=submission, data=data)
    # 1 existing speaker + 1 new email = 2 <= max 2
    assert form.is_valid(), form.errors


def test_info_form_clean_tags_preserves_private_tags():
    event = _tags_event()
    public_tag = TagFactory(event=event, is_public=True)
    private_tag = TagFactory(event=event, is_public=False)
    submission = SubmissionFactory(event=event)
    submission.tags.add(public_tag, private_tag)
    data = {"title": "Talk", "tags": [public_tag.pk]}

    form = InfoForm(event=event, instance=submission, data=data)
    form.is_valid()

    assert set(form.cleaned_data.get("tags", set())) == {public_tag, private_tag}


def test_info_form_clean_tags_without_instance():
    event = _tags_event()
    public_tag = TagFactory(event=event, is_public=True)
    data = {"title": "Talk", "abstract": "An abstract", "tags": [public_tag.pk]}

    form = InfoForm(event=event, data=data)
    form.is_valid()

    assert form.cleaned_data.get("tags") == {public_tag}


def test_info_form_save_applies_default_values():
    event = EventFactory()
    data = {"title": "My Talk", "abstract": "An abstract"}

    form = InfoForm(event=event, data=data)
    assert form.is_valid(), form.errors
    form.instance.event = event
    result = form.save()

    assert result.pk is not None
    assert result.submission_type == event.cfp.default_type
    assert result.content_locale == event.content_locales[0]


def test_info_form_save_with_image_field_hidden():
    event = EventFactory(cfp__fields={"image": {"visibility": "do_not_ask"}})
    submission = SubmissionFactory(event=event)
    data = {"title": "Updated", "abstract": "An abstract"}

    form = InfoForm(event=event, instance=submission, data=data)
    assert form.is_valid(), form.errors
    result = form.save()

    assert result.title == "Updated"
    assert "image" not in form.cleaned_data


def test_info_form_init_access_code_sets_initial_submission_type():
    event = EventFactory()
    code_type = SubmissionTypeFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.submission_types.add(code_type)

    form = InfoForm(event=event, access_code=access_code)

    assert form.initial["submission_type"] == code_type


def test_submission_filter_form_init_sets_state_choices():
    event = EventFactory()

    form = SubmissionFilterForm(event=event)

    state_values = [choice[0] for choice in form.fields["state"].choices]
    assert "submitted" in state_values
    assert "accepted" in state_values


def test_submission_filter_form_init_excludes_draft_from_state_choices():
    event = EventFactory()

    form = SubmissionFilterForm(event=event)

    state_values = [choice[0] for choice in form.fields["state"].choices]
    assert SubmissionStates.DRAFT not in state_values


@pytest.mark.parametrize(
    ("extra_types", "expect_present"),
    ((0, False), (1, True)),
    ids=["single_type_removed", "multiple_types_shown"],
)
def test_submission_filter_form_init_submission_type_presence(
    extra_types, expect_present
):
    event = EventFactory()
    for _ in range(extra_types):
        SubmissionTypeFactory(event=event)

    form = SubmissionFilterForm(event=event)

    assert ("submission_type" in form.fields) is expect_present


def test_submission_filter_form_init_removes_track_when_single_and_required():
    event = EventFactory(
        feature_flags={"use_tracks": True},
        cfp__fields={"track": {"visibility": "required"}},
    )
    TrackFactory(event=event)

    form = SubmissionFilterForm(event=event)

    assert "track" not in form.fields


def test_submission_filter_form_init_shows_track_when_multiple():
    event = EventFactory()
    TrackFactory(event=event)
    TrackFactory(event=event)

    form = SubmissionFilterForm(event=event)

    assert "track" in form.fields


@pytest.mark.parametrize(
    ("locales", "expect_present"),
    (("en", False), ("en,de", True)),
    ids=["single_locale_removed", "multiple_locales_shown"],
)
def test_submission_filter_form_init_content_locale_presence(locales, expect_present):
    event = EventFactory(content_locale_array=locales)

    form = SubmissionFilterForm(event=event)

    assert ("content_locale" in form.fields) is expect_present


@pytest.mark.parametrize(
    ("tag_count", "expect_present"),
    ((0, False), (1, True)),
    ids=["no_tags_removed", "has_tags_shown"],
)
def test_submission_filter_form_init_tags_presence(tag_count, expect_present):
    event = EventFactory()
    for _ in range(tag_count):
        TagFactory(event=event)

    form = SubmissionFilterForm(event=event)

    assert ("tags" in form.fields) is expect_present


def test_submission_filter_form_init_question_queryset_scoped_to_event():
    event = EventFactory()
    question = QuestionFactory(event=event)
    QuestionFactory()  # different event

    form = SubmissionFilterForm(event=event)

    assert list(form.fields["question"].queryset) == [question]


def test_submission_filter_form_init_usable_states_limits_choices():
    event = EventFactory()

    form = SubmissionFilterForm(event=event, usable_states=["submitted", "accepted"])

    state_values = [
        choice[0]
        for choice in form.fields["state"].choices
        if not str(choice[0]).startswith("pending_state__")
    ]
    assert set(state_values) == {"submitted", "accepted"}


def test_submission_filter_form_init_includes_pending_state_choices():
    event = EventFactory()

    form = SubmissionFilterForm(event=event)

    state_values = [choice[0] for choice in form.fields["state"].choices]
    regular_states = [
        s for s in state_values if not str(s).startswith("pending_state__")
    ]
    pending_states = [s for s in state_values if str(s).startswith("pending_state__")]
    assert len(pending_states) == len(regular_states)


def test_submission_filter_form_init_state_count_reflects_submissions():
    event = EventFactory()
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    form = SubmissionFilterForm(event=event)

    state_dict = {choice[0]: choice[1] for choice in form.fields["state"].choices}
    assert state_dict["submitted"].count == 2
    assert state_dict["accepted"].count == 1


def test_submission_filter_form_init_limit_tracks():
    event = EventFactory()
    track1 = TrackFactory(event=event)
    TrackFactory(event=event)

    form = SubmissionFilterForm(event=event, limit_tracks=[track1])

    assert list(form.fields["track"].queryset) == [track1]


def test_submission_filter_form_filter_question_by_answer():
    event = EventFactory()
    question = QuestionFactory(event=event)
    matching_sub = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=matching_sub, answer="yes")
    non_matching_sub = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=non_matching_sub, answer="no")

    form = SubmissionFilterForm(
        event=event, data={"question": question.pk, "answer": "yes"}
    )
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {matching_sub}


def test_submission_filter_form_filter_question_by_option():
    event = EventFactory()
    question = QuestionFactory(event=event, variant="choices")
    option = AnswerOptionFactory(question=question)
    matching_sub = SubmissionFactory(event=event)
    answer = AnswerFactory(question=question, submission=matching_sub)
    answer.options.add(option)
    SubmissionFactory(event=event)  # non-matching submission without the option

    form = SubmissionFilterForm(
        event=event, data={"question": question.pk, "answer__options": option.pk}
    )
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {matching_sub}


def test_submission_filter_form_filter_question_unanswered():
    event = EventFactory()
    question = QuestionFactory(event=event)
    answered_sub = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=answered_sub)
    unanswered_sub = SubmissionFactory(event=event)

    form = SubmissionFilterForm(
        event=event, data={"question": question.pk, "unanswered": True}
    )
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {unanswered_sub}


def test_submission_filter_form_filter_queryset_by_state():
    event = EventFactory()
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    form = SubmissionFilterForm(event=event, data={"state": ["submitted"]})
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {submitted}


def test_submission_filter_form_filter_queryset_by_pending_state():
    event = EventFactory()
    pending_sub = SubmissionFactory(
        event=event,
        state=SubmissionStates.SUBMITTED,
        pending_state=SubmissionStates.ACCEPTED,
    )
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    form = SubmissionFilterForm(
        event=event, data={"state": ["pending_state__accepted"]}
    )
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {pending_sub}


def test_submission_filter_form_filter_queryset_mixed_state_and_pending():
    event = EventFactory()
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    pending = SubmissionFactory(
        event=event,
        state=SubmissionStates.SUBMITTED,
        pending_state=SubmissionStates.ACCEPTED,
    )
    SubmissionFactory(event=event, state=SubmissionStates.REJECTED)

    form = SubmissionFilterForm(
        event=event, data={"state": ["submitted", "pending_state__accepted"]}
    )
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {submitted, pending}


def test_submission_filter_form_filter_queryset_exclude_pending():
    event = EventFactory()
    no_pending = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(
        event=event,
        state=SubmissionStates.SUBMITTED,
        pending_state=SubmissionStates.ACCEPTED,
    )

    form = SubmissionFilterForm(event=event, data={"pending_state__isnull": True})
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {no_pending}


def test_submission_filter_form_filter_queryset_by_submission_type():
    event = EventFactory()
    extra_type = SubmissionTypeFactory(event=event)
    matching = SubmissionFactory(event=event, submission_type=extra_type)
    SubmissionFactory(event=event)

    form = SubmissionFilterForm(event=event, data={"submission_type": [extra_type.pk]})
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {matching}


def test_submission_filter_form_filter_queryset_by_track():
    event = EventFactory()
    track = TrackFactory(event=event)
    TrackFactory(event=event)
    matching = SubmissionFactory(event=event, track=track)
    SubmissionFactory(event=event)

    form = SubmissionFilterForm(event=event, data={"track": [track.pk]})
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {matching}


def test_submission_filter_form_filter_queryset_by_content_locale():
    event = EventFactory(content_locale_array="en,de")
    en_sub = SubmissionFactory(event=event, content_locale="en")
    SubmissionFactory(event=event, content_locale="de")

    form = SubmissionFilterForm(event=event, data={"content_locale": ["en"]})
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {en_sub}


def test_submission_filter_form_filter_queryset_by_tags():
    event = EventFactory()
    tag = TagFactory(event=event)
    matching = SubmissionFactory(event=event)
    matching.tags.add(tag)
    SubmissionFactory(event=event)

    form = SubmissionFilterForm(event=event, data={"tags": [tag.pk]})
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {matching}


def test_submission_filter_form_filter_queryset_search():
    event = EventFactory()
    matching = SubmissionFactory(event=event, title="Unique Searchable Title")
    SubmissionFactory(event=event, title="Something Else")

    form = SubmissionFilterForm(event=event, data={"q": "Unique Searchable"})
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {matching}


def test_submission_filter_form_filter_queryset_fulltext_search():
    """Fulltext search includes abstract, description, notes, internal_notes."""
    event = EventFactory()
    matching = SubmissionFactory(
        event=event, title="Regular Title", abstract="unique_abstract_keyword"
    )
    SubmissionFactory(event=event, title="Other")

    form = SubmissionFilterForm(
        event=event, data={"q": "unique_abstract_keyword", "fulltext": True}
    )
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {matching}


def test_submission_filter_form_filter_queryset_no_filters():
    event = EventFactory()
    sub1 = SubmissionFactory(event=event)
    sub2 = SubmissionFactory(event=event)

    form = SubmissionFilterForm(event=event, data={})
    assert form.is_valid(), form.errors

    qs = event.submissions.all()
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {sub1, sub2}


@pytest.mark.parametrize(
    ("query", "expected_key"),
    (("Specialized", "normal"), ("Redacted", "anonymised")),
    ids=["original_title_hidden", "anonymised_title_found"],
)
def test_submission_filter_form_anonymised_title_search(query, expected_key):
    """When can_view_speakers=False, search hides the original title of
    anonymised submissions but finds the anonymised title (#970)."""
    event = EventFactory()
    subs = {
        "anonymised": SubmissionFactory(
            event=event,
            title="Specialized Workshop Title",
            anonymised={"_anonymised": True, "title": "Redacted Title"},
        ),
        "normal": SubmissionFactory(event=event, title="Specialized Talk Title"),
    }

    form = SubmissionFilterForm(event=event, data={"q": query}, can_view_speakers=False)
    assert form.is_valid(), form.errors

    filtered = form.filter_queryset(event.submissions.all())

    assert set(filtered) == {subs[expected_key]}


@pytest.mark.parametrize(
    ("query", "finds_submission"),
    (("Secretive", False), ("Redacted", True)),
    ids=["original_content_hidden", "anonymised_content_found"],
)
def test_submission_filter_form_anonymised_fulltext_search(query, finds_submission):
    """When can_view_speakers=False, fulltext search hides original content of
    anonymised submissions but finds the anonymised content (#970)."""
    event = EventFactory()
    sub = SubmissionFactory(
        event=event,
        abstract="Secretive abstract content",
        anonymised={"_anonymised": True, "abstract": "Redacted abstract"},
    )

    form = SubmissionFilterForm(
        event=event, data={"q": query, "fulltext": True}, can_view_speakers=False
    )
    assert form.is_valid(), form.errors

    filtered = form.filter_queryset(event.submissions.all())

    assert set(filtered) == ({sub} if finds_submission else set())


@pytest.mark.parametrize(
    ("query", "fulltext", "finds_submission"),
    (("Unique", True, True), ("Original", False, False)),
    ids=["unredacted_field_found", "redacted_field_hidden"],
)
def test_submission_filter_form_partial_anonymisation_search(
    query, fulltext, finds_submission
):
    """When only the title is anonymised, un-redacted fields remain searchable
    but the redacted title is protected (#970)."""
    event = EventFactory()
    sub = SubmissionFactory(
        event=event,
        title="Original Title",
        description="Unique description content",
        anonymised={"_anonymised": True, "title": "Redacted Title"},
    )

    data = {"q": query}
    if fulltext:
        data["fulltext"] = True
    form = SubmissionFilterForm(event=event, data=data, can_view_speakers=False)
    assert form.is_valid(), form.errors

    filtered = form.filter_queryset(event.submissions.all())

    assert set(filtered) == ({sub} if finds_submission else set())


def test_submission_filter_form_can_view_speakers_searches_original_title():
    """When can_view_speakers=True, search uses the original title even for
    anonymised submissions (organiser view)."""
    event = EventFactory()
    anonymised_sub = SubmissionFactory(
        event=event,
        title="Specialized Workshop Title",
        anonymised={"_anonymised": True, "title": "Redacted Title"},
    )

    form = SubmissionFilterForm(
        event=event, data={"q": "Specialized"}, can_view_speakers=True
    )
    assert form.is_valid(), form.errors

    filtered = form.filter_queryset(event.submissions.all())

    assert set(filtered) == {anonymised_sub}


def test_submission_filter_form_anonymised_search_empty_search_fields():
    """When search_fields is empty, _anonymised_search returns the queryset unchanged."""
    event = EventFactory()
    sub = SubmissionFactory(event=event, title="Some Title")
    qs = event.submissions.all()

    result = SubmissionFilterForm._anonymised_search(qs, "Some", search_fields=())

    assert set(result) == {sub}
