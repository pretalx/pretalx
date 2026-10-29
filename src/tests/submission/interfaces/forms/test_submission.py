# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.schedule.models import TalkSlot
from pretalx.submission.interfaces.forms import (
    AnonymiseForm,
    InfoForm,
    SubmissionInfoForm,
    SubmissionOrgaForm,
    SubmissionSignupForm,
)
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    AttendeeSignupFactory,
    EventFactory,
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


def test_info_form_init_on_plain_event_hides_single_choice_fields():
    event = EventFactory()

    form = InfoForm(event=event)
    read_only = InfoForm(event=event, read_only=True)
    speaker_form = SubmissionInfoForm(event=event)

    assert list(form.fields) == [
        "title",
        "abstract",
        "description",
        "notes",
        "do_not_record",
        "image",
        "additional_speaker",
    ]
    assert form.initial == {
        "submission_type": event.cfp.default_type,
        "content_locale": event.locale,
    }
    assert form.default_values == {
        "submission_type": event.cfp.default_type,
        "content_locale": event.content_locales[0],
    }
    assert all(field.disabled is True for field in read_only.fields.values())
    assert list(speaker_form.fields) == list(form.fields)[:-1]


def test_info_form_init_prefills_additional_speaker_from_draft():
    event = EventFactory()
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.DRAFT,
        draft_additional_speakers=["a@example.com", "b@example.com"],
    )

    form = InfoForm(event=event, instance=submission)
    overridden = InfoForm(
        event=event,
        instance=submission,
        initial={"additional_speaker": "override@example.com"},
    )

    assert form.initial["additional_speaker"] == "a@example.com, b@example.com"
    assert overridden.initial["additional_speaker"] == "override@example.com"


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
    TrackFactory(event=event)

    form = InfoForm(event=event)

    assert "track" not in form.fields


def test_info_form_locks_track_and_type_for_non_submitted_instance():
    event = _tracks_event()
    TrackFactory(event=event)
    TrackFactory(event=event)
    SubmissionTypeFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    form = InfoForm(event=event, instance=submission)

    assert "track" not in form.fields
    assert form.fields["submission_type"].disabled is True
    assert list(form.fields["submission_type"].queryset) == [submission.submission_type]
    assert form.initial["submission_type"] == submission.submission_type.pk


def test_info_form_configure_track_single_track_default_or_locked_by_access_code():
    event = _tracks_event()
    code_track = TrackFactory(event=event, requires_access_code=True)
    public_track = TrackFactory(event=event, requires_access_code=False)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.tracks.add(code_track)

    form = InfoForm(event=event)
    code_form = InfoForm(event=event, access_code=access_code)
    bound = InfoForm(
        event=event,
        access_code=access_code,
        data={"title": "My Talk", "abstract": "An abstract", "track": public_track.pk},
    )

    assert "track" not in form.fields
    assert form.default_values["track"] == public_track
    assert list(code_form.fields["track"].queryset) == [code_track]
    assert code_form.fields["track"].disabled is True
    assert code_form.initial["track"] == code_track
    assert bound.is_valid(), bound.errors
    assert bound.cleaned_data["track"] == code_track


def test_info_form_configure_track_multiple_access_code_tracks_stay_selectable():
    event = _tracks_event()
    code_track1 = TrackFactory(event=event)
    code_track2 = TrackFactory(event=event)
    TrackFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.tracks.add(code_track1, code_track2)

    form = InfoForm(event=event, access_code=access_code)

    assert set(form.fields["track"].queryset) == {code_track1, code_track2}
    assert form.fields["track"].disabled is False


def test_info_form_configure_track_single_access_code_track_on_trackless_instance():
    event = _tracks_event()
    code_track = TrackFactory(event=event, requires_access_code=True)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.tracks.add(code_track)
    submission = SubmissionFactory(
        event=event,
        track=None,
        access_code=access_code,
        state=SubmissionStates.SUBMITTED,
    )
    data = {"title": "My Talk", "abstract": "An abstract"}

    form = InfoForm(event=event, instance=submission, data=data)
    assert form.is_valid(), form.errors

    assert form.save().track == code_track


