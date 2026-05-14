# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from io import BytesIO
from unittest.mock import patch

import pytest
from django import forms
from django.core.files.base import File
from django.core.files.uploadedfile import SimpleUploadedFile
from i18nfield.forms import I18nFormField, I18nFormMixin, I18nTextarea, I18nTextInput

from pretalx.common.forms.mixins import (
    HierarkeyMixin,
    JsonSubfieldMixin,
    PretalxI18nFormMixin,
    ReadOnlyFlag,
)
from tests.factories import EventFactory

pytestmark = pytest.mark.unit


class ReadOnlyTestForm(ReadOnlyFlag, forms.Form):
    name = forms.CharField()
    email = forms.EmailField()


class JsonSubfieldTestForm(JsonSubfieldMixin, forms.Form):
    show_schedule = forms.BooleanField(required=False)
    use_feedback = forms.BooleanField(required=False)

    class Meta:
        json_fields = {
            "show_schedule": "feature_flags",
            "use_feedback": "feature_flags",
        }


class _SaveStub(forms.Form):
    """Provides a no-op save() so HierarkeyMixin.save can call super().save()."""

    def save(self, *args, **kwargs):
        pass


class HierarkeyTestForm(HierarkeyMixin, _SaveStub):
    test_setting = forms.CharField(required=False)
    test_file = forms.FileField(required=False)

    class Meta:
        hierarkey_fields = ("test_setting", "test_file")


class I18nTestForm(PretalxI18nFormMixin, forms.Form):
    name = I18nFormField(widget=I18nTextarea, required=False)


@pytest.mark.parametrize(
    ("read_only", "expected_disabled"),
    ((True, True), (False, False)),
    ids=("read_only", "editable"),
)
def test_read_only_flag_field_disabled(read_only, expected_disabled):
    form = ReadOnlyTestForm(read_only=read_only)

    assert form.read_only is read_only
    assert form.fields["name"].disabled is expected_disabled
    assert form.fields["email"].disabled is expected_disabled


@pytest.mark.parametrize(
    ("read_only", "expected_valid"),
    ((True, False), (False, True)),
    ids=("read_only_rejects", "editable_accepts"),
)
def test_read_only_flag_clean(read_only, expected_valid):
    form = ReadOnlyTestForm(data={"name": "x", "email": "x@x.com"}, read_only=read_only)

    assert form.is_valid() is expected_valid


@pytest.mark.django_db
def test_json_subfield_mixin_init_reads_existing_values():
    event = EventFactory()

    form = JsonSubfieldTestForm(obj=event)

    for field in ("show_schedule", "use_feedback"):
        assert form.fields[field].initial is event.feature_flags.get(field)


@pytest.mark.django_db
def test_json_subfield_mixin_init_uses_defaults_for_missing_fields():
    event = EventFactory()
    # Remove the key to simulate a newly-added form field
    event.feature_flags.pop("show_schedule", None)
    event.save()

    form = JsonSubfieldTestForm(obj=event)

    # Should use the default from Event._meta.get_field("feature_flags").default()
    defaults = event._meta.get_field("feature_flags").default()
    assert form.fields["show_schedule"].initial == defaults.get("show_schedule")


@pytest.mark.django_db
def test_json_subfield_mixin_save_writes_values():
    event = EventFactory()
    form = JsonSubfieldTestForm(
        data={"show_schedule": True, "use_feedback": True}, obj=event
    )
    assert form.is_valid()

    form.instance = event
    form.save()

    event.refresh_from_db()
    assert event.feature_flags["show_schedule"] is True
    assert event.feature_flags["use_feedback"] is True


@pytest.mark.django_db
def test_json_subfield_mixin_save_commit_false():
    event = EventFactory()
    original_flags = dict(event.feature_flags)
    form = JsonSubfieldTestForm(
        data={"show_schedule": True, "use_feedback": True}, obj=event
    )
    assert form.is_valid()

    form.instance = event
    result = form.save(commit=False)

    # Instance attributes updated in memory
    assert result.feature_flags["show_schedule"] is True
    # But database still has original values
    event.refresh_from_db()
    assert event.feature_flags.get("show_schedule") == original_flags.get(
        "show_schedule"
    )


@pytest.mark.django_db
def test_json_subfield_mixin_init_with_obj_kwarg():
    event = EventFactory()
    form = JsonSubfieldTestForm(obj=event)

    assert form.instance is event


@pytest.mark.django_db
def test_json_subfield_mixin_init_with_existing_instance():
    event = EventFactory()

    class PreSetInstanceForm(JsonSubfieldMixin, forms.Form):
        show_schedule = forms.BooleanField(required=False)

        class Meta:
            json_fields = {"show_schedule": "feature_flags"}

        def __init__(self, *args, **kwargs):
            self.instance = kwargs.pop("instance")
            super().__init__(*args, **kwargs)

    form = PreSetInstanceForm(instance=event)

    assert form.instance is event


