# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms


class CfPFormMixin:
    """All forms used in the CfP step process should use this mixin.

    It serves to make it work with the CfP Flow editor, e.g. by allowing
    users to change help_text attributes of fields and reorder fields.
    Needs to go first before all other forms changing help_text behaviour.
    """

    def __init__(self, *args, field_configuration=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_configuration = field_configuration
        if self.field_configuration:
            field_order = [field_data["key"] for field_data in self.field_configuration]
            self.field_configuration = {
                field_data["key"]: field_data for field_data in field_configuration
            }
            for field_data in self.field_configuration:
                if field_data in self.fields:
                    self._update_cfp_texts(field_data)
            self._reorder_fields(field_order)

    def _reorder_fields(self, field_order):
        new_fields = {}
        for key in field_order:
            if key in self.fields:
                new_fields[key] = self.fields[key]
        # Add any remaining fields not in the config
        for key, field in self.fields.items():
            if key not in new_fields:
                new_fields[key] = field

        self.fields = new_fields

    def _update_cfp_texts(self, field_name):
        field = self.fields.get(field_name)
        if not field or not self.field_configuration:
            return
        field_data = self.field_configuration.get(field_name) or {}
        field.original_help_text = field_data.get("help_text") or ""
        if field.original_help_text:
            from pretalx.common.templatetags.rich_text import rich_text  # noqa: PLC0415

            field.help_text = rich_text(
                str(field.original_help_text)
                + " "
                + str(getattr(field, "added_help_text", ""))
            )
        if field_data.get("label"):
            field.label = field_data["label"]
