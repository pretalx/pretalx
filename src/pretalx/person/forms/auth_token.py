from django import forms
from django.utils.translation import gettext_lazy as _

from pretalx.person.models.auth_token import (
    ENDPOINTS,
    PERMISSION_CHOICES,
    READ_PERMISSIONS,
    WRITE_PERMISSIONS,
    UserApiToken,
)


class AuthTokenForm(forms.ModelForm):
    permission_presets = forms.ChoiceField(
        label=_("Permission preset"),
        required=False,
        choices=(
            ("", _("Custom permissions")),
            ("read", _("Read all")),
            ("write", _("Write all")),
        ),
        help_text=_("Choose a preset or configure detailed permissions below."),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["team"].queryset = user.teams.all()

        # Add dynamic fields for each endpoint
        self.endpoint_fields = {}
        for endpoint in ENDPOINTS:
            self.fields[f"endpoint_{endpoint}"] = forms.MultipleChoiceField(
                label=f"/{endpoint}",
                required=False,
                choices=PERMISSION_CHOICES,
                widget=forms.CheckboxSelectMultiple,
                initial=[],
            )
            self.endpoint_fields[f"endpoint_{endpoint}"] = self.fields[
                f"endpoint_{endpoint}"
            ]

    class Meta:
        model = UserApiToken
        fields = ["name", "team", "expires", "permission_presets"]

    def clean(self):
        data = super().clean()
        if data.get("permission_presets") == "read":
            data["endpoints"] = {endpoint: READ_PERMISSIONS for endpoint in ENDPOINTS}
        elif data.get("permission_presets") == "write":
            data["endpoints"] = {endpoint: WRITE_PERMISSIONS for endpoint in ENDPOINTS}
        else:
            for field_name in self.endpoint_fields.keys():
                permissions = self.cleaned_data.get(field_name)
                endpoint = field_name.replace("endpoint_", "")
                # Validate that all selected permissions are valid
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
