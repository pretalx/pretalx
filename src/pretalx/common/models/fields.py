from django.db import models

from pretalx.common.forms.widgets import (
    HtmlDateInput,
    HtmlDateTimeInput,
    MarkdownWidget,
)


class MarkdownField(models.TextField):
    def formfield(self, **kwargs):
        return super().formfield(widget=MarkdownWidget)


class DateTimeField(models.DateTimeField):
    def formfield(self, **kwargs):
        return super().formfield(widget=HtmlDateTimeInput)


class DateField(models.DateField):
    def formfield(self, **kwargs):
        return super().formfield(widget=HtmlDateInput)
