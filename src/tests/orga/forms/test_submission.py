# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django import forms

from pretalx.common.forms.renderers import InlineFormLabelRenderer, InlineFormRenderer
from pretalx.orga.forms.submission import (
    AddSpeakerForm,
    AddSpeakerInlineForm,
    AnonymiseForm,
    SubmissionForm,
    SubmissionStateChangeForm,
)
from pretalx.schedule.models import TalkSlot
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    EventFactory,
    RoomFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TagFactory,
    TalkSlotFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _base_data(submission, **overrides):
    """Minimal valid data for an existing SubmissionForm submission."""
    data = {
        "title": submission.title,
        "abstract": submission.abstract or "An abstract",
        "submission_type": submission.submission_type.pk,
    }
    data.update(overrides)
    return data


def _new_data(event, **overrides):
    """Minimal valid data for a new SubmissionForm submission."""
    data = {
        "title": "New Talk",
        "abstract": "An abstract",
        "submission_type": event.cfp.default_type.pk,
        "state": SubmissionStates.SUBMITTED,
    }
    data.update(overrides)
    return data


def test_submission_form_init_sets_submission_type_queryset(event):
    extra_type = SubmissionTypeFactory(event=event)

    form = SubmissionForm(event=event)

    assert set(form.fields["submission_type"].queryset) == {
        event.cfp.default_type,
        extra_type,
    }


def test_submission_form_init_removes_tags_field_when_no_tags(event):
    form = SubmissionForm(event=event)

    assert "tags" not in form.fields


def test_submission_form_init_shows_tags_field_when_tags_exist(event):
    tag = TagFactory(event=event)

    form = SubmissionForm(event=event)

    assert "tags" in form.fields
    assert list(form.fields["tags"].queryset) == [tag]
    assert form.fields["tags"].required is False


def test_submission_form_init_new_adds_state_field(event):
    """New submissions (no pk) get a state ChoiceField excluding DRAFT."""
    form = SubmissionForm(event=event)

    assert "state" in form.fields
    state_values = [choice for choice, _ in form.fields["state"].choices]
    assert SubmissionStates.SUBMITTED in state_values
    assert SubmissionStates.ACCEPTED in state_values
    assert SubmissionStates.DRAFT not in state_values


def test_submission_form_init_existing_has_no_state_field(event):
    submission = SubmissionFactory(event=event)

    form = SubmissionForm(event=event, instance=submission)

    assert "state" not in form.fields


def test_submission_form_init_new_adds_scheduling_fields(event):
    """New submissions always get room/start/end fields."""
    RoomFactory(event=event)

    form = SubmissionForm(event=event)

    assert "room" in form.fields
    assert "start" in form.fields
    assert "end" in form.fields


