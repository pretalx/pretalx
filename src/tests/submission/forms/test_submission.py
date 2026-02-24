import datetime as dt

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.person.models import SpeakerProfile
from pretalx.submission.forms.submission import InfoForm, SubmissionFilterForm
from pretalx.submission.models import SubmissionStates
from pretalx.submission.models.access_code import SubmitterAccessCode
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TagFactory,
    TrackFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_info_form_init_sets_default_submission_type():
    """New submission gets the CfP's default type as initial."""
    with scopes_disabled():
        event = EventFactory()

        form = InfoForm(event=event)

    assert form.initial["submission_type"] == event.cfp.default_type


@pytest.mark.django_db
def test_info_form_init_sets_default_content_locale():
    """New submission gets the event locale as initial content_locale."""
    with scopes_disabled():
        event = EventFactory()

        form = InfoForm(event=event)

    assert form.initial["content_locale"] == event.locale


@pytest.mark.django_db
def test_info_form_init_preserves_existing_submission_type():
    """An existing submission with a type set does not get overridden."""
    with scopes_disabled():
        event = EventFactory()
        extra_type = SubmissionTypeFactory(event=event)
        submission = SubmissionFactory(event=event, submission_type=extra_type)

        form = InfoForm(event=event, instance=submission)

    assert form.initial["submission_type"] == extra_type.pk


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("remove", "expect_present"),
    ((True, False), (False, True)),
    ids=["removed_when_requested", "kept_by_default"],
)
def test_info_form_init_additional_speaker_presence(remove, expect_present):
    with scopes_disabled():
        event = EventFactory()

        form = InfoForm(event=event, remove_additional_speaker=remove)

    assert ("additional_speaker" in form.fields) is expect_present


@pytest.mark.django_db
def test_info_form_init_readonly_disables_all_fields():
    with scopes_disabled():
        event = EventFactory()

        form = InfoForm(event=event, readonly=True)

    for field in form.fields.values():
        assert field.disabled is True


@pytest.mark.django_db
def test_info_form_init_abstract_do_not_ask_removes_field():
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["abstract"] = {"visibility": "do_not_ask"}
        event.cfp.save()

        form = InfoForm(event=event)

    assert "abstract" not in form.fields


@pytest.mark.django_db
def test_info_form_init_field_configuration_reorders_fields():
    with scopes_disabled():
        event = EventFactory()
        field_config = [{"key": "notes"}, {"key": "title"}, {"key": "abstract"}]

        form = InfoForm(event=event, field_configuration=field_config)

    keys = list(form.fields.keys())
    assert keys.index("notes") < keys.index("title") < keys.index("abstract")


def _enable_tracks(event, visibility="required"):
    """Helper to enable tracks on an event for InfoForm tests."""
    event.feature_flags["use_tracks"] = True
    event.save()
    event.cfp.fields["track"] = {"visibility": visibility}
    event.cfp.save()


@pytest.mark.django_db
def test_info_form_set_track_removes_field_when_tracks_disabled():
    """When use_tracks feature flag is off, track field is removed."""
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = False
        event.save()
        event.cfp.fields["track"] = {"visibility": "required"}
        event.cfp.save()

        form = InfoForm(event=event)

    assert "track" not in form.fields


@pytest.mark.django_db
def test_info_form_set_track_removes_field_when_instance_not_submitted():
    """Track field is removed for non-submitted submissions even with use_tracks on."""
    with scopes_disabled():
        event = EventFactory()
        _enable_tracks(event)
        TrackFactory(event=event)
        TrackFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

        form = InfoForm(event=event, instance=submission)

    assert "track" not in form.fields


@pytest.mark.django_db
def test_info_form_set_track_excludes_access_code_tracks():
    """Without access code, track field excludes restricted tracks."""
    with scopes_disabled():
        event = EventFactory()
        _enable_tracks(event)
        public1 = TrackFactory(event=event, requires_access_code=False)
        public2 = TrackFactory(event=event, requires_access_code=False)
        TrackFactory(event=event, requires_access_code=True)

        form = InfoForm(event=event)

    assert set(form.fields["track"].queryset) == {public1, public2}


