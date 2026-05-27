# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms

from pretalx.common.forms.fields import SizeFileField
from pretalx.common.forms.renderers import InlineFormLabelRenderer
from pretalx.submission.models import Resource


class ResourceForm(forms.ModelForm):
    default_renderer = InlineFormLabelRenderer

    def _post_clean(self):
        # Skip model validation when the row is being deleted: the user's
        # intent is removal, not correctness of the (possibly cleared) fields.
        if self.cleaned_data.get("DELETE"):
            return
        super()._post_clean()

    class Meta:
        model = Resource
        fields = ["resource", "description", "link", "is_public"]
        field_classes = {"resource": SizeFileField}
