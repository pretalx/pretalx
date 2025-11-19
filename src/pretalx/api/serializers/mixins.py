# SPDX-FileCopyrightText: 2023-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.functional import cached_property
from i18nfield.fields import I18nCharField, I18nTextField
from i18nfield.rest_framework import I18nField
from rest_flex_fields.utils import split_levels
from rest_framework.serializers import ModelSerializer

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
