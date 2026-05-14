# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import models


class MarkdownField(models.TextField):
    def formfield(self, **kwargs):
        from pretalx.common.forms.widgets import (  # noqa: PLC0415 -- thin method
            MarkdownWidget,
        )

        return super().formfield(widget=MarkdownWidget)


class DateTimeField(models.DateTimeField):
    def formfield(self, **kwargs):
        from pretalx.common.forms.widgets import (  # noqa: PLC0415 -- thin method
            HtmlDateTimeInput,
        )

        return super().formfield(widget=HtmlDateTimeInput)


class DateField(models.DateField):
    def formfield(self, **kwargs):
        from pretalx.common.forms.widgets import (  # noqa: PLC0415 -- thin method
            HtmlDateInput,
        )

        return super().formfield(widget=HtmlDateInput)
