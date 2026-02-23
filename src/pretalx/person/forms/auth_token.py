# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.widgets import EnhancedSelect, EnhancedSelectMultiple
from pretalx.person.models.auth_token import (
    ENDPOINTS,
    PERMISSION_CHOICES,
    READ_PERMISSIONS,
    WRITE_PERMISSIONS,
    UserApiToken,
)


class AuthTokenForm(forms.ModelForm):
    permission_preset = forms.ChoiceField(
        label=_("Permissions"),
        required=False,
        choices=(
            ("read", _("Read all endpoints")),
            ("write", _("Read and write all endpoints")),
            ("custom", _("Customize permissions and endpoints")),
        ),
        help_text=_("Choose a preset or configure detailed permissions below."),
        widget=EnhancedSelect,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["events"].queryset = user.get_events_with_any_permission()
        self.fields["events"].help_text = mark_safe(
            '<span class="select-all-events font-text p-0 text-underline fake-link" role="button" tabindex="0">'
            + str(_("Select all events"))
            + "</span>"
        )

        self.endpoint_fields = {}
        for endpoint in ENDPOINTS:
            self.fields[f"endpoint_{endpoint}"] = forms.MultipleChoiceField(
                label=f"/{endpoint}",
                required=False,
                choices=PERMISSION_CHOICES,
                widget=forms.CheckboxSelectMultiple,
                initial=READ_PERMISSIONS,
            )
            self.endpoint_fields[f"endpoint_{endpoint}"] = self.fields[
                f"endpoint_{endpoint}"
            ]

    def get_endpoint_fields(self):
        """Used in templates, so has to return the actual fields."""
        return [(field_name, self[field_name]) for field_name in self.endpoint_fields]

    def save(self, *args, **kwargs):
        self.instance.user = self.user
        self.instance.endpoints = self.cleaned_data["endpoints"]
        return super().save(*args, **kwargs)

    class Media:
        js = [forms.Script("common/js/forms/token.js", defer="")]

    class Meta:
        model = UserApiToken
        fields = ["name", "events", "expires", "permission_preset"]
        widgets = {"events": EnhancedSelectMultiple}

    def clean(self):
        data = super().clean()
        if data.get("permission_preset") == "read":
            data["endpoints"] = dict.fromkeys(ENDPOINTS, READ_PERMISSIONS)
        elif data.get("permission_preset") == "write":
            data["endpoints"] = dict.fromkeys(ENDPOINTS, WRITE_PERMISSIONS)
        else:
            data["endpoints"] = {}
            for field_name in self.endpoint_fields:
                permissions = self.cleaned_data.get(field_name)
                endpoint = field_name.replace("endpoint_", "")
                invalid_perms = set(permissions) - set(WRITE_PERMISSIONS)
                if invalid_perms:
                    self.add_error(
                        field_name,
                        _("Invalid permissions selected: {perms}").format(
                            perms=", ".join(invalid_perms)
                        ),
                    )
                data["endpoints"][endpoint] = list(permissions)
        return data
