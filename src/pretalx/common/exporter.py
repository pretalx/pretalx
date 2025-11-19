# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from io import StringIO
from urllib.parse import quote

from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from django.utils.timezone import now

from pretalx.common.urls import EventUrls


class BaseExporter:
    """The base class for all data exporters."""

    def __init__(self, event):
        self.event = event

    def __str__(self):
        """The identifier may be used for callbacks and debugging."""
        return self.identifier

    @property
    def verbose_name(self) -> str:
        """A human-readable name for this exporter.

        This should be short but self-explaining. Good examples include
        'JSON' or 'Microsoft Excel'.
        """
        raise NotImplementedError()  # NOQA

    @property
    def filename_identifier(self) -> str:
        """A short and unique identifier for this exporter.

        This should only contain lower-case letters and in most cases
        will be the same as your package name. By default, it will be
        used in the generated filename.
        You do not have to implement this property if you set both
        ``identifier`` and ``filename`` instead.
        """
        raise NotImplementedError()  # NOQA

    @property
    def extension(self) -> str:
        """The file extension to be used for this exporter.

        By default, it will be used in the generated filename.
        You do not have to implement this property if you implement
        ``filename`` instead.
        """
        raise NotImplementedError()  # NOQA

    @property
    def content_type(self) -> str:
        """The content type to be used when returning data.

        You do not need to implement this property if you override ``render``.
        """
        raise NotImplementedError()  # NOQA

    @property
    def identifier(self) -> str:
        """A short and unique identifier for this exporter.

        This should only contain lower-case letters and in most cases
        will be the same as your package name.
        By default, this will return "{filename_identifier}.{extension}"
        """
        return f"{self.filename_identifier}.{self.extension}"

    def get_timestamp(self):
        return now().strftime("-%Y-%m-%d-%H-%M")

    @property
    def filename(self) -> str:
        """
        If you define an ``extension`` attribute on your exporter,
        you can use the ``filename`` property in your ``get_data`` method.
        It will return a filename including the event slug, your exporter's
        identifier (or the ``filename_identifier``) and a timestamp
        for reliable sorting.
        """
        identifier = self.filename_identifier or self.identifier
        timestamp = self.get_timestamp()
        return f"{self.event.slug}-{identifier}-{timestamp}.{self.extension}"

    @cached_property
    def quoted_identifier(self) -> str:
        return quote(self.identifier)

    @property
    def public(self) -> bool:
        """Return True if the exported data should be publicly available once
        the event is public, False otherwise.

        If you need additional data to decide, you can instead implement the
        ``is_public(self, request, **kwargs)`` method, which overrides this
        property.
        """
        raise NotImplementedError()  # NOQA

    @property
    def show_public(self) -> bool:
        """This value determines if the exporter is listed among the public
        exporters on the schedule page. It defaults to the `public` property,
        but you can override it in order to hide public exports from the
        user-facing menu."""
        return self.public

    @property
    def cors(self) -> str:
        """If you want to let this exporter be accessed with JavaScript, set
        cors = '*' for all accessing domains, or supply a specific domain."""
        return None

    @property
    def show_qrcode(self) -> bool:
        """Return True if the link to the exporter should be shown as QR code,
        False (default) otherwise.

        Override the get_qr_code method to override the QR code itself.
        """
        return False

    @property
    def icon(self) -> str:
        """Return either a fa- string or some other symbol to accompany the
        exporter in displays."""
        raise NotImplementedError()  # NOQA

    @property
    def group(self) -> str:
        """Return either 'speaker' or 'submission' to indicate on which
        organiser export page to list this export.

        Invalid values default to 'submission', which is also where all
        schedule exports live.
        """
        return "submission"

    def get_data(self, request, **kwargs) -> str:
        """Return the file contents that ``render`` should return."""
        raise NotImplementedError()  # NOQA

    def render(self, request, **kwargs) -> tuple[str, str, str]:
        return (
            self.filename,
            self.content_type,
            self.get_data(request=request, **kwargs),
        )

    class urls(EventUrls):
        """The base attribute of this class contains the relative URL where
        this exporter's data will be found, e.g. /event/schedule/export/my-
        export.ext Use ``exporter.urls.base.full()`` for the complete URL,
        taking into account the configured event URL, or HTML export URL."""

        base = "{self.event.urls.export}{self.quoted_identifier}"

    def get_qrcode(self):
        import qrcode
        import qrcode.image.svg
        from defusedxml import ElementTree

        image = qrcode.make(
            self.urls.base.full(), image_factory=qrcode.image.svg.SvgPathFillImage
        )
        return mark_safe(ElementTree.tostring(image.get_image()).decode())


class CSVExporterMixin:
    extension = "csv"
    content_type = "text/plain"

    def get_data(self, request, **kwargs):
        from defusedcsv import csv

        fieldnames, data = self.get_csv_data(request, **kwargs)
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
        return output.getvalue()