@pytest.mark.django_db
def test_info_form_set_track_single_required_track_becomes_default():
    """When exactly one track is available and required, it becomes a default_value."""
    with scopes_disabled():
        event = EventFactory()
        _enable_tracks(event)
        track = TrackFactory(event=event, requires_access_code=False)

        form = InfoForm(event=event)

    assert "track" not in form.fields
    assert form.default_values.get("track") == track


@pytest.mark.django_db
def test_info_form_set_track_with_access_code_tracks():
    """Access code with tracks limits the track queryset to those tracks."""
    with scopes_disabled():
        event = EventFactory()
        _enable_tracks(event)
        code_track1 = TrackFactory(event=event)
        code_track2 = TrackFactory(event=event)
        TrackFactory(event=event)
        access_code = SubmitterAccessCode.objects.create(event=event)
        access_code.tracks.add(code_track1, code_track2)

        form = InfoForm(event=event, access_code=access_code)

    assert set(form.fields["track"].queryset) == {code_track1, code_track2}


@pytest.mark.django_db
def test_info_form_init_access_code_sets_initial_track():
    """Access code sets the initial track for a new submission."""
    with scopes_disabled():
        event = EventFactory()
        _enable_tracks(event)
        code_track = TrackFactory(event=event)
        TrackFactory(event=event)
        access_code = SubmitterAccessCode.objects.create(event=event)
        access_code.tracks.add(code_track)

        form = InfoForm(event=event, access_code=access_code)

    assert form.initial.get("track") == code_track


@pytest.mark.django_db
def test_info_form_set_track_preserves_restricted_track_on_instance():
    """Instance with a restricted track still sees it in the queryset."""
    with scopes_disabled():
        event = EventFactory()
        _enable_tracks(event)
        restricted_track = TrackFactory(event=event, requires_access_code=True)
        public_track = TrackFactory(event=event, requires_access_code=False)
        submission = SubmissionFactory(
            event=event, track=restricted_track, state=SubmissionStates.SUBMITTED
        )

        form = InfoForm(event=event, instance=submission)

    assert set(form.fields["track"].queryset) == {restricted_track, public_track}


@pytest.mark.django_db
def test_info_form_set_submission_types_locks_for_non_submitted_existing():
    """Existing non-submitted submission gets type locked to its current type."""
    with scopes_disabled():
        submission = SubmissionFactory(state=SubmissionStates.ACCEPTED)

        form = InfoForm(event=submission.event, instance=submission)

    assert form.fields["submission_type"].disabled is True
    assert list(form.fields["submission_type"].queryset) == [submission.submission_type]


@pytest.mark.django_db
def test_info_form_set_submission_types_single_type_becomes_default():
    """When only one submission type is available, it becomes a default_value."""
    with scopes_disabled():
        event = EventFactory()

        form = InfoForm(event=event)

    assert "submission_type" not in form.fields
    assert form.default_values["submission_type"] == event.cfp.default_type


@pytest.mark.django_db
def test_info_form_set_submission_types_access_code_with_types():
    """Access code with specific submission types limits the queryset."""
    with scopes_disabled():
        event = EventFactory()
        code_type1 = SubmissionTypeFactory(event=event)
        code_type2 = SubmissionTypeFactory(event=event)
        SubmissionTypeFactory(event=event)  # not in the access code
        access_code = SubmitterAccessCode.objects.create(event=event)
        access_code.submission_types.add(code_type1, code_type2)

        form = InfoForm(event=event, access_code=access_code)

    assert set(form.fields["submission_type"].queryset) == {code_type1, code_type2}


@pytest.mark.django_db
def test_info_form_set_submission_types_access_code_without_types():
    """Access code without specific types falls back to non-restricted types."""
    with scopes_disabled():
        event = EventFactory()
        SubmissionTypeFactory(event=event, requires_access_code=True)
        access_code = SubmitterAccessCode.objects.create(event=event)

        form = InfoForm(event=event, access_code=access_code)

    assert "submission_type" not in form.fields
    assert form.default_values["submission_type"] == event.cfp.default_type


