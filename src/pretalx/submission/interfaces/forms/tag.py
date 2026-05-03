# SPDX-FileCopyrightText: 2020-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.common.forms.fields import ColorField
from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.submission.models import Tag


class TagForm(ReadOnlyFlag, PretalxI18nModelForm):
    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.event = event

    class Meta:
        model = Tag
        fields = ("tag", "description", "color", "is_public")
        field_classes = {"color": ColorField}
