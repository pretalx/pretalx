# SPDX-FileCopyrightText: 2020-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django_scopes.forms import SafeModelMultipleChoiceField

from pretalx.common.forms.fields import ColorField
from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.common.forms.widgets import EnhancedSelectMultiple
from pretalx.submission.models import Submission, Tag


class TagForm(ReadOnlyFlag, PretalxI18nModelForm):
    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.event = event

    class Meta:
        model = Tag
        fields = ("tag", "description", "color", "is_public")
        field_classes = {"color": ColorField}


class TagsForm(ReadOnlyFlag, forms.ModelForm):
    def __init__(self, *, event, **kwargs):
        self.event = event
        super().__init__(**kwargs)
        if not self.event.tags.exists():
            self.fields.pop("tags")
        else:
            self.fields["tags"].queryset = self.event.tags.all()
            self.fields["tags"].required = False

    class Meta:
        model = Submission
        fields = ["tags"]
        widgets = {"tags": EnhancedSelectMultiple(color_field="color")}
        field_classes = {"tags": SafeModelMultipleChoiceField}
