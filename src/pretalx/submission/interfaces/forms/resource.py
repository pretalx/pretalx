# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms

from pretalx.common.forms.fields import DocumentFileField
from pretalx.common.forms.renderers import InlineFormLabelRenderer
from pretalx.submission.models import Resource


class ResourceForm(forms.ModelForm):
    default_renderer = InlineFormLabelRenderer

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # An existing file resource has to be deleted as resource, not as file
        self.fields["resource"].widget.clearable = False

    def _post_clean(self):
        # Skip model validation when the row is being deleted: the user's
        # intent is removal, not correctness of the (possibly cleared) fields.
        if self.cleaned_data.get("DELETE"):
            return
        if "resource" in self.errors:
            return
        super()._post_clean()

    class Meta:
        model = Resource
        fields = ["resource", "description", "link", "is_public"]
        field_classes = {"resource": DocumentFileField}