def test_info_form_configure_submission_types_by_access_code():
    event = EventFactory()
    code_type1 = SubmissionTypeFactory(event=event)
    code_type2 = SubmissionTypeFactory(event=event)
    SubmissionTypeFactory(event=event, requires_access_code=True)
    typed_code = SubmitterAccessCodeFactory(event=event)
    typed_code.submission_types.add(code_type1, code_type2)
    untyped_code = SubmitterAccessCodeFactory(event=event)

    typed_form = InfoForm(event=event, access_code=typed_code)
    untyped_form = InfoForm(event=event, access_code=untyped_code)

    assert set(typed_form.fields["submission_type"].queryset) == {
        code_type1,
        code_type2,
    }
    assert typed_form.fields["submission_type"].disabled is False
    assert set(untyped_form.fields["submission_type"].queryset) == {
        event.cfp.default_type,
        code_type1,
        code_type2,
    }


def test_info_form_configure_submission_types_single_access_code_type_locks_and_saves():
    event = EventFactory()
    code_type = SubmissionTypeFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.submission_types.add(code_type)
    data = {
        "title": "My Talk",
        "abstract": "An abstract",
        "submission_type": event.cfp.default_type.pk,
    }

    form = InfoForm(event=event, access_code=access_code)
    bound = InfoForm(event=event, access_code=access_code, data=data)
    assert bound.is_valid(), bound.errors
    bound.instance.event = event
    result = bound.save()

    assert list(form.fields["submission_type"].queryset) == [code_type]
    assert form.fields["submission_type"].disabled is True
    assert form.initial["submission_type"] == code_type
    assert result.submission_type == code_type


@pytest.mark.parametrize(
    ("visibility", "expected", "duration_help"),
    (
        (
            "optional",
            {
                "Talk": "Default duration: 30\xa0minutes",
                "Workshop": "Default duration: 2\xa0hours",
            },
            True,
        ),
        ("required", {"Talk": None, "Workshop": None}, False),
    ),
)
def test_info_form_submission_type_options_describe_default_duration(
    visibility, expected, duration_help
):
    event = EventFactory(cfp__fields={"duration": {"visibility": visibility}})
    event.submission_types.update(name="Talk", default_duration=30)
    workshop = SubmissionTypeFactory(event=event, name="Workshop", default_duration=120)

    form = InfoForm(event=event)
    options = [option.data for option in form["submission_type"].subwidgets]

    assert set(form.fields["submission_type"].queryset) == {
        event.cfp.default_type,
        workshop,
    }
    assert {
        option["label"]: option["attrs"].get("data-description")
        for option in options
        if option["value"]
    } == expected
    assert ("default duration" in str(form.fields["duration"].help_text)) is (
        duration_help
    )


@pytest.mark.parametrize(
    ("visibility", "choices"),
    (("optional", [("en", "English"), ("de", "Deutsch")]), ("do_not_ask", None)),
)
def test_info_form_configure_locales_multiple_locales(visibility, choices):
    event = EventFactory(
        content_locales=["en", "de"],
        cfp__fields={"content_locale": {"visibility": visibility}},
    )

    form = InfoForm(event=event)

    assert getattr(form.fields.get("content_locale"), "choices", None) == choices


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


def test_info_form_tags_show_public_tags_and_preserve_private_ones():
    event = EventFactory(
        cfp__fields={"tags": {"visibility": "optional", "min": None, "max": None}}
    )
    private_tag = TagFactory(event=event, is_public=False)
    assert "tags" not in InfoForm(event=event).fields

    public_tag = TagFactory(event=event, is_public=True)
    submission = SubmissionFactory(event=event)
    submission.tags.add(public_tag, private_tag)
    data = {"title": "Talk", "abstract": "An abstract", "tags": [public_tag.pk]}

    form = InfoForm(event=event)
    new_bound = InfoForm(event=event, data=data)
    existing = InfoForm(event=event, instance=submission)
    existing_bound = InfoForm(event=event, instance=submission, data=data)
    assert new_bound.is_valid(), new_bound.errors
    assert existing_bound.is_valid(), existing_bound.errors

    assert list(form.fields["tags"].queryset) == [public_tag]
    assert new_bound.cleaned_data["tags"] == {public_tag}
    assert list(existing.initial["tags"]) == [public_tag]
    assert existing_bound.cleaned_data["tags"] == {public_tag, private_tag}


