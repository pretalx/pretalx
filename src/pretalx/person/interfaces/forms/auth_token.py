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
    PRESET_PERMISSIONS = {"read": READ_PERMISSIONS, "write": WRITE_PERMISSIONS}

    permission_preset = forms.ChoiceField(
        label=_("Permissions"),
        required=False,
        choices=(
            ("read", _("Read all endpoints")),
            ("write", _("Read and write all endpoints")),
            ("custom", _("Customise permissions and endpoints")),
        ),
        help_text=_("Choose a preset or configure detailed permissions below."),
        widget=EnhancedSelect,
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.instance.user = user
        self.fields["events"].queryset = user.get_events_with_any_permission()
        self.fields["events"].help_text = mark_safe(  # noqa: S308  -- static HTML with translated string
            '<span class="select-all-events font-text p-0 text-underline fake-link" role="button" tabindex="0">'
            + str(_("Select all events"))
            + "</span>"
        )

        self.endpoint_field_names = []
        for endpoint in ENDPOINTS:
            name = f"endpoint_{endpoint}"
            self.endpoint_field_names.append(name)
            self.fields[name] = forms.MultipleChoiceField(
                label=f"/{endpoint}",
                required=False,
                choices=PERMISSION_CHOICES,
                widget=forms.CheckboxSelectMultiple,
                initial=READ_PERMISSIONS,
            )

    def get_endpoint_fields(self):
        """Used in templates, so has to return the actual bound fields."""
        return [(name, self[name]) for name in self.endpoint_field_names]

    def clean(self):
        data = super().clean()
        if perms := self.PRESET_PERMISSIONS.get(data.get("permission_preset")):
            endpoints = {ep: list(perms) for ep in ENDPOINTS}
        else:
            endpoints = {
                ep: list(self.cleaned_data.get(f"endpoint_{ep}", []))
                for ep in ENDPOINTS
            }
        self.instance.endpoints = endpoints
        return data

    class Media:
        js = [forms.Script("common/js/forms/token.js", defer="")]

    class Meta:
        model = UserApiToken
        fields = ["name", "events", "expires", "permission_preset"]
        widgets = {"events": EnhancedSelectMultiple}
