# SPDX-FileCopyrightText: 2023-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.functional import cached_property
from i18nfield.fields import I18nCharField, I18nTextField
from i18nfield.rest_framework import I18nField
from rest_flex_fields.utils import split_levels
from rest_framework.fields import HiddenField, empty
from rest_framework.serializers import (
    ModelSerializer,
    ValidationError,
    as_serializer_error,
)

from pretalx.api.documentation import extend_schema_field


@extend_schema_field(
    field={
        "type": "object",
        "additionalProperties": {"type": "string"},
        "example": {"en": "English text", "de": "Deutscher Text"},
    },
    component_name="Multi-language string",
)
class DocumentedI18nField(I18nField):
    def to_representation(self, value):
        context = getattr(self.parent, "context", None) or {}
        if context.get("override_locale"):
            return str(value)
        return super().to_representation(value)


class PretalxSerializer(ModelSerializer):
    """
    This serializer class will behave like the i18nfield serializer,
    outputting a dict/object for internationalized strings, unless if
    when it was initialized with an ``override_locale`` (taken from
    a URL queryparam, usually), in which case the string will be cast
    to the locale in question – relying on either a view or a middleware
    to apply the locale manager.
    """

    def __init__(self, *args, **kwargs):
        self.override_locale = kwargs.get("context", {}).get("override_locale")
        self.event = getattr(kwargs.get("context", {}).get("request"), "event", None)
        super().__init__(*args, **kwargs)

    def get_unique_together_validators(self):
        # DRF makes every unique-together field required, which breaks pairs of a
        # context-default HiddenField with a model-filled optional (e.g. identifier).
        def is_blocked_by_hidden_default(validator):
            fields = [
                self.fields[name] for name in validator.fields if name in self.fields
            ]
            has_hidden = any(isinstance(f, HiddenField) for f in fields)
            has_optional = any(
                not isinstance(f, HiddenField) and not f.required for f in fields
            )
            return has_hidden and has_optional

        return [
            v
            for v in super().get_unique_together_validators()
            if not is_blocked_by_hidden_default(v)
        ]

    def run_validation(self, data=empty):
        # DRF skips Model.full_clean by default; run it so model-level validators fire.
        value = super().run_validation(data)
        self._run_model_full_clean(value)
        return value

    def _run_model_full_clean(self, attrs):
        model = self.Meta.model
        # Don't mutate self.instance: callers may render it on a partial-error path,
        # and an unsaved-but-dirty instance leaks unvalidated data.
        instance = copy.copy(self.instance) if self.instance is not None else model()
        concrete = {f.name for f in model._meta.concrete_fields}

        # attrs is keyed by field.source; resolve back to concrete field names,
        # falling back to field_name when source points at a method/property
        # (e.g. duration = IntegerField(source="get_duration")).
        applied = {}
        for name, field in self.fields.items():
            if field.source not in attrs:
                continue
            if field.source in concrete:
                applied[field.source] = attrs[field.source]
            elif name in concrete:
                applied[name] = attrs[field.source]
        for name, value in applied.items():
            setattr(instance, name, value)

        # validate_unique=False: defer to DRF's UniqueValidator + DB to avoid duplicate errors.
        try:
            instance.full_clean(
                exclude=concrete - applied.keys(), validate_unique=False
            )
        except DjangoValidationError as exc:
            raise ValidationError(as_serializer_error(exc)) from exc

    def get_with_fallback(self, data, key):
        """
        Get key from dictionary, or fall back to `self.instance` if it exists.
        Handy for validating data in partial updates.
        (Yes, not terribly safe, but better than nothing.)
        """
        if key in data:
            return data[key]
        if self.instance:
            return getattr(self.instance, key, None)

    @cached_property
    def extra_flex_field_config(self):
        return {
            key: split_levels(self._flex_options_all[key])
            for key in ("expand", "fields", "omit")
        }

    def get_extra_flex_field(self, extra_field, *args, **kwargs):
        if extra_field in self.extra_flex_field_config["expand"][0]:
            klass, settings = self.Meta.extra_expandable_fields[extra_field]
            serializer_class = self._get_serializer_class_from_lazy_string(klass)
            settings["context"] = self.context
            settings["parent"] = self
            for key, value in self.extra_flex_field_config.items():
                if value[1] and extra_field in value[1]:
                    settings[key] = value[1][extra_field]
            return serializer_class(*args, **settings, **kwargs)


PretalxSerializer.serializer_field_mapping[I18nCharField] = DocumentedI18nField
PretalxSerializer.serializer_field_mapping[I18nTextField] = DocumentedI18nField
