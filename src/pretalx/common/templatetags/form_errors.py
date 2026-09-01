# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from django import template

register = template.Library()


@register.filter
def fields_with_errors(form):
    if not hasattr(form, "visible_fields"):
        return []
    return [field for field in form.visible_fields() if field.errors]


def _flatten(forms):
    for form in forms:
        if form is None:
            continue
        if hasattr(form, "visible_fields"):
            yield form
        else:
            yield from (item for item in form if item is not None)


@register.inclusion_tag("common/forms/errors.html")
def form_errors(*forms, fields=True):
    """Render one error summary covering all given forms.

    Makes sure form errors do not double-render.
    fields=False for non-field-errors only, used inside formset rows.
    """
    forms = [
        form
        for form in _flatten(forms)
        if not getattr(form, "error_summary_rendered", False)
    ]
    for form in forms:
        form.error_summary_rendered = True
    errors = [error for form in forms for error in form.non_field_errors()]
    field_errors = (
        [field for form in forms for field in fields_with_errors(form)]
        if fields
        else []
    )
    generic = (
        fields
        and not errors
        and not field_errors
        and any(form.errors for form in forms)
    )
    return {"errors": errors, "field_errors": field_errors, "generic": generic}
