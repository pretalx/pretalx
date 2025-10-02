from django.db import models

from pretalx.common.forms.widgets import MarkdownWidget


class MarkdownField(models.TextField):
    def formfield(self, **kwargs):
        return super().formfield(widget=MarkdownWidget)
