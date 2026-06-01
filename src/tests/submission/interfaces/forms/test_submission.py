# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now

from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.schedule.models import TalkSlot
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.interfaces.forms import (
    AnonymiseForm,
    InfoForm,
    SubmissionFilterForm,
    SubmissionInfoForm,
    SubmissionOrgaForm,
    SubmissionSignupFilterForm,
    SubmissionSignupForm,
)
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    AttendeeSignupFactory,
    EventFactory,
    QuestionFactory,
    RoomFactory,
    SubmissionFactory,
    SubmissionInvitationFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TagFactory,
    TalkSlotFactory,
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


def test_info_form_has_additional_speaker_field():
    event = EventFactory()

    form = InfoForm(event=event)

    assert "additional_speaker" in form.fields


def test_submission_info_form_has_no_additional_speaker_field():
    event = EventFactory()

    form = SubmissionInfoForm(event=event)

    assert "additional_speaker" not in form.fields


def test_info_form_init_prefills_additional_speaker_from_draft_additional_speakers():
    event = EventFactory()
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.DRAFT,
        draft_additional_speakers=["a@example.com", "b@example.com"],
    )

    form = InfoForm(event=event, instance=submission)

    assert form.initial["additional_speaker"] == "a@example.com, b@example.com"


def test_info_form_init_draft_additional_speakers_does_not_override_explicit_initial():
    event = EventFactory()
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.DRAFT,
        draft_additional_speakers=["a@example.com"],
    )

    form = InfoForm(
        event=event,
        instance=submission,
        initial={"additional_speaker": "override@example.com"},
    )

    assert form.initial["additional_speaker"] == "override@example.com"


def test_info_form_init_readonly_disables_all_fields():
    event = EventFactory()

    form = InfoForm(event=event, read_only=True)

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


def test_info_form_configure_track_removes_field_when_tracks_disabled():
    event = EventFactory(
        feature_flags={"use_tracks": False},
        cfp__fields={"track": {"visibility": "required"}},
    )

    form = InfoForm(event=event)

    assert "track" not in form.fields


def test_info_form_configure_track_removes_field_when_instance_not_submitted():
    event = _tracks_event()
    TrackFactory(event=event)
    TrackFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    form = InfoForm(event=event, instance=submission)

    assert "track" not in form.fields


def test_info_form_configure_track_excludes_access_code_tracks():
    event = _tracks_event()
    public1 = TrackFactory(event=event, requires_access_code=False)
    public2 = TrackFactory(event=event, requires_access_code=False)
    TrackFactory(event=event, requires_access_code=True)

    form = InfoForm(event=event)

    assert set(form.fields["track"].queryset) == {public1, public2}


def test_info_form_configure_track_single_required_track_becomes_default():
    event = _tracks_event()
    track = TrackFactory(event=event, requires_access_code=False)

    form = InfoForm(event=event)

    assert "track" not in form.fields
    assert form.default_values.get("track") == track


def test_info_form_configure_track_with_access_code_tracks():
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


def test_info_form_configure_track_preserves_restricted_track_on_instance():
    event = _tracks_event()
    restricted_track = TrackFactory(event=event, requires_access_code=True)
    public_track = TrackFactory(event=event, requires_access_code=False)
    submission = SubmissionFactory(
        event=event, track=restricted_track, state=SubmissionStates.SUBMITTED
    )

    form = InfoForm(event=event, instance=submission)

    assert set(form.fields["track"].queryset) == {restricted_track, public_track}


def test_info_form_configure_submission_types_locks_for_non_submitted_existing():
    submission = SubmissionFactory(state=SubmissionStates.ACCEPTED)

    form = InfoForm(event=submission.event, instance=submission)

    assert form.fields["submission_type"].disabled is True
    assert list(form.fields["submission_type"].queryset) == [submission.submission_type]


def test_info_form_configure_submission_types_single_type_becomes_default():
    event = EventFactory()

    form = InfoForm(event=event)

    assert "submission_type" not in form.fields
    assert form.default_values["submission_type"] == event.cfp.default_type


