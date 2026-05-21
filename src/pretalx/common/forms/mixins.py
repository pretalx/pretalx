# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging

from django import forms
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from hierarkey.forms import HierarkeyForm
from i18nfield.forms import I18nFormField, I18nFormMixin, I18nModelForm, I18nTextarea

from pretalx.common.forms.widgets import I18nMarkdownTextarea

logger = logging.getLogger(__name__)


class ReadOnlyFlag:
    def __init__(self, *args, read_only=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_only = read_only
        if read_only:
            for field in self.fields.values():
                field.disabled = True

    def clean(self):
        if self.read_only:
            raise forms.ValidationError(_("You are trying to change read-only data."))
        return super().clean()


class JsonSubfieldMixin:
    def __init__(self, *args, **kwargs):
        obj = kwargs.pop("obj", None)
        super().__init__(*args, **kwargs)
        if not getattr(self, "instance", None):
            if obj:
                self.instance = obj
            elif getattr(self, "obj", None):
                self.instance = self.obj
        for field, path in self.Meta.json_fields.items():
            data_dict = getattr(self.instance, path) or {}
            if field in data_dict:
                self.fields[field].initial = data_dict.get(field)
            else:
                defaults = self.instance._meta.get_field(path).default()
                self.fields[field].initial = defaults.get(field)

    def _apply_json_subfields(self):
        touched_paths = set()
        for field, path in self.Meta.json_fields.items():
            if field not in self.cleaned_data:
                continue
            data_dict = getattr(self.instance, path, None) or {}
            data_dict[field] = self.cleaned_data.get(field)
            setattr(self.instance, path, data_dict)
            touched_paths.add(path)
        return touched_paths

    def _post_clean(self):
        touched_paths = self._apply_json_subfields()
        super()._post_clean()
        for path in touched_paths:
            try:
                model_field = self.instance._meta.get_field(path)
            except FieldDoesNotExist:  # pragma: no cover -- defensive
                continue
            try:
                model_field.run_validators(getattr(self.instance, path))
            except ValidationError as exc:
                self.add_error(None, exc)

    def save(self, *args, **kwargs):
        if getattr(super(), "save", None):
            instance = super().save(*args, **kwargs)
        else:
            instance = self.instance
        # ``_post_clean`` already wrote the cleaned sub-field values onto
        # the instance, but we apply them again so callers that mutate
        # ``cleaned_data`` between validation and save still see their
        # changes persisted.
        self._apply_json_subfields()
        if kwargs.get("commit", True):
            instance.save()
        return instance


class HierarkeyMixin:
    """This basically vendors hierarkey.forms.HierarkeyForm, but with more
    selective saving of fields.
    """

    BOOL_CHOICES = HierarkeyForm.BOOL_CHOICES

    def __init__(self, *args, obj, attribute_name="settings", **kwargs):
        self.obj = obj
        self.attribute_name = attribute_name
        self._s = getattr(obj, attribute_name)
        base_initial = self._s.freeze()
        base_initial.update(**kwargs["initial"])
        kwargs["initial"] = base_initial
        super().__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        """Saves all changed values to the database."""
        super().save(*args, **kwargs)
        for name in self.Meta.hierarkey_fields:
            field = self.fields.get(name)
            value = self.cleaned_data[name]
            if isinstance(value, UploadedFile):
                # Delete old file
                fname = self._s.get(name, as_type=File)
                if fname:
                    try:
                        default_storage.delete(fname.name)
                    except OSError:
                        logger.exception("Deleting file %s failed.", fname.name)

                # Create new file
                newname = default_storage.save(self.get_new_filename(value.name), value)
                value._name = newname  # noqa: SLF001 -- Django File internal
                self._s.set(name, value)
            elif isinstance(value, File):
                # file is unchanged
                continue
            elif not value and isinstance(field, forms.FileField):
                # file is deleted
                fname = self._s.get(name, as_type=File)
                if fname:
                    try:
                        default_storage.delete(fname.name)
                    except OSError:
                        logger.exception("Deleting file %s failed.", fname.name)
                del self._s[name]
            elif value is None:
                del self._s[name]
            elif self._s.get(name, as_type=type(value)) != value:
                self._s.set(name, value)

    def get_new_filename(self, name: str) -> str:
        nonce = get_random_string(length=8)
        suffix = name.rsplit(".", maxsplit=1)[-1]
        return f"{self.obj._meta.model_name}-{self.attribute_name}/{self.obj.pk}/{name}.{nonce}.{suffix}"


class PretalxI18nFormMixin(I18nFormMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field, I18nFormField):
                if type(field.widget) is I18nTextarea:
                    old = field.widget
                    field.widget = I18nMarkdownTextarea(
                        locales=old.locales, field=old.field, attrs=dict(old.attrs)
                    )
                    field.widget.enabled_locales = old.enabled_locales
                if not field.widget.attrs.get("placeholder"):
                    field.widget.attrs["placeholder"] = field.label

    class Media:
        css = {"all": ["orga/css/forms/i18n.css"]}


class PretalxI18nModelForm(PretalxI18nFormMixin, I18nModelForm):
    pass