@pytest.mark.django_db
def test_info_form_set_submission_types_after_deadline_only_type_specific():
    """After CfP deadline, only types with their own future deadline are available."""
    with scopes_disabled():
        event = EventFactory()
        past = now() - dt.timedelta(days=1)
        future = now() + dt.timedelta(days=1)
        event.cfp.deadline = past
        event.cfp.save()
        future_type1 = SubmissionTypeFactory(event=event, deadline=future)
        future_type2 = SubmissionTypeFactory(event=event, deadline=future)
        SubmissionTypeFactory(event=event, deadline=past)

        form = InfoForm(event=event)

    assert set(form.fields["submission_type"].queryset) == {future_type1, future_type2}


@pytest.mark.django_db
def test_info_form_set_submission_types_duration_help_text():
    """When multiple types and duration field visible, help text is appended."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["duration"] = {"visibility": "optional"}
        event.cfp.save()
        SubmissionTypeFactory(event=event)

        form = InfoForm(event=event)

    assert "duration" in form.fields
    assert "default duration" in str(form.fields["duration"].help_text)


@pytest.mark.django_db
def test_info_form_set_submission_types_multiple_types_shown():
    """When multiple submission types are available, the field is shown."""
    with scopes_disabled():
        event = EventFactory()
        SubmissionTypeFactory(event=event)

        form = InfoForm(event=event)

    assert "submission_type" in form.fields
    assert form.fields["submission_type"].queryset.count() == 2


@pytest.mark.django_db
def test_info_form_set_locales_do_not_ask_skips():
    """When content_locale is do_not_ask, _set_locales is a no-op."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["content_locale"] = {"visibility": "do_not_ask"}
        event.cfp.save()

        form = InfoForm(event=event)

    assert "content_locale" not in form.fields


@pytest.mark.django_db
def test_info_form_set_locales_single_locale_becomes_default():
    """Single content locale becomes a default_value, field is removed."""
    with scopes_disabled():
        event = EventFactory()

        form = InfoForm(event=event)

    assert "content_locale" not in form.fields
    assert form.default_values["content_locale"] == event.content_locales[0]


@pytest.mark.django_db
def test_info_form_set_locales_multiple_locales_shows_field():
    """Multiple content locales keep the field visible with choices."""
    with scopes_disabled():
        event = EventFactory()
        event.content_locale_array = "en,de"
        event.save()

        form = InfoForm(event=event)

    assert "content_locale" in form.fields
    locale_codes = [code for code, _ in form.fields["content_locale"].choices]
    assert "en" in locale_codes
    assert "de" in locale_codes


@pytest.mark.django_db
def test_info_form_set_slot_count_removed_when_feature_disabled():
    """slot_count field is removed when present_multiple_times is off."""
    with scopes_disabled():
        event = EventFactory()

        form = InfoForm(event=event)

    assert "slot_count" not in form.fields


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("state", "expect_disabled"),
    ((SubmissionStates.ACCEPTED, True), (SubmissionStates.SUBMITTED, False)),
    ids=["disabled_for_accepted", "enabled_for_submitted"],
)
def test_info_form_set_slot_count_disabled_by_state(state, expect_disabled):
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["present_multiple_times"] = True
        event.save()
        submission = SubmissionFactory(event=event, state=state)

        form = InfoForm(event=event, instance=submission)

    assert "slot_count" in form.fields
    assert form.fields["slot_count"].disabled is expect_disabled


def _enable_tags(event, visibility="optional"):
    """Helper to enable tags on an event for InfoForm tests."""
    event.cfp.fields["tags"] = {"visibility": visibility, "min": None, "max": None}
    event.cfp.save()


