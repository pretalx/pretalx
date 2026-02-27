import datetime as dt
import json

import pytest
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.orga.forms.cfp import (
    AccessCodeSendForm,
    AnswerOptionForm,
    CfPFieldConfigForm,
    CfPForm,
    CfPSettingsForm,
    QuestionFilterForm,
    QuestionForm,
    ReminderFilterForm,
    StepHeaderForm,
    SubmissionTypeForm,
    SubmitterAccessCodeForm,
    TrackForm,
)
from pretalx.submission.models import SubmissionStates, SubmissionType
from pretalx.submission.models.question import QuestionRequired, QuestionVariant
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_cfp_settings_form_init_populates_json_fields():
    """Initial values are loaded from the event's JSON fields."""
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = True
        event.mail_settings["mail_on_new_submission"] = True
        event.save()

        form = CfPSettingsForm(obj=event)

    assert form.fields["use_tracks"].initial is True
    assert form.fields["mail_on_new_submission"].initial is True


@pytest.mark.django_db
def test_cfp_settings_form_init_appends_email_to_help_text():
    """When the event has an email, the help text includes a mailto link."""
    with scopes_disabled():
        event = EventFactory(email="test@example.com")

        form = CfPSettingsForm(obj=event)

    assert "test@example.com" in form.fields["mail_on_new_submission"].help_text


@pytest.mark.django_db
def test_cfp_settings_form_init_no_email_skips_mailto():
    """When the event has no email, the help text does not include a mailto link."""
    with scopes_disabled():
        event = EventFactory(email="")

        form = CfPSettingsForm(obj=event)

    assert "mailto:" not in str(form.fields["mail_on_new_submission"].help_text)


@pytest.mark.django_db
def test_cfp_settings_form_save_updates_json_fields():
    """Saving the form writes back to the event's JSON fields."""
    with scopes_disabled():
        event = EventFactory()

        form = CfPSettingsForm(
            data={
                "use_tracks": True,
                "present_multiple_times": False,
                "mail_on_new_submission": True,
                "submission_public_review": False,
                "speakers_can_edit_submissions": True,
            },
            obj=event,
        )
        assert form.is_valid(), form.errors
        form.save()
        event.refresh_from_db()

    assert event.feature_flags["use_tracks"] is True
    assert event.feature_flags["present_multiple_times"] is False
    assert event.feature_flags["submission_public_review"] is False
    assert event.mail_settings["mail_on_new_submission"] is True
    assert event.feature_flags["speakers_can_edit_submissions"] is True


@pytest.mark.django_db
def test_cfp_settings_form_read_only_rejects_changes():
    """A read-only form prevents saving."""
    with scopes_disabled():
        event = EventFactory()

        form = CfPSettingsForm(
            data={
                "use_tracks": True,
                "present_multiple_times": False,
                "mail_on_new_submission": False,
                "submission_public_review": False,
                "speakers_can_edit_submissions": True,
            },
            obj=event,
            read_only=True,
        )

    assert not form.is_valid()


@pytest.mark.django_db
def test_cfp_form_valid_with_minimal_data():
    with scopes_disabled():
        event = EventFactory()
        cfp = event.cfp

        form = CfPForm(
            data={
                "headline_0": "Submit your talk!",
                "text_0": "We want your talks.",
                "count_length_in": "chars",
            },
            instance=cfp,
            locales=event.locales,
        )

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_cfp_form_saves_json_fields():
    """show_deadline and count_length_in are stored in cfp.settings."""
    with scopes_disabled():
        event = EventFactory()
        cfp = event.cfp

        form = CfPForm(
            data={
                "headline_0": "Submit",
                "text_0": "",
                "show_deadline": True,
                "count_length_in": "words",
            },
            instance=cfp,
            locales=event.locales,
        )
        assert form.is_valid(), form.errors
        form.save()
        cfp.refresh_from_db()

    assert cfp.settings["show_deadline"] is True
    assert cfp.settings["count_length_in"] == "words"


@pytest.mark.django_db
def test_question_form_init_removes_tracks_when_not_configured():
    """Tracks field is removed when the event doesn't use tracks."""
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = False
        event.save()

        form = QuestionForm(event=event, locales=event.locales)

    assert "tracks" not in form.fields


@pytest.mark.django_db
def test_question_form_init_removes_tracks_when_no_tracks_exist():
    """Tracks field is removed when no tracks exist even if use_tracks is on."""
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = True
        event.save()

        form = QuestionForm(event=event, locales=event.locales)

    assert "tracks" not in form.fields