def test_info_form_configure_submission_types_access_code_with_types():
    event = EventFactory()
    code_type1 = SubmissionTypeFactory(event=event)
    code_type2 = SubmissionTypeFactory(event=event)
    SubmissionTypeFactory(event=event)  # not in the access code
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.submission_types.add(code_type1, code_type2)

    form = InfoForm(event=event, access_code=access_code)

    assert set(form.fields["submission_type"].queryset) == {code_type1, code_type2}


def test_info_form_configure_submission_types_access_code_without_types():
    event = EventFactory()
    SubmissionTypeFactory(event=event, requires_access_code=True)
    access_code = SubmitterAccessCodeFactory(event=event)

    form = InfoForm(event=event, access_code=access_code)

    assert "submission_type" not in form.fields
    assert form.default_values["submission_type"] == event.cfp.default_type


def test_info_form_configure_submission_types_after_deadline_only_type_specific():
    past = now() - dt.timedelta(days=1)
    future = now() + dt.timedelta(days=1)
    event = EventFactory(cfp__deadline=past)
    future_type1 = SubmissionTypeFactory(event=event, deadline=future)
    future_type2 = SubmissionTypeFactory(event=event, deadline=future)
    SubmissionTypeFactory(event=event, deadline=past)

    form = InfoForm(event=event)

    assert set(form.fields["submission_type"].queryset) == {future_type1, future_type2}


def test_info_form_configure_submission_types_duration_help_text():
    event = EventFactory(cfp__fields={"duration": {"visibility": "optional"}})
    SubmissionTypeFactory(event=event)

    form = InfoForm(event=event)

    assert "duration" in form.fields
    assert "default duration" in str(form.fields["duration"].help_text)


def test_info_form_configure_submission_types_multiple_types_shown():
    event = EventFactory()
    SubmissionTypeFactory(event=event)

    form = InfoForm(event=event)

    assert "submission_type" in form.fields
    assert form.fields["submission_type"].queryset.count() == 2


def test_info_form_configure_locales_do_not_ask_skips():
    event = EventFactory(cfp__fields={"content_locale": {"visibility": "do_not_ask"}})

    form = InfoForm(event=event)

    assert "content_locale" not in form.fields


def test_info_form_configure_locales_single_locale_becomes_default():
    event = EventFactory()

    form = InfoForm(event=event)

    assert "content_locale" not in form.fields
    assert form.default_values["content_locale"] == event.content_locales[0]


def test_info_form_configure_locales_multiple_locales_shows_field():
    event = EventFactory(content_locale_array="en,de")

    form = InfoForm(event=event)

    assert "content_locale" in form.fields
    locale_codes = [code for code, _ in form.fields["content_locale"].choices]
    assert "en" in locale_codes
    assert "de" in locale_codes


def test_info_form_configure_slot_count_removed_when_feature_disabled():
    event = EventFactory()

    form = InfoForm(event=event)

    assert "slot_count" not in form.fields


@pytest.mark.parametrize(
    ("state", "expect_disabled"),
    ((SubmissionStates.ACCEPTED, True), (SubmissionStates.SUBMITTED, False)),
    ids=["disabled_for_accepted", "enabled_for_submitted"],
)
def test_info_form_configure_slot_count_disabled_by_state(state, expect_disabled):
    event = EventFactory(feature_flags={"present_multiple_times": True})
    submission = SubmissionFactory(event=event, state=state)

    form = InfoForm(event=event, instance=submission)

    assert "slot_count" in form.fields
    assert form.fields["slot_count"].disabled is expect_disabled


def _tags_event(visibility="optional"):
    return EventFactory(
        cfp__fields={"tags": {"visibility": visibility, "min": None, "max": None}}
    )


def test_info_form_configure_tags_removed_when_no_public_tags():
    event = _tags_event()
    TagFactory(event=event, is_public=False)

    form = InfoForm(event=event)

    assert "tags" not in form.fields


def test_info_form_configure_tags_shows_public_tags():
    event = _tags_event()
    public_tag = TagFactory(event=event, is_public=True)
    TagFactory(event=event, is_public=False)

    form = InfoForm(event=event)

    assert "tags" in form.fields
    assert list(form.fields["tags"].queryset) == [public_tag]