@pytest.mark.django_db
def test_info_form_set_tags_removed_when_no_public_tags():
    """tags field is removed when there are no public tags."""
    with scopes_disabled():
        event = EventFactory()
        _enable_tags(event)
        TagFactory(event=event, is_public=False)

        form = InfoForm(event=event)

    assert "tags" not in form.fields


@pytest.mark.django_db
def test_info_form_set_tags_shows_public_tags():
    """tags field queryset is limited to public tags."""
    with scopes_disabled():
        event = EventFactory()
        _enable_tags(event)
        public_tag = TagFactory(event=event, is_public=True)
        TagFactory(event=event, is_public=False)

        form = InfoForm(event=event)

    assert "tags" in form.fields
    assert list(form.fields["tags"].queryset) == [public_tag]


@pytest.mark.django_db
def test_info_form_set_tags_initial_from_instance():
    """Existing submission's public tags are set as initial."""
    with scopes_disabled():
        event = EventFactory()
        _enable_tags(event)
        public_tag = TagFactory(event=event, is_public=True)
        private_tag = TagFactory(event=event, is_public=False)
        submission = SubmissionFactory(event=event)
        submission.tags.add(public_tag, private_tag)

        form = InfoForm(event=event, instance=submission)

    assert set(form.initial["tags"]) == {public_tag}


@pytest.mark.django_db
def test_info_form_clean_additional_speaker_empty_returns_empty_list():
    with scopes_disabled():
        event = EventFactory()
        data = {"title": "Talk", "additional_speaker": ""}

        form = InfoForm(event=event, data=data)
        form.is_valid()

    assert form.cleaned_data.get("additional_speaker") == []


@pytest.mark.django_db
def test_info_form_clean_additional_speaker_valid_emails():
    with scopes_disabled():
        event = EventFactory()
        data = {"title": "Talk", "additional_speaker": "a@example.com, b@example.com"}

        form = InfoForm(event=event, data=data)
        form.is_valid()

    emails = form.cleaned_data.get("additional_speaker", [])
    assert set(emails) == {"a@example.com", "b@example.com"}


@pytest.mark.django_db
def test_info_form_clean_additional_speaker_invalid_email_raises_error():
    with scopes_disabled():
        event = EventFactory()
        data = {
            "title": "Talk",
            "additional_speaker": "valid@example.com, not-an-email",
        }

        form = InfoForm(event=event, data=data)

    assert not form.is_valid()
    assert "additional_speaker" in form.errors


@pytest.mark.django_db
def test_info_form_clean_additional_speaker_skips_empty_between_commas():
    """Empty strings from splitting (e.g. trailing comma) are skipped."""
    with scopes_disabled():
        event = EventFactory()
        data = {"title": "Talk", "additional_speaker": "a@example.com,,b@example.com,"}

        form = InfoForm(event=event, data=data)
        form.is_valid()

    assert set(form.cleaned_data.get("additional_speaker", [])) == {
        "a@example.com",
        "b@example.com",
    }


@pytest.mark.django_db
def test_info_form_clean_additional_speaker_max_speakers_exceeded():
    """For new submissions, existing_speakers defaults to 1 (the submitter)."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["additional_speaker"] = {"visibility": "optional", "max": 2}
        event.cfp.save()
        data = {"title": "Talk", "additional_speaker": "a@example.com, b@example.com"}

        form = InfoForm(event=event, data=data)

    # 1 (submitter) + 2 emails = 3 > max 2
    assert not form.is_valid()
    assert "additional_speaker" in form.errors


@pytest.mark.django_db
def test_info_form_clean_additional_speaker_deduplicates():
    with scopes_disabled():
        event = EventFactory()
        data = {"title": "Talk", "additional_speaker": "a@example.com\na@example.com"}

        form = InfoForm(event=event, data=data)
        form.is_valid()

    assert form.cleaned_data.get("additional_speaker") == ["a@example.com"]


@pytest.mark.django_db
def test_info_form_clean_additional_speaker_lowercases():
    with scopes_disabled():
        event = EventFactory()
        data = {"title": "Talk", "additional_speaker": "A@Example.COM"}

        form = InfoForm(event=event, data=data)
        form.is_valid()

    assert form.cleaned_data.get("additional_speaker") == ["a@example.com"]


@pytest.mark.django_db
def test_info_form_clean_additional_speaker_within_max_speakers_limit():
    """Adding speakers within the max_speakers limit is accepted."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["additional_speaker"] = {"visibility": "optional", "max": 3}
        event.cfp.save()
        data = {
            "title": "Talk",
            "abstract": "An abstract",
            "additional_speaker": "a@example.com",
        }

        form = InfoForm(event=event, data=data)

        assert form.is_valid(), form.errors
        assert form.cleaned_data["additional_speaker"] == ["a@example.com"]