@pytest.mark.django_db
def test_question_form_init_shows_tracks_when_configured():
    """Tracks field is present with the correct queryset when tracks are set up."""
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = True
        event.save()
        track = TrackFactory(event=event)
        cfp = event.cfp
        fields = cfp.fields
        fields["track"]["visibility"] = "optional"
        cfp.fields = fields
        cfp.save()

        form = QuestionForm(event=event, locales=event.locales)

    assert "tracks" in form.fields
    assert track in form.fields["tracks"].queryset


@pytest.mark.django_db
def test_question_form_init_keeps_submission_types_when_they_exist():
    """submission_types field is present when the event has submission types."""
    with scopes_disabled():
        event = EventFactory()

        form = QuestionForm(event=event, locales=event.locales)

    assert "submission_types" in form.fields


@pytest.mark.django_db
def test_question_form_init_sets_submission_types_queryset():
    with scopes_disabled():
        event = EventFactory()
        extra_type = SubmissionTypeFactory(event=event)

        form = QuestionForm(event=event, locales=event.locales)

    assert "submission_types" in form.fields
    assert extra_type in form.fields["submission_types"].queryset


@pytest.mark.django_db
def test_question_form_clean_options_plain_text():
    """Uploading a plain text file with one option per line returns a list of strings."""
    with scopes_disabled():
        event = EventFactory()
        content = b"Option A\nOption B\nOption C\n"
        upload = SimpleUploadedFile("options.txt", content, content_type="text/plain")

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": "Pick one",
                "variant": QuestionVariant.CHOICES,
                "question_required": QuestionRequired.OPTIONAL,
                "contains_personal_data": False,
            },
            files={"options": upload},
            event=event,
            locales=event.locales,
        )
        form.is_valid()

    assert form.cleaned_data["options"] == ["Option A", "Option B", "Option C"]


@pytest.mark.django_db
def test_question_form_clean_options_json():
    """Uploading a JSON file with i18n objects returns LazyI18nString instances."""
    with scopes_disabled():
        event = EventFactory()
        data = [{"en": "English", "de": "Deutsch"}, {"en": "Yes", "de": "Ja"}]
        content = json.dumps(data).encode()
        upload = SimpleUploadedFile(
            "opts.json", content, content_type="application/json"
        )

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": "Pick one",
                "variant": QuestionVariant.CHOICES,
                "question_required": QuestionRequired.OPTIONAL,
                "contains_personal_data": False,
            },
            files={"options": upload},
            event=event,
            locales=event.locales,
        )
        form.is_valid()

    options = form.cleaned_data["options"]
    assert len(options) == 2
    assert options[0].data == {"en": "English", "de": "Deutsch"}


@pytest.mark.django_db
def test_question_form_clean_options_invalid_file():
    """Uploading an unreadable file raises a validation error."""
    with scopes_disabled():
        event = EventFactory()
        upload = SimpleUploadedFile(
            "bad.bin", b"\x80\x81\x82", content_type="application/octet-stream"
        )

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": "Pick one",
                "variant": QuestionVariant.CHOICES,
                "question_required": QuestionRequired.OPTIONAL,
                "contains_personal_data": False,
            },
            files={"options": upload},
            event=event,
            locales=event.locales,
        )
        form.is_valid()

    assert "options" in form.errors


@pytest.mark.django_db
def test_question_form_clean_options_json_not_list():
    """Uploading a JSON object (not list) falls back to line splitting."""
    with scopes_disabled():
        event = EventFactory()
        content = json.dumps({"key": "value"}).encode()
        upload = SimpleUploadedFile(
            "bad.json", content, content_type="application/json"
        )

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": "Pick one",
                "variant": QuestionVariant.CHOICES,
                "question_required": QuestionRequired.OPTIONAL,
                "contains_personal_data": False,
            },
            files={"options": upload},
            event=event,
            locales=event.locales,
        )
        form.is_valid()

    # Falls back to line-split: '{"key": "value"}' as a single line
    assert len(form.cleaned_data["options"]) == 1


@pytest.mark.django_db
def test_question_form_clean_options_json_list_of_non_dicts():
    """A JSON array of strings (not objects) falls back to line-splitting."""
    with scopes_disabled():
        event = EventFactory()
        content = json.dumps(["Option A", "Option B"]).encode()
        upload = SimpleUploadedFile(
            "opts.json", content, content_type="application/json"
        )

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": "Pick one",
                "variant": QuestionVariant.CHOICES,
                "question_required": QuestionRequired.OPTIONAL,
                "contains_personal_data": False,
            },
            files={"options": upload},
            event=event,
            locales=event.locales,
        )
        form.is_valid()

    # Falls back to line-split: '["Option A", "Option B"]' as a single line
    assert form.cleaned_data["options"] == ['["Option A", "Option B"]']