@pytest.mark.parametrize(
    ("value", "cleaned", "errors"),
    (
        ("", [], None),
        ("a@example.com, b@example.com", ["a@example.com", "b@example.com"], None),
        ("a@example.com,,b@example.com,", ["a@example.com", "b@example.com"], None),
        ("a@example.com\na@example.com", ["a@example.com"], None),
        ("A@Example.COM", ["a@example.com"], None),
        (
            "valid@example.com, not-an-email",
            None,
            ["Please enter only valid email addresses: not-an-email"],
        ),
        (
            ", ".join(f"victim{i}@example.com" for i in range(51)),
            None,
            [
                (
                    "This would exceed the maximum of 50 speakers per proposal. "
                    "Currently: 1 speaker(s) and 0 pending invitation(s)."
                )
            ],
        ),
    ),
    ids=["empty", "list", "empty_tokens", "duplicate", "uppercase", "invalid", "cap"],
)
def test_info_form_clean_additional_speaker(value, cleaned, errors):
    event = EventFactory()
    assert event.cfp.max_speakers is None

    form = InfoForm(event=event, data={"title": "Talk", "additional_speaker": value})
    form.is_valid()

    assert form.cleaned_data.get("additional_speaker") == cleaned
    assert form.errors.get("additional_speaker") == errors


def test_info_form_clean_additional_speaker_counts_only_new_invitations():
    event = EventFactory(
        cfp__fields={"additional_speaker": {"visibility": "optional", "max": 1}}
    )
    submission = SubmissionFactory(event=event)
    SubmissionInvitationFactory(submission=submission, email="invited@example.com")

    new_form = InfoForm(
        event=event, data={"title": "Talk", "additional_speaker": "a@example.com"}
    )
    existing_form = InfoForm(
        event=event,
        instance=submission,
        data={"title": submission.title, "additional_speaker": "invited@example.com"},
    )
    new_form.is_valid()
    existing_form.is_valid()

    assert new_form.errors["additional_speaker"] == [
        (
            "This would exceed the maximum of 1 speakers per proposal. "
            "Currently: 1 speaker(s) and 0 pending invitation(s)."
        )
    ]
    assert existing_form.cleaned_data["additional_speaker"] == ["invited@example.com"]
    assert "additional_speaker" not in existing_form.errors


def test_info_form_save_applies_default_values_and_skips_hidden_image():
    event = EventFactory(cfp__fields={"image": {"visibility": "do_not_ask"}})
    data = {"title": "My Talk", "abstract": "An abstract"}

    form = InfoForm(event=event, data=data)
    assert form.is_valid(), form.errors
    form.instance.event = event
    result = form.save()

    assert result.pk is not None
    assert result.title == "My Talk"
    assert result.submission_type == event.cfp.default_type
    assert result.content_locale == event.content_locales[0]
    assert "image" not in form.cleaned_data


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


def test_submission_orga_form_init_new_on_plain_event(event):
    room = RoomFactory(event=event)

    form = SubmissionOrgaForm(event=event)
    read_only = SubmissionOrgaForm(event=event, read_only=True)
    read_only_bound = SubmissionOrgaForm(
        event=event, read_only=True, data={"title": "Test"}
    )

    assert list(form.fields) == [
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
        "state",
        "room",
        "start",
        "end",
    ]
    assert [choice for choice, _ in form.fields["state"].choices] == [
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.REJECTED,
        SubmissionStates.CANCELED,
        SubmissionStates.WITHDRAWN,
    ]
    assert form.fields["state"].initial == SubmissionStates.SUBMITTED
    assert list(form.fields["room"].queryset) == [room]
    assert "default duration" not in str(form.fields["duration"].help_text)
    assert [name for name, field in read_only.fields.items() if not field.disabled] == [
        "room",
        "start",
        "end",
    ]
    assert not read_only_bound.is_valid()
    assert read_only_bound.errors["__all__"] == [
        "You are trying to change read-only data."
    ]


def test_submission_orga_form_init_new_on_rich_event():
    event = EventFactory(
        feature_flags={"present_multiple_times": True},
        locales=["en", "de"],
        content_locales=["en", "de", "fr"],
    )
    extra_type = SubmissionTypeFactory(event=event)
    tag = TagFactory(event=event)
    track = TrackFactory(event=event)

    form = SubmissionOrgaForm(event=event)

    assert list(form.fields) == [
        "title",
        "submission_type",
        "track",
        "tags",
        "abstract",
        "description",
        "notes",
        "internal_notes",
        "content_locale",
        "do_not_record",
        "duration",
        "slot_count",
        "image",
        "is_featured",
        "state",
        "room",
        "start",
        "end",
    ]
    assert set(form.fields["submission_type"].queryset) == {
        event.cfp.default_type,
        extra_type,
    }
    assert list(form.fields["tags"].queryset) == [tag]
    assert form.fields["tags"].required is False
    assert list(form.fields["track"].queryset) == [track]
    assert form.fields["content_locale"].choices == [
        ("en", "English"),
        ("de", "Deutsch"),
        ("fr", "Français"),
    ]
    assert "default duration" in str(form.fields["duration"].help_text)