def test_submission_form_init_accepted_submission_has_scheduling_fields(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    form = SubmissionForm(event=event, instance=submission)

    assert "room" in form.fields
    assert "start" in form.fields
    assert "end" in form.fields


def test_submission_form_init_submitted_submission_has_no_scheduling_fields(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    form = SubmissionForm(event=event, instance=submission)

    assert "room" not in form.fields
    assert "start" not in form.fields
    assert "end" not in form.fields


def test_submission_form_init_existing_populates_slot_initial(event):
    """When an existing submission has a scheduled WIP slot, room/start/end are pre-filled."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    slot = TalkSlotFactory(submission=submission, is_visible=True)

    form = SubmissionForm(event=event, instance=submission)

    assert form.initial["room"] == slot.room
    assert form.initial["start"] == slot.local_start
    assert form.initial["end"] == slot.local_end


def test_submission_form_init_removes_slot_count_without_feature_flag(event):
    form = SubmissionForm(event=event)

    assert "slot_count" not in form.fields


def test_submission_form_init_keeps_slot_count_with_feature_flag():
    event = EventFactory(feature_flags={"present_multiple_times": True})
    form = SubmissionForm(event=event)

    assert "slot_count" in form.fields


def test_submission_form_init_removes_track_without_feature_flag():
    event = EventFactory(feature_flags={"use_tracks": False})
    form = SubmissionForm(event=event)

    assert "track" not in form.fields


def test_submission_form_init_keeps_track_with_feature_flag(event):
    track = TrackFactory(event=event)

    form = SubmissionForm(event=event)

    assert "track" in form.fields
    assert list(form.fields["track"].queryset) == [track]


def test_submission_form_init_removes_content_locale_for_single_locale(event):
    form = SubmissionForm(event=event)

    assert "content_locale" not in form.fields


def test_submission_form_init_keeps_content_locale_for_multiple_locales():
    """Content locale choices reflect content_locale_array, which may differ from locale_array."""
    event = EventFactory(locale_array="en,de", content_locale_array="en,de,fr")
    form = SubmissionForm(event=event)

    assert form.fields["content_locale"].choices == [
        ("en", "English"),
        ("de", "Deutsch"),
        ("fr", "Français"),
    ]


def test_submission_form_init_abstract_do_not_ask_removes_field():
    """When abstract visibility is do_not_ask, the field is removed."""
    event = EventFactory(cfp__fields={"abstract": {"visibility": "do_not_ask"}})

    form = SubmissionForm(event=event)

    assert "abstract" not in form.fields


def test_submission_form_init_content_locale_do_not_ask_skips_locale_setup():
    """When content_locale is do_not_ask, the locale choices are not configured."""
    event = EventFactory(
        content_locale_array="en,de",
        cfp__fields={"content_locale": {"visibility": "do_not_ask"}},
    )

    form = SubmissionForm(event=event)

    assert "content_locale" not in form.fields


def test_submission_form_init_duration_help_text_with_multiple_types(event):
    """Duration help text mentions default when multiple submission types exist."""
    SubmissionTypeFactory(event=event)

    form = SubmissionForm(event=event)

    assert "default duration" in str(form.fields["duration"].help_text)


def test_submission_form_init_no_duration_help_text_with_single_type(event):
    """Duration help text is not appended when only one submission type exists."""
    form = SubmissionForm(event=event)

    assert "default duration" not in str(form.fields["duration"].help_text)


def test_submission_form_init_abstract_rows(event):
    form = SubmissionForm(event=event)

    assert form.fields["abstract"].widget.attrs["rows"] == 2


def test_submission_form_init_read_only_disables_model_fields(event):
    """ReadOnlyFlag disables fields set by ModelForm before SubmissionForm adds dynamic fields."""
    form = SubmissionForm(event=event, read_only=True)

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


def test_submission_form_clean_read_only_raises_validation_error(event):
    form = SubmissionForm(event=event, read_only=True, data={"title": "Test"})

    assert not form.is_valid()
    assert "__all__" in form.errors


def test_submission_form_init_anonymise_uses_anonymised_data(event):
    """When anonymise=True, initial values come from instance.anonymised."""
    submission = SubmissionFactory(
        event=event,
        title="Original Title",
        anonymised={"_anonymised": True, "title": "Anonymised Title"},
    )

    form = SubmissionForm(event=event, anonymise=True, instance=submission)

    assert form.initial["title"] == "Anonymised Title"


def test_submission_form_init_anonymise_falls_back_to_instance_attr(event):
    """When anonymise=True and field not in anonymised_data, uses instance attr."""
    submission = SubmissionFactory(
        event=event, title="Original Title", anonymised={"_anonymised": True}
    )

    form = SubmissionForm(event=event, anonymise=True, instance=submission)

    assert form.initial["title"] == "Original Title"


def test_submission_form_clean_start_before_event_raises_error(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)
    early = event.datetime_from - dt.timedelta(days=1)

    form = SubmissionForm(
        event=event,
        instance=submission,
        data=_base_data(
            submission,
            room=room.pk,
            start=early,
            end=event.datetime_from + dt.timedelta(hours=1),
        ),
    )

    assert not form.is_valid()
    assert "start" in form.errors


def test_submission_form_clean_end_after_event_raises_error(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)
    late = event.datetime_to + dt.timedelta(days=1)

    form = SubmissionForm(
        event=event,
        instance=submission,
        data=_base_data(submission, room=room.pk, start=event.datetime_from, end=late),
    )

    assert not form.is_valid()
    assert "end" in form.errors


def test_submission_form_clean_start_after_end_raises_error(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)

    form = SubmissionForm(
        event=event,
        instance=submission,
        data=_base_data(
            submission,
            room=room.pk,
            start=event.datetime_from + dt.timedelta(hours=2),
            end=event.datetime_from + dt.timedelta(hours=1),
        ),
    )

    assert not form.is_valid()
    assert "end" in form.errors


def test_submission_form_clean_room_without_start_raises_error(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)

    form = SubmissionForm(
        event=event, instance=submission, data=_base_data(submission, room=room.pk)
    )

    assert not form.is_valid()
    assert "room" in form.errors


def test_submission_form_clean_start_without_room_raises_error(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    form = SubmissionForm(
        event=event,
        instance=submission,
        data=_base_data(submission, start=event.datetime_from),
    )

    assert not form.is_valid()
    assert "start" in form.errors


def test_submission_form_clean_valid_scheduling(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)
    start = event.datetime_from + dt.timedelta(hours=1)
    end = event.datetime_from + dt.timedelta(hours=2)

    form = SubmissionForm(
        event=event,
        instance=submission,
        data=_base_data(submission, room=room.pk, start=start, end=end),
    )

    assert form.is_valid(), form.errors


def test_submission_form_clean_no_scheduling_fields_is_valid(event):
    """Omitting all scheduling fields is fine."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    form = SubmissionForm(event=event, instance=submission, data=_base_data(submission))

    assert form.is_valid(), form.errors


def test_submission_form_save_new_sets_state(event):
    """Creating a new submission via the form calls set_state with the chosen state."""
    form = SubmissionForm(event=event, data=_new_data(event))
    assert form.is_valid(), form.errors
    form.instance.event = event
    result = form.save()

    assert result.pk is not None
    assert result.state == SubmissionStates.SUBMITTED


def test_submission_form_save_new_sets_content_locale_from_event(event):
    """When content_locale field is hidden (single locale), the event's locale is used."""
    form = SubmissionForm(event=event, data=_new_data(event))
    assert form.is_valid(), form.errors
    form.instance.event = event
    result = form.save()

    assert result.content_locale == event.locale


def test_submission_form_save_new_preserves_content_locale_when_field_present():
    """When content_locale field is visible, it uses the submitted value."""
    event = EventFactory(content_locale_array="en,de")
    form = SubmissionForm(event=event, data=_new_data(event, content_locale="de"))
    assert form.is_valid(), form.errors
    form.instance.event = event
    result = form.save()

    assert result.content_locale == "de"


def test_submission_form_save_existing_duration_change_updates_slots(event):
    """Changing duration triggers update_duration on the submission."""
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, duration=30
    )
    slot = TalkSlotFactory(submission=submission, is_visible=True)

    form = SubmissionForm(
        event=event,
        instance=submission,
        data=_base_data(
            submission, duration=60, room=slot.room.pk, start=slot.start, end=slot.end
        ),
    )
    assert form.is_valid(), form.errors
    form.save()

    slot.refresh_from_db()

    assert slot.end == slot.start + dt.timedelta(minutes=60)


def test_submission_form_save_existing_track_change_updates_review_scores(event):
    """Changing track triggers update_review_scores."""
    track1 = TrackFactory(event=event)
    track2 = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track1)

    form = SubmissionForm(
        event=event, instance=submission, data=_base_data(submission, track=track2.pk)
    )
    assert form.is_valid(), form.errors
    result = form.save()

    assert result.track == track2