@pytest.mark.django_db
def test_question_form_clean_options_empty_file():
    """No options file uploaded returns None (no options)."""
    with scopes_disabled():
        event = EventFactory()

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": "Pick one",
                "variant": QuestionVariant.CHOICES,
                "question_required": QuestionRequired.OPTIONAL,
                "contains_personal_data": False,
            },
            event=event,
            locales=event.locales,
        )
        form.is_valid()

    assert form.cleaned_data.get("options") is None


@pytest.mark.django_db
def test_question_form_clean_after_deadline_requires_deadline():
    """Setting question_required=AFTER_DEADLINE without a deadline is an error."""
    with scopes_disabled():
        event = EventFactory()

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": "Pick one",
                "variant": QuestionVariant.STRING,
                "question_required": QuestionRequired.AFTER_DEADLINE,
                "deadline": "",
                "contains_personal_data": False,
            },
            event=event,
            locales=event.locales,
        )
        valid = form.is_valid()

    assert not valid
    assert "deadline" in form.errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    "question_required",
    (QuestionRequired.REQUIRED, QuestionRequired.OPTIONAL),
    ids=["required", "optional"],
)
def test_question_form_clean_required_or_optional_clears_deadline(question_required):
    """Setting question_required to REQUIRED or OPTIONAL clears the deadline."""
    with scopes_disabled():
        event = EventFactory()

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": "Pick one",
                "variant": QuestionVariant.STRING,
                "question_required": question_required,
                "deadline": now().isoformat(),
                "contains_personal_data": False,
            },
            event=event,
            locales=event.locales,
        )
        form.is_valid()

    assert form.cleaned_data["deadline"] is None


@pytest.mark.django_db
def test_question_form_clean_replace_without_options_is_error():
    """Checking 'replace options' without uploading new options is an error."""
    with scopes_disabled():
        event = EventFactory()

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": "Pick one",
                "variant": QuestionVariant.CHOICES,
                "question_required": QuestionRequired.OPTIONAL,
                "options_replace": True,
                "contains_personal_data": False,
            },
            event=event,
            locales=event.locales,
        )
        valid = form.is_valid()

    assert not valid
    assert "options_replace" in form.errors


@pytest.mark.django_db
def test_question_form_clean_public_clears_limit_teams():
    """Making a question public clears the limit_teams field."""
    with scopes_disabled():
        event = EventFactory()

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": "Pick one",
                "variant": QuestionVariant.STRING,
                "question_required": QuestionRequired.OPTIONAL,
                "is_public": True,
                "contains_personal_data": False,
            },
            event=event,
            locales=event.locales,
        )
        form.is_valid()

    assert "limit_teams" not in form.cleaned_data


@pytest.mark.django_db
def test_question_form_clean_identifier_validates_uniqueness():
    """Duplicate identifiers within the same event are rejected."""
    with scopes_disabled():
        event = EventFactory()
        QuestionFactory(event=event, identifier="MY-ID")

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": "Another question",
                "variant": QuestionVariant.STRING,
                "question_required": QuestionRequired.OPTIONAL,
                "identifier": "MY-ID",
                "contains_personal_data": False,
            },
            event=event,
            locales=event.locales,
        )
        valid = form.is_valid()

    assert not valid
    assert "identifier" in form.errors


@pytest.mark.django_db
def test_question_form_clean_identifier_allows_same_instance():
    """A question can keep its own identifier without conflict."""
    with scopes_disabled():
        event = EventFactory()
        question = QuestionFactory(event=event, identifier="MY-ID")

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": "Updated question",
                "variant": QuestionVariant.STRING,
                "question_required": QuestionRequired.OPTIONAL,
                "identifier": "MY-ID",
                "contains_personal_data": False,
            },
            instance=question,
            event=event,
            locales=event.locales,
        )
        valid = form.is_valid()

    assert valid, form.errors


@pytest.mark.django_db
def test_question_form_save_creates_options_with_replace():
    """Saving with replace=True deletes old options/answers and creates new ones."""
    with scopes_disabled():
        event = EventFactory()
        question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
        old_option = AnswerOptionFactory(question=question, answer="Old")
        AnswerFactory(question=question, answer="Old")

        content = b"New A\nNew B\n"
        upload = SimpleUploadedFile("options.txt", content, content_type="text/plain")

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": str(question.question),
                "variant": QuestionVariant.CHOICES,
                "question_required": QuestionRequired.OPTIONAL,
                "options_replace": True,
                "contains_personal_data": False,
            },
            files={"options": upload},
            instance=question,
            event=event,
            locales=event.locales,
        )
        assert form.is_valid(), form.errors
        form.save()

        options = list(
            question.options.order_by("position").values_list("answer", flat=True)
        )
        assert options == ["New A", "New B"]
        assert question.answers.count() == 0
        assert not question.options.filter(pk=old_option.pk).exists()