def test_info_form_configure_tags_initial_from_instance():
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


def test_info_form_clean_additional_speaker_caps_address_count():
    event = EventFactory()
    assert event.cfp.max_speakers is None
    addresses = ", ".join(f"victim{i}@example.com" for i in range(51))
    data = {"title": "Talk", "additional_speaker": addresses}

    form = InfoForm(event=event, data=data)

    assert not form.is_valid()
    assert "additional_speaker" in form.errors


def test_info_form_clean_additional_speaker_skips_empty_between_commas():
    event = EventFactory()
    data = {"title": "Talk", "additional_speaker": "a@example.com,,b@example.com,"}

    form = InfoForm(event=event, data=data)
    form.is_valid()

    assert set(form.cleaned_data.get("additional_speaker", [])) == {
        "a@example.com",
        "b@example.com",
    }


def test_info_form_clean_additional_speaker_delegates_to_speaker_limit_validator():
    event = EventFactory(
        cfp__fields={"additional_speaker": {"visibility": "optional", "max": 2}}
    )
    data = {"title": "Talk", "additional_speaker": "a@example.com, b@example.com"}

    form = InfoForm(event=event, data=data)

    assert not form.is_valid()
    assert "additional_speaker" in form.errors


def test_info_form_clean_additional_speaker_skips_validator_when_all_invited():
    event = EventFactory(
        cfp__fields={"additional_speaker": {"visibility": "optional", "max": 1}}
    )
    submission = SubmissionFactory(event=event)
    SubmissionInvitationFactory(submission=submission, email="invited@example.com")
    data = {"title": submission.title, "additional_speaker": "invited@example.com"}

    form = InfoForm(event=event, instance=submission, data=data)
    form.is_valid()

    assert form.cleaned_data["additional_speaker"] == ["invited@example.com"]
    assert "additional_speaker" not in form.errors


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

    form = SubmissionFilterForm(event=event, limit_tracks=frozenset({track1.pk}))

    assert list(form.fields["track"].queryset) == [track1]


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


def _orga_base_data(submission, **overrides):
    data = {
        "title": submission.title,
        "abstract": submission.abstract or "An abstract",
        "submission_type": submission.submission_type.pk,
    }
    data.update(overrides)
    return data


def _orga_new_data(event, **overrides):
    data = {
        "title": "New Talk",
        "abstract": "An abstract",
        "submission_type": event.cfp.default_type.pk,
        "state": SubmissionStates.SUBMITTED,
    }
    data.update(overrides)
    return data


def test_submission_orga_form_init_sets_submission_type_queryset(event):
    extra_type = SubmissionTypeFactory(event=event)

    form = SubmissionOrgaForm(event=event)

    assert set(form.fields["submission_type"].queryset) == {
        event.cfp.default_type,
        extra_type,
    }


def test_submission_orga_form_init_removes_tags_field_when_no_tags(event):
    form = SubmissionOrgaForm(event=event)

    assert "tags" not in form.fields


def test_submission_orga_form_init_shows_tags_field_when_tags_exist(event):
    tag = TagFactory(event=event)

    form = SubmissionOrgaForm(event=event)

    assert "tags" in form.fields
    assert list(form.fields["tags"].queryset) == [tag]
    assert form.fields["tags"].required is False


def test_submission_orga_form_init_new_adds_state_field(event):
    form = SubmissionOrgaForm(event=event)

    assert "state" in form.fields
    state_values = [choice for choice, _ in form.fields["state"].choices]
    assert SubmissionStates.SUBMITTED in state_values
    assert SubmissionStates.ACCEPTED in state_values
    assert SubmissionStates.DRAFT not in state_values


def test_submission_orga_form_init_existing_has_no_state_field(event):
    submission = SubmissionFactory(event=event)

    form = SubmissionOrgaForm(event=event, instance=submission)

    assert "state" not in form.fields


def test_submission_orga_form_init_new_adds_scheduling_fields(event):
    RoomFactory(event=event)

    form = SubmissionOrgaForm(event=event)

    assert "room" in form.fields
    assert "start" in form.fields
    assert "end" in form.fields