@pytest.mark.django_db
def test_info_form_clean_additional_speaker_max_speakers_with_existing_instance():
    """max_speakers counts existing speakers on a saved submission instance."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["additional_speaker"] = {"visibility": "optional", "max": 2}
        event.cfp.save()
        submission = SubmissionFactory(event=event)
        speaker = SpeakerProfile.objects.create(event=event)
        submission.speakers.add(speaker)
        data = {
            "title": "Talk",
            "abstract": "An abstract",
            "additional_speaker": "new@example.com",
        }

        form = InfoForm(event=event, instance=submission, data=data)
        # 1 existing speaker + 1 new email = 2 <= max 2
        assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_info_form_clean_tags_preserves_private_tags():
    """clean_tags adds back private tags from the instance."""
    with scopes_disabled():
        event = EventFactory()
        _enable_tags(event)
        public_tag = TagFactory(event=event, is_public=True)
        private_tag = TagFactory(event=event, is_public=False)
        submission = SubmissionFactory(event=event)
        submission.tags.add(public_tag, private_tag)
        data = {"title": "Talk", "tags": [public_tag.pk]}

        form = InfoForm(event=event, instance=submission, data=data)
        form.is_valid()

    assert set(form.cleaned_data.get("tags", set())) == {public_tag, private_tag}


@pytest.mark.django_db
def test_info_form_clean_tags_without_instance():
    """clean_tags on a new (unsaved) submission returns only the selected public tags."""
    with scopes_disabled():
        event = EventFactory()
        _enable_tags(event)
        public_tag = TagFactory(event=event, is_public=True)
        data = {"title": "Talk", "abstract": "An abstract", "tags": [public_tag.pk]}

        form = InfoForm(event=event, data=data)
        form.is_valid()

    assert form.cleaned_data.get("tags") == {public_tag}


@pytest.mark.django_db
def test_info_form_save_applies_default_values():
    """save() sets default_values on the instance before saving."""
    with scopes_disabled():
        event = EventFactory()
        data = {"title": "My Talk", "abstract": "An abstract"}

        form = InfoForm(event=event, data=data)
        assert form.is_valid(), form.errors
        form.instance.event = event
        result = form.save()

    assert result.pk is not None
    assert result.submission_type == event.cfp.default_type
    assert result.content_locale == event.content_locales[0]


@pytest.mark.django_db
def test_info_form_save_with_image_field_hidden():
    """save() works when image field is hidden (do_not_ask) — no image processing occurs."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["image"] = {"visibility": "do_not_ask"}
        event.cfp.save()
        submission = SubmissionFactory(event=event)
        data = {"title": "Updated", "abstract": "An abstract"}

        form = InfoForm(event=event, instance=submission, data=data)
        assert form.is_valid(), form.errors
        result = form.save()

    assert result.title == "Updated"
    assert "image" not in form.cleaned_data


@pytest.mark.django_db
def test_info_form_init_access_code_sets_initial_submission_type():
    """Access code with a specific submission type sets it as initial."""
    with scopes_disabled():
        event = EventFactory()
        code_type = SubmissionTypeFactory(event=event)
        access_code = SubmitterAccessCode.objects.create(event=event)
        access_code.submission_types.add(code_type)

        form = InfoForm(event=event, access_code=access_code)

    assert form.initial["submission_type"] == code_type