@pytest.mark.django_db
def test_question_form_save_adds_options_without_duplicates():
    """Saving without replace adds only new options, skipping existing ones."""
    with scopes_disabled():
        event = EventFactory()
        question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
        AnswerOptionFactory(question=question, answer="Existing", position=1)

        content = b"Existing\nBrand New\n"
        upload = SimpleUploadedFile("options.txt", content, content_type="text/plain")

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": str(question.question),
                "variant": QuestionVariant.CHOICES,
                "question_required": QuestionRequired.OPTIONAL,
                "contains_personal_data": False,
            },
            files={"options": upload},
            instance=question,
            event=event,
            locales=event.locales,
        )
        assert form.is_valid(), form.errors
        form.save()

        assert question.options.count() == 2
        new_option = question.options.get(answer="Brand New")
        assert new_option.position == 2


@pytest.mark.django_db
def test_question_form_save_without_options_returns_instance():
    """Saving without any options file just returns the question instance."""
    with scopes_disabled():
        event = EventFactory()
        question = QuestionFactory(event=event, variant=QuestionVariant.STRING)

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": "Updated text",
                "variant": QuestionVariant.STRING,
                "question_required": QuestionRequired.OPTIONAL,
                "contains_personal_data": False,
            },
            instance=question,
            event=event,
            locales=event.locales,
        )
        assert form.is_valid(), form.errors
        result = form.save()

    assert result.pk == question.pk


@pytest.mark.django_db
def test_question_form_save_updates_existing_option_positions():
    """When uploading options without replace, existing option positions are updated."""
    with scopes_disabled():
        event = EventFactory()
        question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
        existing = AnswerOptionFactory(question=question, answer="A", position=5)

        content = b"A\nB\n"
        upload = SimpleUploadedFile("options.txt", content, content_type="text/plain")

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": str(question.question),
                "variant": QuestionVariant.CHOICES,
                "question_required": QuestionRequired.OPTIONAL,
                "contains_personal_data": False,
            },
            files={"options": upload},
            instance=question,
            event=event,
            locales=event.locales,
        )
        assert form.is_valid(), form.errors
        form.save()

        existing.refresh_from_db()
        assert existing.position == 1


@pytest.mark.django_db
def test_question_form_save_adds_i18n_options_on_multilingual_event():
    """On a multilingual event, i18n options are matched and merged correctly."""
    with scopes_disabled():
        event = EventFactory()
        event.locale_array = "en,de"
        event.content_locale_array = "en,de"
        event.save()
        question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
        AnswerOptionFactory(question=question, answer="Existing", position=1)

        data = [{"en": "Existing", "de": "Bestehend"}, {"en": "New", "de": "Neu"}]
        content = json.dumps(data).encode()
        upload = SimpleUploadedFile(
            "opts.json", content, content_type="application/json"
        )

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": str(question.question),
                "variant": QuestionVariant.CHOICES,
                "question_required": QuestionRequired.OPTIONAL,
                "contains_personal_data": False,
            },
            files={"options": upload},
            instance=question,
            event=event,
            locales=event.locales,
        )
        assert form.is_valid(), form.errors
        form.save()

        assert question.options.count() == 2


@pytest.mark.django_db
def test_question_form_save_adds_only_existing_options_no_new():
    """When all uploaded options already exist, no new options are created."""
    with scopes_disabled():
        event = EventFactory()
        question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
        AnswerOptionFactory(question=question, answer="Only", position=3)

        content = b"Only\n"
        upload = SimpleUploadedFile("options.txt", content, content_type="text/plain")

        form = QuestionForm(
            data={
                "target": "submission",
                "question_0": str(question.question),
                "variant": QuestionVariant.CHOICES,
                "question_required": QuestionRequired.OPTIONAL,
                "contains_personal_data": False,
            },
            files={"options": upload},
            instance=question,
            event=event,
            locales=event.locales,
        )
        assert form.is_valid(), form.errors
        form.save()

        assert question.options.count() == 1
        option = question.options.first()
        assert option.position == 1


@pytest.mark.django_db
def test_answer_option_form_valid_with_answer():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.CHOICES)
        form = AnswerOptionForm(
            data={"answer_0": "My option"}, locales=question.event.locales
        )

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_submission_type_form_valid_with_minimal_data():
    with scopes_disabled():
        event = EventFactory()

        form = SubmissionTypeForm(
            data={"name_0": "Workshop", "default_duration": "60"},
            event=event,
            locales=event.locales,
        )
        valid = form.is_valid()

    assert valid, form.errors