def test_submission_orga_form_init_accepted_submission_has_scheduling_fields(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    form = SubmissionOrgaForm(event=event, instance=submission)

    assert "room" in form.fields
    assert "start" in form.fields
    assert "end" in form.fields


def test_submission_orga_form_init_submitted_submission_has_no_scheduling_fields(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    form = SubmissionOrgaForm(event=event, instance=submission)

    assert "room" not in form.fields
    assert "start" not in form.fields
    assert "end" not in form.fields


def test_submission_orga_form_init_existing_populates_slot_initial(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    slot = TalkSlotFactory(submission=submission, is_visible=True)

    form = SubmissionOrgaForm(event=event, instance=submission)

    assert form.initial["room"] == slot.room
    assert form.initial["start"] == slot.local_start
    assert form.initial["end"] == slot.local_end


def test_submission_orga_form_init_removes_slot_count_without_feature_flag(event):
    form = SubmissionOrgaForm(event=event)

    assert "slot_count" not in form.fields


def test_submission_orga_form_init_keeps_slot_count_with_feature_flag():
    event = EventFactory(feature_flags={"present_multiple_times": True})
    form = SubmissionOrgaForm(event=event)

    assert "slot_count" in form.fields


def test_submission_orga_form_init_removes_track_without_feature_flag():
    event = EventFactory(feature_flags={"use_tracks": False})
    form = SubmissionOrgaForm(event=event)

    assert "track" not in form.fields


def test_submission_orga_form_init_keeps_track_with_feature_flag(event):
    track = TrackFactory(event=event)

    form = SubmissionOrgaForm(event=event)

    assert "track" in form.fields
    assert list(form.fields["track"].queryset) == [track]


def test_submission_orga_form_init_removes_content_locale_for_single_locale(event):
    form = SubmissionOrgaForm(event=event)

    assert "content_locale" not in form.fields


def test_submission_orga_form_init_keeps_content_locale_for_multiple_locales():
    event = EventFactory(locale_array="en,de", content_locale_array="en,de,fr")
    form = SubmissionOrgaForm(event=event)

    assert form.fields["content_locale"].choices == [
        ("en", "English"),
        ("de", "Deutsch"),
        ("fr", "Français"),
    ]


def test_submission_orga_form_init_abstract_do_not_ask_removes_field():
    event = EventFactory(cfp__fields={"abstract": {"visibility": "do_not_ask"}})

    form = SubmissionOrgaForm(event=event)

    assert "abstract" not in form.fields


def test_submission_orga_form_init_content_locale_do_not_ask_skips_locale_setup():
    event = EventFactory(
        content_locale_array="en,de",
        cfp__fields={"content_locale": {"visibility": "do_not_ask"}},
    )

    form = SubmissionOrgaForm(event=event)

    assert "content_locale" not in form.fields


def test_submission_orga_form_init_duration_help_text_with_multiple_types(event):
    SubmissionTypeFactory(event=event)

    form = SubmissionOrgaForm(event=event)

    assert "default duration" in str(form.fields["duration"].help_text)


def test_submission_orga_form_init_no_duration_help_text_with_single_type(event):
    form = SubmissionOrgaForm(event=event)

    assert "default duration" not in str(form.fields["duration"].help_text)


def test_submission_orga_form_init_abstract_rows(event):
    form = SubmissionOrgaForm(event=event)

    assert form.fields["abstract"].widget.attrs["rows"] == 2


def test_submission_orga_form_init_read_only_disables_model_fields(event):
    form = SubmissionOrgaForm(event=event, read_only=True)

    model_fields = {
        "title",
        "submission_type",
        "abstract",
        "description",
        "notes",
        "internal_notes",
        "do_not_record",
        "duration",
        "image",
        "is_featured",
    }
    for name in model_fields:
        assert name in form.fields, f"Expected field: {name}"
        assert form.fields[name].disabled is True, f"{name} should be disabled"


def test_submission_orga_form_clean_read_only_raises_validation_error(event):
    form = SubmissionOrgaForm(event=event, read_only=True, data={"title": "Test"})

    assert not form.is_valid()
    assert "__all__" in form.errors


def test_submission_orga_form_init_anonymise_uses_anonymised_data(event):
    submission = SubmissionFactory(
        event=event,
        title="Original Title",
        anonymised={"_anonymised": True, "title": "Anonymised Title"},
    )

    form = SubmissionOrgaForm(event=event, anonymise=True, instance=submission)

    assert form.initial["title"] == "Anonymised Title"


def test_submission_orga_form_init_anonymise_falls_back_to_instance_attr(event):
    submission = SubmissionFactory(
        event=event, title="Original Title", anonymised={"_anonymised": True}
    )

    form = SubmissionOrgaForm(event=event, anonymise=True, instance=submission)

    assert form.initial["title"] == "Original Title"


def test_submission_orga_form_clean_start_before_event_raises_error(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)
    early = event.datetime_from - dt.timedelta(days=1)

    form = SubmissionOrgaForm(
        event=event,
        instance=submission,
        data=_orga_base_data(
            submission,
            room=room.pk,
            start=early,
            end=event.datetime_from + dt.timedelta(hours=1),
        ),
    )

    assert not form.is_valid()
    assert "start" in form.errors


def test_submission_orga_form_clean_end_after_event_raises_error(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)
    late = event.datetime_to + dt.timedelta(days=1)

    form = SubmissionOrgaForm(
        event=event,
        instance=submission,
        data=_orga_base_data(
            submission, room=room.pk, start=event.datetime_from, end=late
        ),
    )

    assert not form.is_valid()
    assert "end" in form.errors


def test_submission_orga_form_clean_start_after_end_raises_error(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)

    form = SubmissionOrgaForm(
        event=event,
        instance=submission,
        data=_orga_base_data(
            submission,
            room=room.pk,
            start=event.datetime_from + dt.timedelta(hours=2),
            end=event.datetime_from + dt.timedelta(hours=1),
        ),
    )

    assert not form.is_valid()
    assert "end" in form.errors


def test_submission_orga_form_clean_room_without_start_raises_error(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)

    form = SubmissionOrgaForm(
        event=event, instance=submission, data=_orga_base_data(submission, room=room.pk)
    )

    assert not form.is_valid()
    assert "room" in form.errors


def test_submission_orga_form_clean_start_without_room_raises_error(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    form = SubmissionOrgaForm(
        event=event,
        instance=submission,
        data=_orga_base_data(submission, start=event.datetime_from),
    )

    assert not form.is_valid()
    assert "start" in form.errors


def test_submission_orga_form_clean_valid_scheduling(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)
    start = event.datetime_from + dt.timedelta(hours=1)
    end = event.datetime_from + dt.timedelta(hours=2)

    form = SubmissionOrgaForm(
        event=event,
        instance=submission,
        data=_orga_base_data(submission, room=room.pk, start=start, end=end),
    )

    assert form.is_valid(), form.errors


def test_submission_orga_form_clean_no_scheduling_fields_is_valid(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    form = SubmissionOrgaForm(
        event=event, instance=submission, data=_orga_base_data(submission)
    )

    assert form.is_valid(), form.errors


def test_submission_orga_form_save_new_sets_state(event):
    form = SubmissionOrgaForm(event=event, data=_orga_new_data(event))
    assert form.is_valid(), form.errors
    form.instance.event = event
    result = form.save()

    assert result.pk is not None
    assert result.state == SubmissionStates.SUBMITTED


def test_submission_orga_form_save_new_sets_content_locale_from_event(event):
    form = SubmissionOrgaForm(event=event, data=_orga_new_data(event))
    assert form.is_valid(), form.errors
    form.instance.event = event
    result = form.save()

    assert result.content_locale == event.locale


def test_submission_orga_form_save_new_preserves_content_locale_when_field_present():
    event = EventFactory(content_locale_array="en,de")
    form = SubmissionOrgaForm(
        event=event, data=_orga_new_data(event, content_locale="de")
    )
    assert form.is_valid(), form.errors
    form.instance.event = event
    result = form.save()

    assert result.content_locale == "de"


def test_submission_orga_form_save_existing_duration_change_updates_slots(event):
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, duration=30
    )
    slot = TalkSlotFactory(submission=submission, is_visible=True)

    form = SubmissionOrgaForm(
        event=event,
        instance=submission,
        data=_orga_base_data(
            submission, duration=60, room=slot.room.pk, start=slot.start, end=slot.end
        ),
    )
    assert form.is_valid(), form.errors
    form.save()

    slot.refresh_from_db()

    assert slot.end == slot.start + dt.timedelta(minutes=60)


def test_submission_orga_form_save_existing_track_change_updates_review_scores(event):
    track1 = TrackFactory(event=event)
    track2 = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track1)

    form = SubmissionOrgaForm(
        event=event,
        instance=submission,
        data=_orga_base_data(submission, track=track2.pk),
    )
    assert form.is_valid(), form.errors
    result = form.save()

    assert result.track == track2


def test_submission_orga_form_scheduling_kwargs_returns_changed_values(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=submission, is_visible=True)
    room = RoomFactory(event=event)
    start = event.datetime_from + dt.timedelta(hours=2)
    end = event.datetime_from + dt.timedelta(hours=3)

    form = SubmissionOrgaForm(
        event=event,
        instance=submission,
        data=_orga_base_data(submission, room=room.pk, start=start, end=end),
    )
    assert form.is_valid(), form.errors
    assert form.scheduling_kwargs() == {"room": room, "start": start, "end": end}


def test_submission_orga_form_scheduling_kwargs_none_when_unchanged(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=submission, is_visible=True)

    form = SubmissionOrgaForm(
        event=event, instance=submission, data=_orga_base_data(submission)
    )
    assert form.is_valid(), form.errors
    assert form.scheduling_kwargs() is None


def test_submission_orga_form_scheduling_kwargs_none_without_fields(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    form = SubmissionOrgaForm(
        event=event, instance=submission, data=_orga_base_data(submission)
    )
    assert form.is_valid(), form.errors
    assert form.scheduling_kwargs() is None


def test_submission_orga_form_save_slot_count_change_updates_talk_slots():
    event = EventFactory(feature_flags={"present_multiple_times": True})
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, slot_count=1
    )
    TalkSlotFactory(submission=submission, is_visible=True)

    form = SubmissionOrgaForm(
        event=event, instance=submission, data=_orga_base_data(submission, slot_count=2)
    )
    assert form.is_valid(), form.errors
    form.save()

    slot_count = TalkSlot.objects.filter(
        submission=submission, schedule=submission.event.wip_schedule
    ).count()

    assert slot_count == 2


def test_submission_orga_form_meta_media_includes_js():
    form = SubmissionOrgaForm.__dict__["Media"]
    assert any("submission.js" in str(js) for js in form.js)


def test_anonymise_form_raises_on_unsaved_instance():
    with pytest.raises(ValueError, match="Cannot anonymise unsaved submission"):
        AnonymiseForm(instance=None)


def test_anonymise_form_raises_on_instance_without_pk(event):

    unsaved = Submission(event=event, title="Test")

    with pytest.raises(ValueError, match="Cannot anonymise unsaved submission"):
        AnonymiseForm(instance=unsaved)


def test_anonymise_form_init_with_tags_does_not_crash(event):
    TagFactory(event=event)
    submission = SubmissionFactory(event=event)

    form = AnonymiseForm(instance=submission)

    assert "tags" not in form.fields


def test_anonymise_form_init_with_active_tracks_does_not_crash(event):
    TrackFactory(event=event)
    submission = SubmissionFactory(event=event)

    form = AnonymiseForm(instance=submission)

    assert "track" not in form.fields


def test_anonymise_form_init_sets_plaintext_on_fields(event):
    submission = SubmissionFactory(event=event, title="Original")

    form = AnonymiseForm(instance=submission)

    assert form.fields["title"].plaintext == "Original"


def test_anonymise_form_init_removes_content_locale_field(event):
    submission = SubmissionFactory(event=event)

    form = AnonymiseForm(instance=submission)

    assert "content_locale" not in form.fields


def test_anonymise_form_init_removes_non_model_fields(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    form = AnonymiseForm(instance=submission)

    assert "room" not in form.fields
    assert "start" not in form.fields
    assert "end" not in form.fields
    assert "state" not in form.fields


def test_anonymise_form_init_all_fields_not_required(event):
    submission = SubmissionFactory(event=event)

    form = AnonymiseForm(instance=submission)

    for field in form.fields.values():
        assert field.required is False


def test_anonymise_form_save_stores_anonymised_data(event):
    submission = SubmissionFactory(event=event, title="Original Title")

    form = AnonymiseForm(
        instance=submission,
        data={
            "title": "Anonymised Title",
            "abstract": submission.abstract or "",
            "description": submission.description or "",
            "notes": submission.notes or "",
        },
    )
    assert form.is_valid(), form.errors
    form.save()

    submission.refresh_from_db()

    assert submission.anonymised["_anonymised"] is True
    assert submission.anonymised["title"] == "Anonymised Title"


def test_anonymise_form_save_only_stores_changed_fields(event):
    submission = SubmissionFactory(event=event, title="Original", abstract="Abstract")

    form = AnonymiseForm(
        instance=submission,
        data={
            "title": "Original",
            "abstract": "New abstract",
            "description": submission.description or "",
            "notes": submission.notes or "",
        },
    )
    assert form.is_valid(), form.errors
    form.save()

    submission.refresh_from_db()

    assert "title" not in submission.anonymised
    assert submission.anonymised["abstract"] == "New abstract"


def test_anonymise_form_save_does_not_modify_original_model_fields(event):
    submission = SubmissionFactory(event=event, title="Original Title")

    form = AnonymiseForm(
        instance=submission,
        data={
            "title": "Anonymised Title",
            "abstract": "",
            "description": "",
            "notes": "",
        },
    )
    assert form.is_valid(), form.errors
    form.save()

    submission.refresh_from_db()

    assert submission.title == "Original Title"


def test_anonymise_form_default_renderer():
    assert AnonymiseForm.default_renderer is InlineFormRenderer


def test_anonymise_form_meta_fields():
    assert AnonymiseForm.Meta.fields == ["title", "abstract", "description", "notes"]


@pytest.mark.parametrize(
    ("flag_enabled", "present"),
    ((False, False), (True, True)),
    ids=("disabled", "enabled"),
)
def test_submission_orga_form_attendee_signup_field_visibility(flag_enabled, present):
    event = EventFactory(feature_flags={"attendee_signup": flag_enabled})
    submission = SubmissionFactory(event=event)

    form = SubmissionOrgaForm(event=event, instance=submission)

    assert ("attendee_signup_required" in form.fields) is present


def test_submission_orga_form_attendee_signup_field_disabled_in_read_only_mode():
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event)

    form = SubmissionOrgaForm(event=event, instance=submission, read_only=True)

    assert form.fields["attendee_signup_required"].disabled is True


def test_submission_orga_form_attendee_signup_default_label_ignores_submission_override():
    # The label must reflect what would apply if the orga left the
    # override unset — track/type defaults are False (factory defaults), so
    # the underlying default is "No signup" regardless of the override.
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event, attendee_signup_required=True)

    form = SubmissionOrgaForm(event=event, instance=submission)

    default_choice_label = str(
        dict(form.fields["attendee_signup_required"].choices)["unknown"]
    )
    assert "currently: No signup" in default_choice_label


@pytest.mark.parametrize("source", ("track", "submission_type"))
def test_submission_orga_form_attendee_signup_default_label_inherits_requirement(
    source,
):
    event = EventFactory(feature_flags={"attendee_signup": True})
    kwargs = {}
    if source == "track":
        kwargs["track"] = TrackFactory(event=event, attendee_signup_required=True)
    else:
        kwargs["submission_type"] = SubmissionTypeFactory(
            event=event, attendee_signup_required=True
        )
    submission = SubmissionFactory(event=event, **kwargs)

    form = SubmissionOrgaForm(event=event, instance=submission)

    default_choice_label = str(
        dict(form.fields["attendee_signup_required"].choices)["unknown"]
    )
    assert "currently: Requires signup" in default_choice_label


@pytest.mark.parametrize(
    ("instance_value", "expected_initial"),
    ((True, "true"), (False, "false"), (None, "unknown")),
)
def test_submission_orga_form_attendee_signup_initial_matches_instance(
    instance_value, expected_initial
):
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event, attendee_signup_required=instance_value)

    form = SubmissionOrgaForm(event=event, instance=submission)

    assert form.initial["attendee_signup_required"] == expected_initial


@pytest.mark.parametrize(
    ("submitted", "expected"), (("true", True), ("false", False), ("unknown", None))
)
def test_submission_orga_form_clean_attendee_signup_required(submitted, expected):
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event)
    form = SubmissionOrgaForm(event=event, instance=submission)
    form.cleaned_data = {"attendee_signup_required": submitted}

    assert form.clean_attendee_signup_required() is expected


