# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import contextlib
import datetime as dt
import io
import json
import textwrap
from decimal import Decimal

from django import forms
from django.http import QueryDict
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from i18nfield.strings import LazyI18nString
from i18nfield.utils import I18nJSONEncoder

from pretalx.common.exporter import write_csv
from pretalx.common.signals import (
    register_exportable_tables,
    register_table_serializers,
)
from pretalx.common.tables.filters import FilterContext, TableFilterSet


class ExportError(Exception):
    pass


class TableSerializer:
    """Turns a configured table into file content of one format.

    ``multilang`` formats can carry structured i18n values and make the
    locale optional; the others need a locale to flatten them. ``options``
    maps option names to form field factories for the export forms.
    """

    identifier = None
    verbose_name = None
    extension = None
    content_type = None
    multilang = False
    options = {}

    def __init__(self, table, *, locale=None, options=None):
        self.table = table
        self.locale = locale
        self.options = {**self.default_options(), **(options or {})}

    @classmethod
    def default_options(cls):
        return {name: field().initial for name, field in cls.options.items()}

    @classmethod
    def option_fields(cls):
        return {name: field() for name, field in cls.options.items()}

    def render(self, file):
        raise NotImplementedError


def _localize_datetime(value):
    if timezone.is_aware(value):
        return timezone.localtime(value)
    return value


@contextlib.contextmanager
def text_writer(file, *, newline=None):
    """Wrap a binary file for text writing, leaving it open and owned by the caller."""
    text = io.TextIOWrapper(file, encoding="utf-8", newline=newline)
    try:
        yield text
    finally:
        text.flush()
        text.detach()


class CSVSerializer(TableSerializer):
    identifier = "csv"
    verbose_name = _("CSV")
    extension = "csv"
    content_type = "text/csv"
    options = {
        "delimiter": lambda: forms.ChoiceField(
            label=_("Field separator"),
            choices=((",", _("Comma")), (";", _("Semicolon")), ("\t", _("Tab"))),
            initial=",",
            required=False,
        ),
        "list_delimiter": lambda: forms.ChoiceField(
            label=_("List separator"),
            help_text=_(
                "How multiple values in one cell are separated, for example several speakers of one session."
            ),
            choices=(("newline", _("Newline")), ("comma", _("Comma"))),
            initial="newline",
            required=False,
        ),
    }
    list_delimiters = {"newline": "\n", "comma": ", "}

    def format_value(self, value):
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(_("Yes") if value else _("No"))
        if isinstance(value, (list, tuple, set)):
            delimiter = self.list_delimiters.get(
                self.options.get("list_delimiter"), "\n"
            )
            return delimiter.join(self.format_value(entry) for entry in value)
        if isinstance(value, dt.datetime):
            return _localize_datetime(value).isoformat()
        if isinstance(value, (dt.date, dt.time)):
            return value.isoformat()
        return str(value)

    def render(self, file):
        rows = self.table.as_values()
        headers = [str(header) for header in next(rows)]
        with text_writer(file, newline="") as text:
            write_csv(
                text,
                fieldnames=headers,
                delimiter=self.options.get("delimiter") or ",",
                rows=([self.format_value(value) for value in row] for row in rows),
            )


class JSONSerializer(TableSerializer):
    identifier = "json"
    verbose_name = _("JSON")
    extension = "json"
    content_type = "application/json"
    multilang = True

    def format_value(self, value):
        if isinstance(value, LazyI18nString):
            return str(value) if self.locale else value
        if isinstance(value, (list, tuple, set)):
            return [self.format_value(entry) for entry in value]
        if isinstance(value, dt.datetime):
            return _localize_datetime(value).isoformat()
        if isinstance(value, (dt.date, dt.time)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if value is None or isinstance(value, (bool, int, float, str, dict)):
            return value
        return str(value)

    def render(self, file):
        names = self.table.export_column_names()
        rows = self.table.as_values()
        next(rows)
        with text_writer(file) as text:
            text.write("[")
            empty = True
            for row in rows:
                data = dict(
                    zip(names, (self.format_value(value) for value in row), strict=True)
                )
                text.write("\n" if empty else ",\n")
                text.write(
                    textwrap.indent(
                        json.dumps(data, cls=I18nJSONEncoder, indent=2), "  "
                    )
                )
                empty = False
            text.write("]" if empty else "\n]")


def get_table_serializers(event):
    serializers = {
        serializer.identifier: serializer
        for serializer in (CSVSerializer, JSONSerializer)
    }
    for _receiver, serializer in register_table_serializers.send(event):
        if serializer is not None:
            serializers.setdefault(serializer.identifier, serializer)
    return serializers


def get_table_serializer(event, identifier):
    return get_table_serializers(event).get(identifier)


def get_exportable_tables(event):
    responses = sorted(
        register_exportable_tables.send(event),
        key=lambda response: not response[0].__module__.startswith("pretalx."),
    )
    tables = {}
    for _receiver, table_classes in responses:
        for table_class in table_classes or ():
            if table_class.export_permission is not None:
                tables.setdefault(table_class.__name__, table_class)
    return tables


def get_exportable_table(event, name):
    return get_exportable_tables(event).get(name)


def filters_to_querydict(filters):
    data = QueryDict(mutable=True)
    for param, values in (filters or {}).items():
        if isinstance(values, (list, tuple)):
            data.setlist(param, [str(value) for value in values])
        else:
            data[param] = str(values)
    return data


def build_filterset(table_class, event, user, filters, form_id="", apply_initials=True):
    context = FilterContext(
        event=event, user=user, **table_class.get_filter_options(event, user)
    )
    table_filters = table_class.get_filters(context)
    if not table_filters:
        return None
    return TableFilterSet(
        table_filters,
        data=filters_to_querydict(filters),
        context=context,
        form_id=form_id,
        apply_initials=apply_initials,
    )


def build_export_table(event, user, config):
    table_class = get_exportable_table(event, config.get("table"))
    if table_class is None:
        raise ExportError("unknown table")
    if not user.has_perm(table_class.export_permission, event):
        raise ExportError("permission denied")
    queryset = table_class.prepare_queryset(
        table_class.base_queryset(event, user), event=event, user=user
    )
    filterset = build_filterset(
        table_class, event, user, config.get("filters"), apply_initials=False
    )
    if filterset:
        queryset = filterset.filter(queryset)
    queryset = table_class.augment_queryset(queryset, event=event, user=user)
    table = table_class(
        data=queryset, event=event, user=user, filterset=filterset, for_export=True
    )
    table.configure_export(config.get("columns"), config.get("ordering"))
    return table


def render_export(event, user, config, file):
    serializer_class = get_table_serializer(event, config.get("serializer"))
    if serializer_class is None:
        raise ExportError("unknown format")
    locale = config.get("locale") or None
    if locale and locale not in event.locales:
        locale = None
    if not locale and (not serializer_class.multilang or len(event.locales) <= 1):
        locale = event.locale
    with timezone.override(event.tz), translation.override(locale or event.locale):
        table = build_export_table(event, user, config)
        serializer = serializer_class(
            table, locale=locale, options=config.get("serializer_options")
        )
        serializer.render(file)