@pytest.mark.django_db
def test_submission_type_form_clean_name_rejects_duplicate():
    with scopes_disabled():
        event = EventFactory()
        SubmissionTypeFactory(event=event, name="Workshop")

        form = SubmissionTypeForm(
            data={"name_0": "Workshop", "default_duration": "60"},
            event=event,
            locales=event.locales,
        )
        valid = form.is_valid()

    assert not valid
    assert "name" in form.errors


@pytest.mark.django_db
def test_submission_type_form_clean_name_allows_same_instance():
    """Editing a submission type's other fields should not conflict with its own name."""
    with scopes_disabled():
        event = EventFactory()
        stype = SubmissionTypeFactory(event=event, name="Workshop")

        form = SubmissionTypeForm(
            data={"name_0": "Workshop", "default_duration": "90"},
            instance=stype,
            event=event,
            locales=event.locales,
        )
        valid = form.is_valid()

    assert valid, form.errors


@pytest.mark.django_db
def test_submission_type_form_save_updates_default_duration():
    """Saving the form with a changed default_duration calls update_duration,
    updating submissions that use the default."""
    with scopes_disabled():
        event = EventFactory()
        stype = SubmissionTypeFactory(event=event, name="Workshop", default_duration=30)
        SubmissionFactory(event=event, submission_type=stype, duration=None)

        form = SubmissionTypeForm(
            data={"name_0": "Workshop", "default_duration": "60"},
            instance=stype,
            event=event,
            locales=event.locales,
        )
        assert form.is_valid(), form.errors
        result = form.save()

        result.refresh_from_db()

    assert result.default_duration == 60


@pytest.mark.django_db
def test_submission_type_form_save_without_duration_change():
    """Saving with the same default_duration does not trigger update_duration."""
    with scopes_disabled():
        event = EventFactory()
        stype = SubmissionTypeFactory(event=event, name="Workshop", default_duration=60)

        form = SubmissionTypeForm(
            data={"name_0": "Renamed Workshop", "default_duration": "60"},
            instance=stype,
            event=event,
            locales=event.locales,
        )
        assert form.is_valid(), form.errors
        result = form.save()

        result.refresh_from_db()

    assert str(result.name) == "Renamed Workshop"
    assert result.default_duration == 60


@pytest.mark.django_db
def test_question_form_init_removes_submission_types_when_none_exist():
    """submission_types field is removed when the event has no submission types."""
    with scopes_disabled():
        event = EventFactory()
        other_event = EventFactory()
        # Move all submission types to another event so this one has zero
        SubmissionType.objects.filter(event=event).update(event=other_event)
        form = QuestionForm(event=event, locales=event.locales)

    assert "submission_types" not in form.fields


@pytest.mark.django_db
def test_track_form_valid_with_minimal_data():
    with scopes_disabled():
        event = EventFactory()

        form = TrackForm(
            data={"name_0": "Security", "color": "#ff0000"},
            event=event,
            locales=event.locales,
        )
        valid = form.is_valid()

    assert valid, form.errors


@pytest.mark.django_db
def test_track_form_clean_name_rejects_duplicate():
    with scopes_disabled():
        event = EventFactory()
        TrackFactory(event=event, name="Security")

        form = TrackForm(
            data={"name_0": "Security", "color": "#00ff00"},
            event=event,
            locales=event.locales,
        )
        valid = form.is_valid()

    assert not valid
    assert "name" in form.errors


@pytest.mark.django_db
def test_track_form_clean_name_allows_same_instance():
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event, name="Security")

        form = TrackForm(
            data={"name_0": "Security", "color": "#ff0000"},
            instance=track,
            event=event,
            locales=event.locales,
        )
        valid = form.is_valid()

    assert valid, form.errors


@pytest.mark.django_db
def test_track_form_init_adds_access_code_link_for_existing_track():
    """Existing tracks get a help text link to create access codes."""
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event)

        form = TrackForm(instance=track, event=event, locales=event.locales)

    assert str(track.pk) in form.fields["requires_access_code"].help_text


@pytest.mark.django_db
def test_track_form_init_no_access_code_link_for_new_track():
    """New tracks (no pk) don't get the access code creation link."""
    with scopes_disabled():
        event = EventFactory()

        form = TrackForm(event=event, locales=event.locales)

    assert "<a href=" not in str(form.fields["requires_access_code"].help_text)