def test_submission_form_save_scheduling_updates_slot(event):
    """Saving an accepted submission with room/start/end updates the WIP slot."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=submission, is_visible=True)
    room = RoomFactory(event=event)
    start = event.datetime_from + dt.timedelta(hours=2)
    end = event.datetime_from + dt.timedelta(hours=3)

    form = SubmissionForm(
        event=event,
        instance=submission,
        data=_base_data(submission, room=room.pk, start=start, end=end),
    )
    assert form.is_valid(), form.errors
    form.save()

    slot = submission.slots.filter(schedule=submission.event.wip_schedule).first()

    assert slot.room == room
    assert slot.start == start
    assert slot.end == end


def test_submission_form_save_clearing_start_removes_slots(event):
    """Clearing scheduling fields deletes scheduled WIP slots."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=submission, is_visible=True)

    form = SubmissionForm(event=event, instance=submission, data=_base_data(submission))
    assert form.is_valid(), form.errors
    form.save()

    scheduled_slots = TalkSlot.objects.filter(
        submission=submission,
        schedule=submission.event.wip_schedule,
        start__isnull=False,
    )

    assert scheduled_slots.count() == 0


def test_submission_form_save_slot_count_change_updates_talk_slots():
    """Changing slot_count triggers update_talk_slots."""
    event = EventFactory(feature_flags={"present_multiple_times": True})
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, slot_count=1
    )
    TalkSlotFactory(submission=submission, is_visible=True)

    form = SubmissionForm(
        event=event, instance=submission, data=_base_data(submission, slot_count=2)
    )
    assert form.is_valid(), form.errors
    form.save()

    slot_count = TalkSlot.objects.filter(
        submission=submission, schedule=submission.event.wip_schedule
    ).count()

    assert slot_count == 2