def test_submission_orga_form_init_do_not_ask_removes_fields():
    event = EventFactory(
        content_locales=["en", "de"],
        cfp__fields={
            "abstract": {"visibility": "do_not_ask"},
            "content_locale": {"visibility": "do_not_ask"},
        },
    )

    form = SubmissionOrgaForm(event=event)

    assert "abstract" not in form.fields
    assert "content_locale" not in form.fields


def test_submission_orga_form_init_existing_scheduling_fields_follow_state(event):
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    slot = TalkSlotFactory(submission=confirmed, is_visible=True)
    RoomFactory(event=event, hidden=True)

    submitted_form = SubmissionOrgaForm(event=event, instance=submitted)
    confirmed_form = SubmissionOrgaForm(event=event, instance=confirmed)

    assert {"state", "room", "start", "end"}.isdisjoint(submitted_form.fields)
    assert "state" not in confirmed_form.fields
    assert list(confirmed_form.fields["room"].queryset) == [slot.room]
    assert confirmed_form.initial["room"] == slot.room
    assert confirmed_form.initial["start"] == slot.local_start
    assert confirmed_form.initial["end"] == slot.local_end


def test_submission_orga_form_init_anonymise_prefers_anonymised_data(event):
    submission = SubmissionFactory(
        event=event,
        title="Original Title",
        abstract="Original abstract",
        anonymised={"_anonymised": True, "title": "Anonymised Title"},
    )

    form = SubmissionOrgaForm(event=event, anonymise=True, instance=submission)

    assert form.initial["title"] == "Anonymised Title"
    assert form.initial["abstract"] == "Original abstract"
    assert "state" not in form.fields


def test_submission_orga_form_clean_scheduling_fields(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)
    start = event.datetime_from
    hour = dt.timedelta(hours=1)
    cases = (
        ({}, {}),
        (
            {"room": room.pk, "start": start - hour, "end": start + hour},
            {
                "start": ["Scheduled times cannot be before the event starts."],
                "room": [
                    "You cannot assign a room without setting the start time as well."
                ],
            },
        ),
        (
            {"room": room.pk, "start": start, "end": event.datetime_to + hour},
            {"end": ["Scheduled times cannot be after the event ends."]},
        ),
        (
            {"room": room.pk, "start": start + 2 * hour, "end": start + hour},
            {"end": ["The end time has to be after the start time."]},
        ),
        (
            {"room": room.pk},
            {
                "room": [
                    "You cannot assign a room without setting the start time as well."
                ]
            },
        ),
        (
            {"start": start},
            {
                "start": [
                    "You cannot set a start time without assigning the room as well."
                ]
            },
        ),
    )

    for overrides, errors in cases:
        form = SubmissionOrgaForm(
            event=event,
            instance=submission,
            data=_orga_base_data(submission, **overrides),
        )
        form.is_valid()
        assert form.errors == errors, overrides


def test_submission_orga_form_save_new_sets_state_and_content_locale(event):
    multi_locale_event = EventFactory(content_locales=["en", "de"])

    form = SubmissionOrgaForm(event=event, data=_orga_new_data(event))
    assert form.is_valid(), form.errors
    form.instance.event = event
    result = form.save()
    german = SubmissionOrgaForm(
        event=multi_locale_event,
        data=_orga_new_data(multi_locale_event, content_locale="de"),
    )
    assert german.is_valid(), german.errors
    german.instance.event = multi_locale_event
    german_result = german.save()

    assert result.pk is not None
    assert result.state == SubmissionStates.SUBMITTED
    assert result.content_locale == event.locale
    assert german_result.content_locale == "de"