@pytest.mark.django_db
def test_access_code_form_generates_code_for_new_instance():
    with scopes_disabled():
        event = EventFactory()

        form = SubmitterAccessCodeForm(event=event)

    assert len(form.initial["code"]) > 0


@pytest.mark.django_db
def test_access_code_form_does_not_overwrite_existing_code():
    with scopes_disabled():
        event = EventFactory()
        access_code = SubmitterAccessCodeFactory(event=event)

        form = SubmitterAccessCodeForm(instance=access_code, event=event)

    assert form.instance.code == access_code.code


@pytest.mark.django_db
def test_access_code_form_filters_submission_types_by_event():
    with scopes_disabled():
        event = EventFactory()
        other_event = EventFactory()
        our_type = SubmissionTypeFactory(event=event)
        other_type = SubmissionTypeFactory(event=other_event)

        form = SubmitterAccessCodeForm(event=event)

    assert our_type in form.fields["submission_types"].queryset
    assert other_type not in form.fields["submission_types"].queryset


@pytest.mark.django_db
def test_access_code_form_shows_tracks_when_enabled():
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = True
        event.save()
        track = TrackFactory(event=event)

        form = SubmitterAccessCodeForm(event=event)

    assert "tracks" in form.fields
    assert track in form.fields["tracks"].queryset


@pytest.mark.django_db
def test_access_code_form_hides_tracks_when_disabled():
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = False
        event.save()

        form = SubmitterAccessCodeForm(event=event)

    assert "tracks" not in form.fields


@pytest.mark.django_db
def test_access_code_send_form_init_populates_subject_and_text():
    with scopes_disabled():
        event = EventFactory()
        access_code = SubmitterAccessCodeFactory(event=event)
        user = UserFactory()

        form = AccessCodeSendForm(instance=access_code, user=user)

    assert str(event.name) in form.initial["subject"]
    assert str(event.name) in form.initial["text"]


@pytest.mark.django_db
def test_access_code_send_form_includes_tracks_in_text():
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = True
        event.save()
        track = TrackFactory(event=event, name="Security")
        access_code = SubmitterAccessCodeFactory(event=event)
        access_code.tracks.add(track)
        user = UserFactory()

        form = AccessCodeSendForm(instance=access_code, user=user)

    assert "Security" in form.initial["text"]


@pytest.mark.django_db
def test_access_code_send_form_includes_submission_types_in_text():
    with scopes_disabled():
        event = EventFactory()
        stype = SubmissionTypeFactory(event=event, name="Lightning Talk")
        access_code = SubmitterAccessCodeFactory(event=event)
        access_code.submission_types.add(stype)
        user = UserFactory()

        form = AccessCodeSendForm(instance=access_code, user=user)

    assert "Lightning Talk" in form.initial["text"]


@pytest.mark.django_db
def test_access_code_send_form_includes_valid_until_in_text():
    with scopes_disabled():
        event = EventFactory()
        valid_until = now()
        access_code = SubmitterAccessCodeFactory(event=event, valid_until=valid_until)
        user = UserFactory()

        form = AccessCodeSendForm(instance=access_code, user=user)

    assert valid_until.strftime("%Y-%m-%d") in form.initial["text"]


@pytest.mark.django_db
def test_access_code_send_form_generic_text_without_restrictions():
    """When no tracks or types are set, the text has a generic CfP message."""
    with scopes_disabled():
        event = EventFactory()
        access_code = SubmitterAccessCodeFactory(event=event)
        user = UserFactory()

        form = AccessCodeSendForm(instance=access_code, user=user)

    assert "submit a proposal" in form.initial["text"].lower()


@pytest.mark.django_db
def test_access_code_send_form_save_sends_invite():
    djmail.outbox = []
    with scopes_disabled():
        event = EventFactory()
        access_code = SubmitterAccessCodeFactory(event=event)
        user = UserFactory()

        form = AccessCodeSendForm(
            data={
                "to": "recipient@example.com",
                "subject": "Your access code",
                "text": "Here it is.",
            },
            instance=access_code,
            user=user,
        )
        assert form.is_valid(), form.errors
        form.save()

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["recipient@example.com"]


@pytest.mark.django_db
def test_question_filter_form_init_sets_submission_type_queryset():
    with scopes_disabled():
        event = EventFactory()
        stype = event.cfp.default_type

        form = QuestionFilterForm(event=event)

    assert stype in form.fields["submission_type"].queryset


@pytest.mark.django_db
def test_question_filter_form_hides_track_when_disabled():
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = False
        event.save()

        form = QuestionFilterForm(event=event)

    assert "track" not in form.fields