def test_submission_form_meta_media_includes_js():
    form = SubmissionForm.__dict__["Media"]
    assert any("submission.js" in str(js) for js in form.js)


def test_anonymise_form_raises_on_unsaved_instance():
    with pytest.raises(ValueError, match="Cannot anonymise unsaved submission"):
        AnonymiseForm(instance=None)


def test_anonymise_form_raises_on_instance_without_pk(event):

    unsaved = Submission(event=event, title="Test")

    with pytest.raises(ValueError, match="Cannot anonymise unsaved submission"):
        AnonymiseForm(instance=unsaved)


def test_anonymise_form_init_sets_plaintext_on_fields(event):
    """Each field gets a `plaintext` attribute from the original instance."""
    submission = SubmissionFactory(event=event, title="Original")

    form = AnonymiseForm(instance=submission)

    assert form.fields["title"].plaintext == "Original"


def test_anonymise_form_init_removes_content_locale_field(event):
    submission = SubmissionFactory(event=event)

    form = AnonymiseForm(instance=submission)

    assert "content_locale" not in form.fields


def test_anonymise_form_init_removes_non_model_fields(event):
    """Fields that aren't submission attributes (like room, start, end) are removed."""
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
    """Fields that match the original instance value are not stored."""
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
    """Saving AnonymiseForm only updates the anonymised field, not the submission fields."""
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


def test_submission_state_change_form_pending_field():
    form = SubmissionStateChangeForm()

    assert "pending" in form.fields
    assert form.fields["pending"].required is False
    assert form.fields["pending"].initial is False


def test_submission_state_change_form_valid_with_pending_true():
    form = SubmissionStateChangeForm(data={"pending": True})

    assert form.is_valid()
    assert form.cleaned_data["pending"] is True


def test_submission_state_change_form_valid_without_data():
    form = SubmissionStateChangeForm(data={})

    assert form.is_valid()
    assert form.cleaned_data["pending"] is False


def test_add_speaker_form_init_removes_locale_for_single_locale(event):
    form = AddSpeakerForm(event=event)

    assert "locale" not in form.fields


def test_add_speaker_form_init_keeps_locale_for_multiple_locales():
    event = EventFactory(locale_array="en,de")

    form = AddSpeakerForm(event=event)

    assert "locale" in form.fields
    locale_codes = [code for code, _ in form.fields["locale"].choices]
    assert "en" in locale_codes
    assert "de" in locale_codes
    assert form.fields["locale"].initial == event.locale


def test_add_speaker_form_clean_name_without_email_raises_error(event):
    form = AddSpeakerForm(event=event, data={"name": "Speaker Name"})

    assert not form.is_valid()
    assert "__all__" in form.errors


def test_add_speaker_form_clean_email_only_is_valid(event):
    form = AddSpeakerForm(event=event, data={"email": "speaker@example.com"})

    assert form.is_valid(), form.errors


def test_add_speaker_form_clean_both_name_and_email_is_valid(event):
    form = AddSpeakerForm(
        event=event, data={"email": "speaker@example.com", "name": "Speaker Name"}
    )

    assert form.is_valid(), form.errors


def test_add_speaker_form_clean_empty_is_valid(event):
    """Both email and name empty is valid (form allows optional submission)."""
    form = AddSpeakerForm(event=event, data={})

    assert form.is_valid(), form.errors


def test_add_speaker_form_email_uses_select_widget(event):
    form = AddSpeakerForm(event=event)

    assert isinstance(form.fields["email"].widget, forms.Select)


def test_add_speaker_inline_form_uses_inline_renderer(event):

    form = AddSpeakerInlineForm(event=event)

    assert form.default_renderer is InlineFormLabelRenderer