def test_submission_orga_form_blocks_required_false_with_signups():
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission_type = SubmissionTypeFactory(event=event)
    submission = SubmissionFactory(event=event, submission_type=submission_type)
    AttendeeSignupFactory(submission=submission)

    form = SubmissionOrgaForm(
        event=event,
        instance=submission,
        data={
            "title": submission.title,
            "submission_type": submission_type.pk,
            "content_locale": "en",
            "abstract": "x",
            "description": "x",
            "notes": "x",
            "internal_notes": "x",
            "duration": "",
            "slot_count": "1",
            "attendee_signup_required": "false",
        },
    )

    assert not form.is_valid()
    assert "attendee_signup_required" in form.errors


def test_submission_signup_form_meta_fields():
    assert SubmissionSignupForm.Meta.fields == ["attendee_signup_capacity"]


@pytest.mark.parametrize(
    ("submitted_value", "expected_saved"),
    (("5", 5), ("", None)),
    ids=("positive_capacity", "empty_clears_capacity"),
)
def test_submission_signup_form_accepts_capacity(submitted_value, expected_saved):
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event, attendee_signup_capacity=10)
    AttendeeSignupFactory(submission=submission)

    form = SubmissionSignupForm(
        instance=submission, data={"attendee_signup_capacity": submitted_value}
    )

    assert form.is_valid(), form.errors
    form.save()
    submission.refresh_from_db()
    assert submission.attendee_signup_capacity == expected_saved


