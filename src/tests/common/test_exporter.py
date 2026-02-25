from urllib.parse import quote

import pytest
from django.utils.timezone import now

from pretalx.common.exporter import BaseExporter, CSVExporterMixin

pytestmark = pytest.mark.unit


class ConcreteExporter(BaseExporter):
    verbose_name = "Test Exporter"
    filename_identifier = "test-export"
    extension = "json"
    content_type = "application/json"
    public = True
    icon = "fa-download"

    def get_data(self, request, **kwargs):
        return '{"test": true}'


class ConcreteCSVExporter(CSVExporterMixin, BaseExporter):
    verbose_name = "CSV Export"
    filename_identifier = "csv-export"
    public = False
    icon = "fa-table"

    def get_csv_data(self, request, **kwargs):
        return ["name", "age"], [{"name": "Alice", "age": 30}]


def test_base_exporter_stores_event():
    exporter = BaseExporter("my-event")

    assert exporter.event == "my-event"


@pytest.mark.parametrize(
    "action",
    (
        pytest.param(lambda e: e.verbose_name, id="verbose_name"),
        pytest.param(lambda e: e.filename_identifier, id="filename_identifier"),
        pytest.param(lambda e: e.extension, id="extension"),
        pytest.param(lambda e: e.content_type, id="content_type"),
        pytest.param(lambda e: e.public, id="public"),
        pytest.param(lambda e: e.icon, id="icon"),
        pytest.param(lambda e: e.get_data(None), id="get_data"),
        pytest.param(str, id="str"),
        pytest.param(lambda e: e.render(request=None), id="render"),
        pytest.param(lambda e: e.show_public, id="show_public"),
    ),
)
def test_base_exporter_raises_not_implemented(action):
    with pytest.raises(NotImplementedError):
        action(BaseExporter(None))


def test_concrete_exporter_str_returns_identifier():
    exporter = ConcreteExporter(None)

    assert str(exporter) == "test-export.json"


def test_concrete_exporter_identifier():
    exporter = ConcreteExporter(None)

    assert exporter.identifier == "test-export.json"


def test_exporter_get_timestamp_format():
    exporter = ConcreteExporter(None)

    timestamp = exporter.get_timestamp()

    assert timestamp == now().strftime("-%Y-%m-%d-%H-%M")


@pytest.mark.django_db
def test_exporter_filename(event):
    exporter = ConcreteExporter(event)

    filename = exporter.filename

    assert filename.startswith(f"{event.slug}-test-export-")
    assert filename.endswith(".json")


def test_exporter_quoted_identifier():
    exporter = ConcreteExporter(None)

    assert exporter.quoted_identifier == quote("test-export.json")


@pytest.mark.parametrize(
    ("attr", "expected"),
    (
        ("show_public", True),
        ("cors", None),
        ("show_qrcode", False),
        ("group", "submission"),
    ),
)
def test_exporter_default_property(attr, expected):
    assert getattr(ConcreteExporter(None), attr) == expected


@pytest.mark.django_db
def test_exporter_render(event):
    exporter = ConcreteExporter(event)

    filename, content_type, data = exporter.render(request=None)

    assert filename.startswith(f"{event.slug}-test-export-")
    assert content_type == "application/json"
    assert data == '{"test": true}'


@pytest.mark.django_db
def test_exporter_urls_base(event):
    exporter = ConcreteExporter(event)

    url = str(exporter.urls.base)

    assert event.slug in url
    assert "test-export.json" in url


@pytest.mark.django_db
def test_exporter_get_qrcode_returns_svg(event):
    exporter = ConcreteExporter(event)

    svg = exporter.get_qrcode()

    assert "svg" in str(svg).lower()


@pytest.mark.parametrize(
    ("attr", "expected"), (("extension", "csv"), ("content_type", "text/plain"))
)
def test_csv_exporter_mixin_class_attribute(attr, expected):
    assert getattr(CSVExporterMixin, attr) == expected


def test_csv_exporter_get_data_returns_csv():
    exporter = ConcreteCSVExporter(None)

    data = exporter.get_data(request=None)

    assert data == "name,age\r\nAlice,30\r\n"
