# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import i18nfield.forms
from django import forms

from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.common.forms.widgets import SearchInput
from pretalx.common.text.phrases import phrases


class SearchForm(forms.Form):
    default_renderer = InlineFormRenderer

    q = forms.CharField(label=phrases.base.search, required=False, widget=SearchInput)


class I18nFormSet(i18nfield.forms.I18nModelFormSet):
    """Compatibility shim for django-i18nfield."""

    def __init__(self, *args, **kwargs):
        event = kwargs.pop("event", None)
        kwargs["locales"] = getattr(event, "locales", [])
        super().__init__(*args, **kwargs)


class I18nEventFormSet(i18nfield.forms.I18nModelFormSet):
    """Compatibility shim for django-i18nfield."""

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop("event", None)
        kwargs["locales"] = getattr(self.event, "locales", [])
        super().__init__(*args, **kwargs)

    def _construct_form(self, *args, **kwargs):
        kwargs["locales"] = self.locales
        kwargs["event"] = self.event
        return super()._construct_form(*args, **kwargs)


def save_related_formset(formset, *, parent, fk_field):
    for form in formset.initial_forms:
        if form in formset.deleted_forms:
            if form.instance.pk:
                form.instance.delete()
                form.instance.pk = None
        elif form.has_changed():
            setattr(form.instance, fk_field, parent)
            form.save()
    for form in formset.extra_forms:
        if not form.has_changed():
            continue
        if formset._should_delete_form(form):  # noqa: SLF001 -- Django formset internal
            continue
        setattr(form.instance, fk_field, parent)
        form.save()
