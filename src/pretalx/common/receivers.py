# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.dispatch import receiver

from pretalx.orga.signals import event_copy_data

QUESTION_PREFIX = "question_"


def _remap_values(values, mapping):
    remapped = []
    for value in values:
        try:
            remapped.append(str(mapping[int(value)].pk))
        except (KeyError, TypeError, ValueError):
            continue
    return remapped


def _remap_prefixed(name, prefix, mapping):
    try:
        new_object = mapping[int(name.removeprefix(prefix))]
    except (KeyError, ValueError):
        return None
    return f"{prefix}{new_object.pk}"


def _score_prefix(name):
    for prefix in ("score_", "independent_score_"):
        if name.startswith(prefix):
            return prefix
    return None


def _remap_option_values(values, option_map):
    remapped = []
    for value in values:
        if not value.isdigit():
            remapped.append(value)
        elif int(value) in option_map:
            remapped.append(str(option_map[int(value)].pk))
    return remapped


def _option_map(question_map):
    from pretalx.submission.models import Question  # noqa: PLC0415 -- receiver

    mapping = {}
    for old_pk, new_question in question_map.items():
        old_question = Question.all_objects.filter(pk=old_pk).first()
        if not old_question:
            continue
        new_options = {
            option.identifier: option for option in new_question.options.all()
        }
        mapping[old_pk] = {
            old_option.pk: new_options[old_option.identifier]
            for old_option in old_question.options.all()
            if old_option.identifier in new_options
        }
    return mapping


def _remap_filter(
    param, values, *, track_map, submission_type_map, tag_map, question_map, option_map
):
    values = [str(value) for value in values]
    if param == "track":
        return param, _remap_values(values, track_map)
    if param == "submission_type":
        return param, _remap_values(values, submission_type_map)
    if param == "tags":
        return param, _remap_values(values, tag_map)
    if param.startswith(QUESTION_PREFIX):
        new_param = _remap_prefixed(param, QUESTION_PREFIX, question_map)
        if not new_param:
            return None, []
        options = option_map.get(int(param.removeprefix(QUESTION_PREFIX)))
        if not options:
            return new_param, values
        return new_param, _remap_option_values(values, options)
    return param, values


def remap_filters(filters, **maps):
    result = {}
    for param, values in filters.items():
        new_param, new_values = _remap_filter(param, values, **maps)
        if new_param and new_values:
            result[new_param] = new_values
    return result


def remap_columns(columns, question_map, score_category_map):
    result = []
    for column in columns:
        descending = column.startswith("-")
        name = column.removeprefix("-")
        if name.startswith(QUESTION_PREFIX):
            name = _remap_prefixed(name, QUESTION_PREFIX, question_map)
        elif prefix := _score_prefix(name):
            name = _remap_prefixed(name, prefix, score_category_map)
        if not name:
            continue
        result.append(f"-{name}" if descending else name)
    return result


@receiver(event_copy_data)
def copy_table_exports(
    sender,
    other,
    question_map,
    track_map,
    submission_type_map,
    tag_map,
    score_category_map,
    **kwargs,
):
    from pretalx.common.models.exports import TableExport  # noqa: PLC0415 -- receiver
    from pretalx.event.models import Event  # noqa: PLC0415 -- receiver

    source = Event.objects.filter(slug__iexact=other).first()
    if not source:
        return
    exports = list(TableExport.objects.filter(event=source))
    if not exports:
        return
    option_map = _option_map(question_map)
    for export in exports:
        export.pk = None
        export.event = sender
        export.columns = remap_columns(
            export.columns or [], question_map, score_category_map
        )
        export.ordering = remap_columns(
            export.ordering or [], question_map, score_category_map
        )
        export.filters = remap_filters(
            export.filters or {},
            track_map=track_map,
            submission_type_map=submission_type_map,
            tag_map=tag_map,
            question_map=question_map,
            option_map=option_map,
        )
        export.save()
