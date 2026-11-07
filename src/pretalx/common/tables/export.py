# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import contextlib
import datetime as dt
import io
import json
import re
import textwrap
from decimal import Decimal

import xlsxwriter
from django import forms
from django.http import QueryDict
from django.utils import timezone, translation
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from i18nfield.strings import LazyI18nString
from i18nfield.utils import I18nJSONEncoder
from xlsxwriter.utility import cell_autofit_width

from pretalx.common.exporter import write_csv
from pretalx.common.signals import (
    register_exportable_tables,
    register_table_serializers,
)
from pretalx.common.tables.filters import FilterContext, TableFilterSet


class ExportError(Exception):
    pass


ALL_LOCALES = "__all__"


class TableSerializer:
    """Turns a configured table into file content of one format."""

    identifier = None
    verbose_name = None
    extension = None
    content_type = None
    options = {}
    all_locales = False

    def __init__(self, event, options=None):
        self.event = event
        self.options = {**self.default_options(event), **(options or {})}

    @classmethod
    def option_fields(cls, event):
        fields = {}
        if len(event.locales) > 1:
            choices = list(event.named_locales)
            if cls.all_locales:
                choices.insert(0, (ALL_LOCALES, _("All languages")))
            fields["locale"] = forms.ChoiceField(
                label=_("Language"),
                choices=choices,
                initial=ALL_LOCALES if cls.all_locales else event.locale,
            )
        return {
            **fields,
            **{name: factory(event) for name, factory in cls.options.items()},
        }

    @classmethod
    def default_options(cls, event):
        return {name: field.initial for name, field in cls.option_fields(event).items()}

    @cached_property
    def locale(self):
        locale = self.options.get("locale")
        if locale in self.event.locales:
            return locale
        if self.all_locales and locale in (None, ALL_LOCALES):
            return None
        return self.event.locale

    def export(self, table, file):
        with translation.override(self.locale or self.event.locale):
            self.render(table, file)

    def render(self, table, file):
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


LIST_DELIMITERS = {"newline": "\n", "comma": ", "}


def get_list_delimiter_field(event):
    return forms.ChoiceField(
        label=_("List separator"),
        help_text=_(
            "How multiple values in one cell are separated, for example several speakers of one session."
        ),
        choices=(("newline", _("Newline")), ("comma", _("Comma"))),
        initial="newline",
        required=False,
    )


class CSVSerializer(TableSerializer):
    identifier = "csv"
    verbose_name = _("CSV")
    extension = "csv"
    content_type = "text/csv"
    options = {
        "delimiter": lambda event: forms.ChoiceField(
            label=_("Field separator"),
            choices=((",", _("Comma")), (";", _("Semicolon")), ("\t", _("Tab"))),
            initial=",",
            required=False,
        ),
        "list_delimiter": get_list_delimiter_field,
    }

    def format_value(self, value):
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(_("Yes") if value else _("No"))
        if isinstance(value, (list, tuple, set)):
            delimiter = LIST_DELIMITERS.get(self.options.get("list_delimiter"), "\n")
            return delimiter.join(self.format_value(entry) for entry in value)
        if isinstance(value, dt.datetime):
            return _localize_datetime(value).isoformat()
        if isinstance(value, (dt.date, dt.time)):
            return value.isoformat()
        return str(value)

    def render(self, table, file):
        rows = table.as_values()
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
    all_locales = True

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
            return str(value)
        if value is None or isinstance(value, (bool, int, float, str, dict)):
            return value
        return str(value)

    def render(self, table, file):
        names = table.export_column_names()
        rows = table.as_values()
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


