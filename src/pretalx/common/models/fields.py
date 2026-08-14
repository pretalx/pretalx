# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.contrib.contenttypes.fields import GenericForeignKey
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


class StaleTolerantGenericForeignKey(GenericForeignKey):
    def _model_is_gone(self, instance):
        ct_attname = self.model._meta.get_field(self.ct_field).attname
        ct_id = getattr(instance, ct_attname, None)
        if ct_id is None:
            return False
        content_type = self.get_content_type(id=ct_id, using=instance._state.db)
        return content_type.model_class() is None

    def __get__(self, instance, cls=None):
        if instance is not None and self._model_is_gone(instance):
            self.set_cached_value(instance, None)
            return None
        return super().__get__(instance, cls)

    def get_prefetch_querysets(self, instances, querysets=None):
        return super().get_prefetch_querysets(
            [instance for instance in instances if not self._model_is_gone(instance)],
            querysets,
        )