def test_submission_signup_form_rejects_zero_capacity():
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event)

    form = SubmissionSignupForm(
        instance=submission, data={"attendee_signup_capacity": "0"}
    )

    assert not form.is_valid()
    assert "attendee_signup_capacity" in form.errors


def test_submission_signup_filter_form_state_counts_reflect_signups():
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event)
    AttendeeSignupFactory(submission=submission)
    AttendeeSignupFactory(submission=submission)
    AttendeeSignupFactory(submission=submission, state=AttendeeSignupStates.CANCELED)

    form = SubmissionSignupFilterForm(submission=submission)
    choices = dict(form.fields["state"].choices)

    assert choices[AttendeeSignupStates.CONFIRMED].count == 2
    assert choices[AttendeeSignupStates.CANCELED].count == 1


def test_submission_signup_filter_form_without_submission_uses_zero_counts():
    form = SubmissionSignupFilterForm(submission=None)
    choices = dict(form.fields["state"].choices)
    assert choices[AttendeeSignupStates.CONFIRMED].count == 0


def test_submission_signup_filter_form_filter_queryset_by_state():
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event)
    confirmed = AttendeeSignupFactory(submission=submission)
    AttendeeSignupFactory(submission=submission, state=AttendeeSignupStates.CANCELED)

    form = SubmissionSignupFilterForm(
        data={"state": [AttendeeSignupStates.CONFIRMED]}, submission=submission
    )
    assert form.is_valid()

    result = list(form.filter_queryset(submission.attendee_signups.all()))
    assert result == [confirmed]


def test_submission_signup_filter_form_filter_queryset_no_state_returns_all():
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event)
    AttendeeSignupFactory(submission=submission)
    AttendeeSignupFactory(submission=submission)

    form = SubmissionSignupFilterForm(data={}, submission=submission)
    assert form.is_valid()

    result = form.filter_queryset(submission.attendee_signups.all())
    assert result.count() == 2