@pytest.mark.django_db
def test_submission_filter_form_init_sets_state_choices():
    with scopes_disabled():
        event = EventFactory()

        form = SubmissionFilterForm(event=event)

    state_values = [choice[0] for choice in form.fields["state"].choices]
    assert "submitted" in state_values
    assert "accepted" in state_values


@pytest.mark.django_db
def test_submission_filter_form_init_excludes_draft_from_state_choices():
    with scopes_disabled():
        event = EventFactory()

        form = SubmissionFilterForm(event=event)

    state_values = [choice[0] for choice in form.fields["state"].choices]
    assert SubmissionStates.DRAFT not in state_values


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("extra_types", "expect_present"),
    ((0, False), (1, True)),
    ids=["single_type_removed", "multiple_types_shown"],
)
def test_submission_filter_form_init_submission_type_presence(
    extra_types, expect_present
):
    with scopes_disabled():
        event = EventFactory()
        for _ in range(extra_types):
            SubmissionTypeFactory(event=event)

        form = SubmissionFilterForm(event=event)

    assert ("submission_type" in form.fields) is expect_present


@pytest.mark.django_db
def test_submission_filter_form_init_removes_track_when_single_and_required():
    """track field is removed when only one track exists and track is required."""
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = True
        event.save()
        TrackFactory(event=event)
        event.cfp.fields["track"] = {"visibility": "required"}
        event.cfp.save()

        form = SubmissionFilterForm(event=event)

    assert "track" not in form.fields


@pytest.mark.django_db
def test_submission_filter_form_init_shows_track_when_multiple():
    """track field is shown when multiple tracks exist."""
    with scopes_disabled():
        event = EventFactory()
        TrackFactory(event=event)
        TrackFactory(event=event)

        form = SubmissionFilterForm(event=event)

    assert "track" in form.fields


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("locales", "expect_present"),
    (("en", False), ("en,de", True)),
    ids=["single_locale_removed", "multiple_locales_shown"],
)
def test_submission_filter_form_init_content_locale_presence(locales, expect_present):
    with scopes_disabled():
        event = EventFactory()
        event.content_locale_array = locales
        event.save()

        form = SubmissionFilterForm(event=event)

    assert ("content_locale" in form.fields) is expect_present


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("tag_count", "expect_present"),
    ((0, False), (1, True)),
    ids=["no_tags_removed", "has_tags_shown"],
)
def test_submission_filter_form_init_tags_presence(tag_count, expect_present):
    with scopes_disabled():
        event = EventFactory()
        for _ in range(tag_count):
            TagFactory(event=event)

        form = SubmissionFilterForm(event=event)

    assert ("tags" in form.fields) is expect_present


@pytest.mark.django_db
def test_submission_filter_form_init_question_queryset_scoped_to_event():
    with scopes_disabled():
        event = EventFactory()
        question = QuestionFactory(event=event)
        QuestionFactory()  # different event

        form = SubmissionFilterForm(event=event)

    assert list(form.fields["question"].queryset) == [question]


@pytest.mark.django_db
def test_submission_filter_form_init_usable_states_limits_choices():
    """When usable_states is given, state choices are limited."""
    with scopes_disabled():
        event = EventFactory()

        form = SubmissionFilterForm(
            event=event, usable_states=["submitted", "accepted"]
        )

    state_values = [
        choice[0]
        for choice in form.fields["state"].choices
        if not str(choice[0]).startswith("pending_state__")
    ]
    assert set(state_values) == {"submitted", "accepted"}


@pytest.mark.django_db
def test_submission_filter_form_init_includes_pending_state_choices():
    """State choices include a pending_state__ variant for each regular state."""
    with scopes_disabled():
        event = EventFactory()

        form = SubmissionFilterForm(event=event)

    state_values = [choice[0] for choice in form.fields["state"].choices]
    regular_states = [
        s for s in state_values if not str(s).startswith("pending_state__")
    ]
    pending_states = [s for s in state_values if str(s).startswith("pending_state__")]
    assert len(pending_states) == len(regular_states)