@pytest.mark.django_db
def test_json_subfield_mixin_init_with_self_obj_fallback():
    event = EventFactory()

    class ObjForm(JsonSubfieldMixin, forms.Form):
        show_schedule = forms.BooleanField(required=False)

        class Meta:
            json_fields = {"show_schedule": "feature_flags"}

        def __init__(self, *args, **kwargs):
            self.obj = kwargs.pop("obj_attr")
            super().__init__(*args, **kwargs)

    form = ObjForm(obj_attr=event)

    assert form.instance is event


@pytest.mark.django_db
def test_json_subfield_mixin_init_without_obj_or_instance_raises():
    """When neither obj kwarg, self.obj, nor instance is provided, accessing
    self.instance in the field initialization raises AttributeError."""
    EventFactory()

    class BareForm(JsonSubfieldMixin, forms.Form):
        show_schedule = forms.BooleanField(required=False)

        class Meta:
            json_fields = {"show_schedule": "feature_flags"}

    with pytest.raises(AttributeError):
        BareForm()


@pytest.mark.django_db
def test_json_subfield_mixin_save_delegates_to_super():

    class BaseSave(forms.Form):
        """Simulates a ModelForm-like base with a save() method."""

        save_called = False

        def save(self, *args, **kwargs):
            self.save_called = True
            return self.instance

    class FormWithSave(JsonSubfieldMixin, BaseSave):
        test_field = forms.BooleanField(required=False)

        class Meta:
            json_fields = {"test_field": "feature_flags"}

    event = EventFactory()
    form = FormWithSave(data={"test_field": True}, obj=event)
    assert form.is_valid()

    result = form.save()

    assert form.save_called is True
    assert result.feature_flags["test_field"] is True


@pytest.mark.django_db
def test_hierarkey_mixin_init_loads_settings():
    event = EventFactory()
    event.settings.set("test_setting", "hello")

    form = HierarkeyTestForm(obj=event, attribute_name="settings", initial={})

    assert form.initial.get("test_setting") == "hello"