@pytest.mark.django_db
def test_question_filter_form_shows_track_when_enabled():
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = True
        event.save()
        track = TrackFactory(event=event)

        form = QuestionFilterForm(event=event)

    assert "track" in form.fields
    assert track in form.fields["track"].queryset


@pytest.mark.django_db
def test_question_filter_form_get_submissions_no_filter():
    """Without filters, returns all submissions."""
    with scopes_disabled():
        event = EventFactory()
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)

        form = QuestionFilterForm(data={"role": "", "submission_type": ""}, event=event)
        assert form.is_valid(), form.errors
        talks = form.get_submissions()

    assert set(talks) == {sub1, sub2}


@pytest.mark.django_db
def test_question_filter_form_get_submissions_accepted_role():
    """Filtering by 'accepted' includes accepted and confirmed."""
    with scopes_disabled():
        event = EventFactory()
        accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

        form = QuestionFilterForm(
            data={"role": "accepted", "submission_type": ""}, event=event
        )
        assert form.is_valid(), form.errors
        talks = form.get_submissions()

    assert set(talks) == {accepted, confirmed}


@pytest.mark.django_db
def test_question_filter_form_get_submissions_confirmed_role():
    """Filtering by 'confirmed' includes only confirmed submissions."""
    with scopes_disabled():
        event = EventFactory()
        confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

        form = QuestionFilterForm(
            data={"role": "confirmed", "submission_type": ""}, event=event
        )
        assert form.is_valid(), form.errors
        talks = form.get_submissions()

    assert list(talks) == [confirmed]


@pytest.mark.django_db
def test_question_filter_form_get_submissions_by_track():
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = True
        event.save()
        track = TrackFactory(event=event)
        on_track = SubmissionFactory(event=event, track=track)
        SubmissionFactory(event=event)

        form = QuestionFilterForm(
            data={"role": "", "submission_type": "", "track": track.pk}, event=event
        )
        assert form.is_valid(), form.errors
        talks = form.get_submissions()

    assert list(talks) == [on_track]


@pytest.mark.django_db
def test_question_filter_form_get_submissions_by_submission_type():
    with scopes_disabled():
        event = EventFactory()
        stype = SubmissionTypeFactory(event=event)
        matching = SubmissionFactory(event=event, submission_type=stype)
        SubmissionFactory(event=event)

        form = QuestionFilterForm(
            data={"role": "", "submission_type": stype.pk}, event=event
        )
        assert form.is_valid(), form.errors
        talks = form.get_submissions()

    assert list(talks) == [matching]


@pytest.mark.django_db
def test_question_filter_form_get_question_information_text_variant():
    """Text-variant answers are grouped by answer value."""
    with scopes_disabled():
        event = EventFactory()
        question = QuestionFactory(event=event, target="submission")
        sub = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        sub.speakers.add(speaker)
        AnswerFactory(question=question, submission=sub, answer="yes")

        form = QuestionFilterForm(data={"role": "", "submission_type": ""}, event=event)
        assert form.is_valid(), form.errors
        info = form.get_question_information(question)

    assert info["answer_count"] == 1
    grouped = list(info["grouped_answers"])
    assert len(grouped) == 1
    assert grouped[0]["answer"] == "yes"
    assert grouped[0]["count"] == 1


@pytest.mark.django_db
def test_question_filter_form_get_question_information_grouped_choices():
    """Choice question answers are grouped by option."""
    with scopes_disabled():
        event = EventFactory()
        question = QuestionFactory(
            event=event, target="submission", variant=QuestionVariant.CHOICES
        )
        opt = AnswerOptionFactory(question=question, answer="Option A")
        sub = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        sub.speakers.add(speaker)
        answer = AnswerFactory(question=question, submission=sub, answer="Option A")
        answer.options.add(opt)

        form = QuestionFilterForm(data={"role": "", "submission_type": ""}, event=event)
        assert form.is_valid(), form.errors
        info = form.get_question_information(question)

    assert info["answer_count"] == 1
    grouped = list(info["grouped_answers"])
    assert len(grouped) == 1
    assert grouped[0]["count"] == 1