@pytest.mark.django_db
def test_submission_filter_form_init_state_count_reflects_submissions():
    """State choices include correct count annotations."""
    with scopes_disabled():
        event = EventFactory()
        SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

        form = SubmissionFilterForm(event=event)

    state_dict = {choice[0]: choice[1] for choice in form.fields["state"].choices}
    assert state_dict["submitted"].count == 2
    assert state_dict["accepted"].count == 1


@pytest.mark.django_db
def test_submission_filter_form_init_limit_tracks():
    """limit_tracks restricts which tracks appear in the filter."""
    with scopes_disabled():
        event = EventFactory()
        track1 = TrackFactory(event=event)
        TrackFactory(event=event)

        form = SubmissionFilterForm(event=event, limit_tracks=[track1])

    assert list(form.fields["track"].queryset) == [track1]


@pytest.mark.django_db
def test_submission_filter_form_filter_question_by_answer():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_submission_filter_form_filter_question_by_option():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_submission_filter_form_filter_question_unanswered():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_submission_filter_form_filter_queryset_by_state():
    with scopes_disabled():
        event = EventFactory()
        submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

        form = SubmissionFilterForm(event=event, data={"state": ["submitted"]})
        assert form.is_valid(), form.errors

        qs = event.submissions.all()
        filtered = form.filter_queryset(qs)

    assert set(filtered) == {submitted}


@pytest.mark.django_db
def test_submission_filter_form_filter_queryset_by_pending_state():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_submission_filter_form_filter_queryset_mixed_state_and_pending():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_submission_filter_form_filter_queryset_exclude_pending():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_submission_filter_form_filter_queryset_by_submission_type():
    with scopes_disabled():
        event = EventFactory()
        extra_type = SubmissionTypeFactory(event=event)
        matching = SubmissionFactory(event=event, submission_type=extra_type)
        SubmissionFactory(event=event)

        form = SubmissionFilterForm(
            event=event, data={"submission_type": [extra_type.pk]}
        )
        assert form.is_valid(), form.errors

        qs = event.submissions.all()
        filtered = form.filter_queryset(qs)

    assert set(filtered) == {matching}


@pytest.mark.django_db
def test_submission_filter_form_filter_queryset_by_track():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_submission_filter_form_filter_queryset_by_content_locale():
    with scopes_disabled():
        event = EventFactory()
        event.content_locale_array = "en,de"
        event.save()
        en_sub = SubmissionFactory(event=event, content_locale="en")
        SubmissionFactory(event=event, content_locale="de")

        form = SubmissionFilterForm(event=event, data={"content_locale": ["en"]})
        assert form.is_valid(), form.errors

        qs = event.submissions.all()
        filtered = form.filter_queryset(qs)

    assert set(filtered) == {en_sub}


@pytest.mark.django_db
def test_submission_filter_form_filter_queryset_by_tags():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_submission_filter_form_filter_queryset_search():
    with scopes_disabled():
        event = EventFactory()
        matching = SubmissionFactory(event=event, title="Unique Searchable Title")
        SubmissionFactory(event=event, title="Something Else")

        form = SubmissionFilterForm(event=event, data={"q": "Unique Searchable"})
        assert form.is_valid(), form.errors

        qs = event.submissions.all()
        filtered = form.filter_queryset(qs)

    assert set(filtered) == {matching}


@pytest.mark.django_db
def test_submission_filter_form_filter_queryset_fulltext_search():
    """Fulltext search includes abstract, description, notes, internal_notes."""
    with scopes_disabled():
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


@pytest.mark.django_db
def test_submission_filter_form_filter_queryset_no_filters():
    """With no filters, all submissions are returned."""
    with scopes_disabled():
        event = EventFactory()
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)

        form = SubmissionFilterForm(event=event, data={})
        assert form.is_valid(), form.errors

        qs = event.submissions.all()
        filtered = form.filter_queryset(qs)

    assert set(filtered) == {sub1, sub2}