def test_submission_orga_form_save_applies_duration_and_track_side_effects(event):
    track1 = TrackFactory(event=event)
    track2 = TrackFactory(event=event)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, duration=30, track=track1
    )
    slot = TalkSlotFactory(submission=submission, is_visible=True)

    form = SubmissionOrgaForm(
        event=event,
        instance=submission,
        data=_orga_base_data(
            submission,
            duration=60,
            track=track2.pk,
            room=slot.room.pk,
            start=slot.start,
            end=slot.end,
        ),
    )
    assert form.is_valid(), form.errors
    result = form.save()

    slot.refresh_from_db()

    assert result.track == track2
    assert slot.end == slot.start + dt.timedelta(minutes=60)


def test_submission_orga_form_scheduling_kwargs(event):
    confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=confirmed, is_visible=True)
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    room = RoomFactory(event=event)
    start = event.datetime_from + dt.timedelta(hours=2)
    end = event.datetime_from + dt.timedelta(hours=3)

    changed = SubmissionOrgaForm(
        event=event,
        instance=confirmed,
        data=_orga_base_data(confirmed, room=room.pk, start=start, end=end),
    )
    unchanged = SubmissionOrgaForm(
        event=event, instance=confirmed, data=_orga_base_data(confirmed)
    )
    without_fields = SubmissionOrgaForm(
        event=event, instance=submitted, data=_orga_base_data(submitted)
    )
    assert changed.is_valid(), changed.errors
    assert unchanged.is_valid(), unchanged.errors
    assert without_fields.is_valid(), without_fields.errors

    assert changed.scheduling_kwargs() == {"room": room, "start": start, "end": end}
    assert unchanged.scheduling_kwargs() is None
    assert without_fields.scheduling_kwargs() is None


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


def test_anonymise_form_raises_on_unsaved_instance(event):
    with pytest.raises(ValueError, match="Cannot anonymise unsaved submission"):
        AnonymiseForm(instance=None)
    with pytest.raises(ValueError, match="Cannot anonymise unsaved submission"):
        AnonymiseForm(instance=Submission(event=event, title="Test"))


def test_anonymise_form_init_keeps_only_optional_text_fields():
    event = EventFactory(
        feature_flags={"attendee_signup": True}, content_locales=["en", "de"]
    )
    TagFactory(event=event)
    TrackFactory(event=event)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.ACCEPTED, title="Original"
    )

    form = AnonymiseForm(instance=submission)

    assert list(form.fields) == ["title", "abstract", "description", "notes"]
    assert {name: field.plaintext for name, field in form.fields.items()} == {
        "title": "Original",
        "abstract": submission.abstract,
        "description": submission.description,
        "notes": submission.notes,
    }
    assert all(field.required is False for field in form.fields.values())


def test_anonymise_form_save_stores_only_changed_fields(event):
    submission = SubmissionFactory(
        event=event,
        title="Original Title",
        abstract="Abstract",
        description="",
        notes="Notes",
    )

    form = AnonymiseForm(
        instance=submission,
        data={
            "title": "Anonymised Title",
            "abstract": "Abstract",
            "description": "",
            "notes": "New notes",
        },
    )
    assert form.is_valid(), form.errors
    form.save()

    submission.refresh_from_db()

    assert submission.anonymised == {
        "_anonymised": True,
        "title": "Anonymised Title",
        "notes": "New notes",
    }
    assert submission.title == "Original Title"
    assert submission.notes == "Notes"


def test_submission_orga_form_attendee_signup_field_follows_feature_flag():
    disabled_event = EventFactory(feature_flags={"attendee_signup": False})
    event = EventFactory(feature_flags={"attendee_signup": True})

    disabled_form = SubmissionOrgaForm(
        event=disabled_event, instance=SubmissionFactory(event=disabled_event)
    )
    read_only = SubmissionOrgaForm(
        event=event, instance=SubmissionFactory(event=event), read_only=True
    )

    assert "attendee_signup_required" not in disabled_form.fields
    assert read_only.fields["attendee_signup_required"].disabled is True


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
    ("value", "token"), ((True, "true"), (False, "false"), (None, "unknown"))
)
def test_submission_orga_form_attendee_signup_round_trips_through_tokens(value, token):
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event, attendee_signup_required=value)

    form = SubmissionOrgaForm(event=event, instance=submission)
    form.cleaned_data = {"attendee_signup_required": token}

    assert form.initial["attendee_signup_required"] == token
    assert form.clean_attendee_signup_required() is value
    assert [
        str(label) for _, label in form.fields["attendee_signup_required"].choices
    ] == ["Default (currently: No signup)", "Requires signup", "No signup"]


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