@pytest.mark.django_db
def test_question_filter_form_get_question_information_file_variant():
    """File questions return individual answers without grouping."""
    with scopes_disabled():
        event = EventFactory()
        question = QuestionFactory(
            event=event, target="submission", variant=QuestionVariant.FILE
        )
        sub = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        sub.speakers.add(speaker)
        AnswerFactory(question=question, submission=sub, answer="file://test.pdf")

        form = QuestionFilterForm(data={"role": "", "submission_type": ""}, event=event)
        assert form.is_valid(), form.errors
        info = form.get_question_information(question)

    assert info["answer_count"] == 1
    grouped = list(info["grouped_answers"])
    assert len(grouped) == 1
    assert grouped[0]["count"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field_key", "expect_length_fields"),
    (
        ("title", True),
        ("abstract", True),
        ("description", True),
        ("biography", True),
        ("notes", False),
        ("image", False),
    ),
    ids=["title", "abstract", "description", "biography", "notes", "image"],
)
def test_cfp_field_config_form_length_fields_presence(field_key, expect_length_fields):
    """min_length/max_length fields are only present for text-like fields."""
    with scopes_disabled():
        event = EventFactory()

        form = CfPFieldConfigForm(field_key=field_key, event=event)

    assert ("min_length" in form.fields) is expect_length_fields
    assert ("max_length" in form.fields) is expect_length_fields


@pytest.mark.django_db
def test_cfp_field_config_form_max_speakers_only_for_additional_speaker():
    with scopes_disabled():
        event = EventFactory()

        form_speaker = CfPFieldConfigForm(field_key="additional_speaker", event=event)
        form_other = CfPFieldConfigForm(field_key="title", event=event)

    assert "max" in form_speaker.fields
    assert "max" not in form_other.fields


@pytest.mark.django_db
def test_cfp_field_config_form_tag_fields_only_for_tags():
    with scopes_disabled():
        event = EventFactory()

        form_tags = CfPFieldConfigForm(field_key="tags", event=event)
        form_other = CfPFieldConfigForm(field_key="title", event=event)

    assert "min_number" in form_tags.fields
    assert "max_number" in form_tags.fields
    assert "min_number" not in form_other.fields
    assert "max_number" not in form_other.fields


@pytest.mark.django_db
def test_cfp_field_config_form_tags_help_text_mentions_public_tags():
    """The help_text for the tags field mentions public tags."""
    with scopes_disabled():
        event = EventFactory()

        form = CfPFieldConfigForm(field_key="tags", event=event)

    assert "public tags" in str(form.fields["help_text"].help_text).lower()


@pytest.mark.django_db
def test_cfp_field_config_form_clean_rejects_min_greater_than_max():
    with scopes_disabled():
        event = EventFactory()

        form = CfPFieldConfigForm(
            data={"visibility": "optional", "min_number": 5, "max_number": 2},
            field_key="tags",
            event=event,
        )
        valid = form.is_valid()

    assert not valid


@pytest.mark.django_db
def test_cfp_field_config_form_clean_accepts_valid_tag_range():
    with scopes_disabled():
        event = EventFactory()

        form = CfPFieldConfigForm(
            data={"visibility": "optional", "min_number": 1, "max_number": 5},
            field_key="tags",
            event=event,
        )
        valid = form.is_valid()

    assert valid, form.errors


@pytest.mark.django_db
def test_step_header_form_valid_with_empty_data():
    """An empty step header form is valid (fields are optional)."""
    with scopes_disabled():
        event = EventFactory()

        form = StepHeaderForm(data={}, event=event)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_step_header_form_sets_text_rows():
    with scopes_disabled():
        event = EventFactory()

        form = StepHeaderForm(event=event)

    assert form.fields["text"].widget.attrs["rows"] == "3"


@pytest.mark.django_db
def test_reminder_filter_form_questions_queryset_excludes_frozen():
    """Questions with freeze_after in the past are excluded from the queryset."""
    with scopes_disabled():
        event = EventFactory()
        active_q = QuestionFactory(event=event, target="submission", freeze_after=None)
        QuestionFactory(
            event=event, target="submission", freeze_after=now() - dt.timedelta(days=1)
        )

        form = ReminderFilterForm(event=event)

    qs = form.fields["questions"].queryset
    assert active_q in qs
    assert qs.count() == 1


@pytest.mark.django_db
def test_reminder_filter_form_inherits_track_filtering():
    """ReminderFilterForm inherits QuestionFilterForm's track field handling."""
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = False
        event.save()

        form = ReminderFilterForm(event=event)

    assert "track" not in form.fields


@pytest.mark.django_db
def test_reminder_filter_form_includes_speaker_and_submission_questions():
    """The questions queryset includes both speaker and submission questions."""
    with scopes_disabled():
        event = EventFactory()
        sub_q = QuestionFactory(event=event, target="submission")
        spk_q = QuestionFactory(event=event, target="speaker")
        QuestionFactory(event=event, target="reviewer")

        form = ReminderFilterForm(event=event)

    qs = form.fields["questions"].queryset
    assert sub_q in qs
    assert spk_q in qs
    assert qs.count() == 2