@pytest.mark.django_db
def test_hierarkey_mixin_save_changed_value():
    event = EventFactory()
    event.settings.set("test_setting", "old_value")

    form = HierarkeyTestForm(
        data={"test_setting": "new_value"},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    assert form.is_valid()

    HierarkeyMixin.save(form)

    assert event.settings.get("test_setting") == "new_value"


@pytest.mark.django_db
def test_hierarkey_mixin_save_unchanged_value():
    event = EventFactory()
    event.settings.set("test_setting", "same")

    form = HierarkeyTestForm(
        data={"test_setting": "same"}, obj=event, attribute_name="settings", initial={}
    )
    assert form.is_valid()

    HierarkeyMixin.save(form)

    assert event.settings.get("test_setting") == "same"


@pytest.mark.django_db
def test_hierarkey_mixin_save_none_value_deletes():
    event = EventFactory()
    event.settings.set("test_setting", "will_be_deleted")

    form = HierarkeyTestForm(data={}, obj=event, attribute_name="settings", initial={})
    form.cleaned_data = {"test_setting": None, "test_file": None}

    HierarkeyMixin.save(form)

    assert event.settings.get("test_setting") is None


@pytest.mark.django_db
def test_hierarkey_mixin_save_uploaded_file():
    event = EventFactory()
    upload = SimpleUploadedFile("logo.png", b"png data", content_type="image/png")

    form = HierarkeyTestForm(
        data={},
        files={"test_file": upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form.cleaned_data = {"test_setting": None, "test_file": upload}

    HierarkeyMixin.save(form)

    stored = event.settings.get("test_file", as_type=File)
    assert f"event-settings/{event.pk}/" in stored.name
    assert "logo.png" in stored.name


@pytest.mark.django_db
def test_hierarkey_mixin_save_uploaded_file_deletes_old():
    event = EventFactory()

    # First, upload a file through the full save path so it exists in storage
    old_upload = SimpleUploadedFile("old.png", b"old data", content_type="image/png")
    form1 = HierarkeyTestForm(
        data={},
        files={"test_file": old_upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form1.cleaned_data = {"test_setting": None, "test_file": old_upload}
    HierarkeyMixin.save(form1)

    # Now upload a replacement file
    new_upload = SimpleUploadedFile("new.png", b"new data", content_type="image/png")
    form2 = HierarkeyTestForm(
        data={},
        files={"test_file": new_upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form2.cleaned_data = {"test_setting": None, "test_file": new_upload}
    HierarkeyMixin.save(form2)

    stored = event.settings.get("test_file", as_type=File)
    assert f"event-settings/{event.pk}/" in stored.name
    assert "new.png" in stored.name


@pytest.mark.django_db
def test_hierarkey_mixin_save_file_unchanged():
    event = EventFactory()
    event.settings.set("test_setting", "keep_this")
    plain_file = File(BytesIO(b"content"), name="existing.txt")

    form = HierarkeyTestForm(
        data={"test_setting": "keep_this"},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form.cleaned_data = {"test_setting": "keep_this", "test_file": plain_file}

    HierarkeyMixin.save(form)

    assert event.settings.get("test_setting") == "keep_this"


@pytest.mark.django_db
def test_hierarkey_mixin_save_empty_file_field_deletes():
    event = EventFactory()

    # First upload a file through the save path so it exists in storage
    upload = SimpleUploadedFile("logo.png", b"data", content_type="image/png")
    form1 = HierarkeyTestForm(
        data={},
        files={"test_file": upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form1.cleaned_data = {"test_setting": None, "test_file": upload}
    HierarkeyMixin.save(form1)
    assert "logo.png" in event.settings.get("test_file", as_type=File).name

    # Now submit with empty file value to trigger deletion
    form2 = HierarkeyTestForm(
        data={"test_setting": ""}, obj=event, attribute_name="settings", initial={}
    )
    form2.cleaned_data = {"test_setting": "", "test_file": None}

    HierarkeyMixin.save(form2)

    assert event.settings.get("test_file") is None


@pytest.mark.django_db
def test_hierarkey_mixin_save_uploaded_file_delete_old_oserror():
    """When deleting the old file fails with OSError, the new upload still proceeds."""
    event = EventFactory()

    # Upload initial file
    old_upload = SimpleUploadedFile("old.png", b"old", content_type="image/png")
    form1 = HierarkeyTestForm(
        data={},
        files={"test_file": old_upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form1.cleaned_data = {"test_setting": None, "test_file": old_upload}
    HierarkeyMixin.save(form1)

    # Replace with new file, but mock delete to raise OSError
    new_upload = SimpleUploadedFile("new.png", b"new", content_type="image/png")
    form2 = HierarkeyTestForm(
        data={},
        files={"test_file": new_upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form2.cleaned_data = {"test_setting": None, "test_file": new_upload}

    with patch("pretalx.common.forms.mixins.default_storage") as mock_storage:
        mock_storage.delete.side_effect = OSError("disk error")
        mock_storage.save.return_value = "event-settings/new.png"
        HierarkeyMixin.save(form2)

    assert event.settings.get("test_file") is not None


@pytest.mark.django_db
def test_hierarkey_mixin_save_clear_file_delete_oserror():
    """When deleting a cleared file fails with OSError, the setting is still removed."""
    event = EventFactory()

    # Upload initial file
    upload = SimpleUploadedFile("logo.png", b"data", content_type="image/png")
    form1 = HierarkeyTestForm(
        data={},
        files={"test_file": upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form1.cleaned_data = {"test_setting": None, "test_file": upload}
    HierarkeyMixin.save(form1)

    # Clear the file, but mock delete to raise OSError
    form2 = HierarkeyTestForm(
        data={"test_setting": ""}, obj=event, attribute_name="settings", initial={}
    )
    form2.cleaned_data = {"test_setting": "", "test_file": None}

    with patch("pretalx.common.forms.mixins.default_storage") as mock_storage:
        mock_storage.delete.side_effect = OSError("disk error")
        HierarkeyMixin.save(form2)

    assert event.settings.get("test_file") is None


@pytest.mark.django_db
def test_hierarkey_mixin_get_new_filename():
    event = EventFactory()
    form = HierarkeyTestForm(obj=event, attribute_name="settings", initial={})

    filename = form.get_new_filename("logo.png")

    assert f"event-settings/{event.pk}/" in filename
    assert filename.endswith(".png")
    assert "logo.png." in filename


def test_pretalx_i18n_form_mixin_preserves_existing_placeholder():

    class _InjectPlaceholder(I18nFormMixin):
        """Sets placeholder after I18nFormMixin sets up widgets but before
        PretalxI18nFormMixin checks for placeholders."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            for field in self.fields.values():
                if isinstance(field, I18nFormField):
                    field.widget.attrs["placeholder"] = "Pre-existing"

    class I18nWithPlaceholder(PretalxI18nFormMixin, _InjectPlaceholder, forms.Form):
        name = I18nFormField(widget=I18nTextarea, required=False)
        extra = forms.CharField(required=False)

    form = I18nWithPlaceholder(locales=["en"])

    assert form.fields["name"].widget.attrs["placeholder"] == "Pre-existing"


def test_pretalx_i18n_form_mixin_skips_non_i18n_fields():

    class MixedForm(PretalxI18nFormMixin, forms.Form):
        plain = forms.CharField(required=False)
        i18n_name = I18nFormField(widget=I18nTextarea, required=False)

    form = MixedForm(locales=["en"])

    assert isinstance(form.fields["plain"], forms.CharField)
    assert "placeholder" not in form.fields["plain"].widget.attrs


def test_pretalx_i18n_form_mixin_non_textarea_i18n_widget():

    class I18nTextInputForm(PretalxI18nFormMixin, forms.Form):
        name = I18nFormField(widget=I18nTextInput, required=False)

    form = I18nTextInputForm(locales=["en"])

    assert isinstance(form.fields["name"].widget, I18nTextInput)