class XLSXSerializer(TableSerializer):
    identifier = "xlsx"
    verbose_name = _("Microsoft Excel")
    extension = "xlsx"
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    options = {"list_delimiter": get_list_delimiter_field}

    @staticmethod
    def sheet_name(name):
        name = re.sub(r"[\[\]:*?/\\]", "", str(name or ""))
        name = name.encode("utf-16-le")[:62].decode("utf-16-le", errors="ignore")
        name = name.strip("'")
        if not name or name.lower() == "history":
            return None
        return name

    @staticmethod
    def text_width(text):
        # Capping at 100 chars because we won't show much more anyway
        return max(cell_autofit_width(line[:100]) for line in text.split("\n"))

    def format_value(self, value):
        if isinstance(value, (list, tuple, set)):
            delimiter = LIST_DELIMITERS.get(self.options.get("list_delimiter"), "\n")
            entries = (
                str(_("Yes") if entry else _("No"))
                if isinstance(entry, bool)
                else self.format_value(entry)
                for entry in value
            )
            return delimiter.join(
                "" if entry is None else str(entry) for entry in entries
            )
        if isinstance(value, dt.datetime):
            value = _localize_datetime(value)
        if isinstance(value, dt.date) and value.year < 1900:
            # Excel cannot show dates before 1900 and renders them as ###.
            return value.isoformat()
        if value is None or isinstance(
            value, (bool, int, float, Decimal, dt.date, dt.time)
        ):
            return value
        return str(value)

    def render(self, table, file):
        workbook = xlsxwriter.Workbook(
            file,
            {
                "constant_memory": True,
                "default_format_properties": {
                    "font_name": "Calibri",  # library default
                    "font_size": 11,  # library default
                    "valign": "top",
                },
                "nan_inf_to_errors": True,
                "remove_timezone": True,
            },
        )
        workbook.set_properties(
            {"title": str(table.export_name or ""), "author": "pretalx"}
        )
        worksheet = workbook.add_worksheet(self.sheet_name(table.export_name))
        worksheet.freeze_panes(1, 0)
        worksheet.ignore_errors({"number_stored_as_text": "A1:XFD1048576"})
        worksheet.repeat_rows(0)
        worksheet.set_landscape()
        worksheet.fit_to_pages(1, 0)
        bold = workbook.add_format({"bold": True})
        wrap = workbook.add_format({"text_wrap": True})
        checkbox = workbook.add_format(
            {"checkbox": True}
        )  # pre-2024 versions show as TRUE / FALSE
        date_formats = (
            (
                dt.datetime,
                workbook.add_format({"num_format": "yyyy-mm-dd hh:mm"}),
                "%Y-%m-%d %H:%M",
            ),
            (dt.date, workbook.add_format({"num_format": "yyyy-mm-dd"}), "%Y-%m-%d"),
            (dt.time, workbook.add_format({"num_format": "hh:mm"}), "%H:%M"),
        )

        rows = table.as_values()
        headers = [str(header) for header in next(rows)]
        # autofit() does not work in constant_memory mode, so we track width while writing.
        # We add 16 pixels for the filter button, like xlsxwriter does.
        widths = {
            col: self.text_width(header) + 16 for col, header in enumerate(headers)
        }
        for col, header in enumerate(headers):
            worksheet.write_string(0, col, header, bold)
        last_row = 0
        for last_row, row in enumerate(rows, start=1):
            for col, raw in enumerate(row):
                value = self.format_value(raw)
                if value is None:
                    continue
                if isinstance(value, str):
                    if not re.fullmatch(
                        r"https?://\S+", value, re.IGNORECASE
                    ) or worksheet.write_url(last_row, col, value):
                        # write_url can fail for absurdly long links or too many in one sheet (65530)
                        worksheet.write_string(
                            last_row, col, value, wrap if "\n" in value else None
                        )
                    text = value
                elif isinstance(value, bool):
                    worksheet.write_boolean(last_row, col, value, checkbox)
                    text = "TRUE" if value else "FALSE"
                elif isinstance(value, (dt.date, dt.time)):
                    cell_format, pattern = next(
                        (cell_format, pattern)
                        for value_type, cell_format, pattern in date_formats
                        if isinstance(value, value_type)
                    )
                    worksheet.write_datetime(last_row, col, value, cell_format)
                    text = value.strftime(pattern)
                else:
                    worksheet.write_number(last_row, col, value)
                    text = str(value)
                widths[col] = max(widths[col], self.text_width(text))
        worksheet.autofilter(0, 0, last_row, len(headers) - 1)
        for col, width in widths.items():
            # 64 is the default column width. Capping at 500 to keep the table sane.
            if width > 64:
                worksheet.set_column_pixels(col, col, min(width, 500))
        workbook.close()


def get_table_serializers(event):
    serializers = {
        serializer.identifier: serializer
        for serializer in (CSVSerializer, JSONSerializer, XLSXSerializer)
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
    serializer = serializer_class(event, options=config.get("serializer_options"))
    with timezone.override(event.tz):
        table = build_export_table(event, user, config)
        serializer.export(table, file)
