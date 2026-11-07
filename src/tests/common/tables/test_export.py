# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import csv
import datetime as dt
import io
import json
import zipfile
from decimal import Decimal
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.core.files.base import ContentFile

from pretalx.common.signals import (
    register_exportable_tables,
    register_table_serializers,
)
from pretalx.common.tables.export import (
    ALL_LOCALES,
    CSVSerializer,
    ExportError,
    JSONSerializer,
    TableSerializer,
    XLSXSerializer,
    build_export_table,
    filters_to_querydict,
    get_exportable_table,
    get_exportable_tables,
    get_table_serializer,
    get_table_serializers,
    render_export,
)
from pretalx.orga.tables.feedback import SubmissionFeedbackTable
from pretalx.orga.tables.submission import SubmissionTable
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.enums import SubmissionStates
from pretalx.submission.models import Submission
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    FeedbackFactory,
    QuestionFactory,
    QueuedMailFactory,
    ReviewFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    RoomFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TagFactory,
    TalkSlotFactory,
    TrackFactory,
)
from tests.utils import make_orga_user, refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _config(**overrides):
    config = {
        "table": "SubmissionTable",
        "columns": ["title"],
        "ordering": [],
        "filters": {},
        "serializer": "csv",
        "serializer_options": {},
    }
    config.update(overrides)
    return config


def _render(event, user, config):
    output = io.BytesIO()
    render_export(event, user, config, output)
    return output.getvalue()


def _csv_rows(content):
    return list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))


XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _xlsx_cells(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        styles = ET.fromstring(archive.read("xl/styles.xml"))
    formats = {
        fmt.get("numFmtId"): fmt.get("formatCode")
        for fmt in styles.iterfind("m:numFmts/m:numFmt", XLSX_NS)
    }
    xfs = styles.findall("m:cellXfs/m:xf", XLSX_NS)
    fonts = styles.findall("m:fonts/m:font", XLSX_NS)
    cells = {}
    for cell in sheet.iterfind("m:sheetData/m:row/m:c", XLSX_NS):
        xf = xfs[int(cell.get("s", 0))]
        text = cell.findtext(
            "m:is/m:t" if cell.get("t") == "inlineStr" else "m:v", namespaces=XLSX_NS
        )
        cells[cell.get("r")] = {
            "value": text,
            "type": cell.get("t"),
            "format": formats.get(xf.get("numFmtId")),
            "bold": fonts[int(xf.get("fontId"))].find("m:b", XLSX_NS) is not None,
            "wrap": xf.find("m:alignment[@wrapText='1']", XLSX_NS) is not None,
        }
    name = workbook.find("m:sheets/m:sheet", XLSX_NS).get("name")
    return name, sheet, cells


def test_table_serializers_offer_csv_json_and_xlsx(event):
    assert get_table_serializers(event) == {
        "csv": CSVSerializer,
        "json": JSONSerializer,
        "xlsx": XLSXSerializer,
    }
    assert get_table_serializer(event, "csv") is CSVSerializer
    assert get_table_serializer(event, "pdf") is None
    assert CSVSerializer.default_options(event) == {
        "delimiter": ",",
        "list_delimiter": "newline",
    }
    assert JSONSerializer.default_options(event) == {}
    assert XLSXSerializer.default_options(event) == {"list_delimiter": "newline"}


@pytest.mark.parametrize(
    ("locales", "has_locale"), ((["en"], False), (["en", "de"], True))
)
def test_serializers_offer_locale_only_with_several_languages(locales, has_locale):
    event = EventFactory(locales=locales, locale="en")

    csv_fields = CSVSerializer.option_fields(event)
    json_fields = JSONSerializer.option_fields(event)

    assert list(csv_fields) == (["locale"] if has_locale else []) + [
        "delimiter",
        "list_delimiter",
    ]
    assert list(json_fields) == (["locale"] if has_locale else [])
    assert CSVSerializer.default_options(event).get("locale") == (
        "en" if has_locale else None
    )
    assert JSONSerializer.default_options(event).get("locale") == (
        ALL_LOCALES if has_locale else None
    )
    if has_locale:
        assert [value for value, _label in csv_fields["locale"].choices] == locales
        assert [value for value, _label in json_fields["locale"].choices] == [
            ALL_LOCALES,
            *locales,
        ]


def test_table_serializers_add_plugin_formats_without_replacing_core(
    event, register_signal_handler
):
    class PDFSerializer(TableSerializer):
        identifier = "pdf"

    class FakeCSVSerializer(TableSerializer):
        identifier = "csv"

    for serializer in (None, PDFSerializer, FakeCSVSerializer):
        register_signal_handler(
            register_table_serializers,
            lambda signal, sender, serializer=serializer, **kwargs: serializer,
        )

    assert get_table_serializers(event) == {
        "csv": CSVSerializer,
        "json": JSONSerializer,
        "xlsx": XLSXSerializer,
        "pdf": PDFSerializer,
    }


def test_exportable_tables_add_plugin_tables_without_replacing_core(
    event, register_signal_handler
):
    class PluginTable(SubmissionTable):
        export_name = "Plugin"

    clash = type("SubmissionTable", (PluginTable,), {})

    for tables in (None, [PluginTable, clash, SubmissionFeedbackTable]):
        register_signal_handler(
            register_exportable_tables,
            lambda signal, sender, tables=tables, **kwargs: tables,
        )

    tables = get_exportable_tables(event)

    assert list(tables) == [
        "SubmissionTable",
        "ReviewTable",
        "ReviewExportTable",
        "SpeakerTable",
        "OutboxMailTable",
        "SentMailTable",
        "MailTemplateTable",
        "FeedbackTable",
        "SubmitterAccessCodeTable",
        "TrackTable",
        "SubmissionTypeTable",
        "TagTable",
        "RoomTable",
        "SubmissionQuestionTable",
        "SpeakerQuestionTable",
        "ReviewerQuestionTable",
        "SpeakerInformationTable",
        "PluginTable",
    ]
    assert tables["SubmissionTable"] is SubmissionTable
    assert get_exportable_table(event, "PluginTable") is PluginTable
    assert get_exportable_table(event, "QuestionTable") is None


def test_exportable_table_base_querysets_scope_to_the_event(event):
    orga = make_orga_user(event, can_change_submissions=True)
    other = EventFactory()
    expected = {
        "MailTemplateTable": set(event.mail_templates.exclude(is_auto_created=True)),
        "FeedbackTable": {FeedbackFactory(talk=SubmissionFactory(event=event))},
        "SubmitterAccessCodeTable": {SubmitterAccessCodeFactory(event=event)},
        "TrackTable": {TrackFactory(event=event)},
        "SubmissionTypeTable": {event.cfp.default_type},
        "TagTable": {TagFactory(event=event)},
        "RoomTable": {RoomFactory(event=event)},
        "SpeakerQuestionTable": {QuestionFactory(event=event, target="speaker")},
        "ReviewerQuestionTable": {QuestionFactory(event=event, target="reviewer")},
        "SpeakerInformationTable": {SpeakerInformationFactory(event=event)},
    }
    FeedbackFactory(talk=SubmissionFactory(event=other))
    SubmitterAccessCodeFactory(event=other)
    TrackFactory(event=other)
    TagFactory(event=other)
    RoomFactory(event=other)
    QuestionFactory(event=other, target="speaker")
    QuestionFactory(event=other, target="reviewer")
    SpeakerInformationFactory(event=other)
    tables = get_exportable_tables(event)

    for name, rows in expected.items():
        assert set(tables[name].base_queryset(event, orga)) == rows, name


def test_filters_to_querydict_keeps_lists_and_scalars():
    data = filters_to_querydict(
        {"state": ["accepted", "confirmed"], "q": "x", "track": ""}
    )

    assert data.getlist("state") == ["accepted", "confirmed"]
    assert data["q"] == "x"
    assert data["track"] == ""


@pytest.mark.parametrize(
    ("filters", "ordering", "titles"),
    (
        ({}, ["title"], ["Alpha", "Beta", "Gamma"]),
        ({"state": ["accepted"]}, ["-title"], ["Beta", "Alpha"]),
        ({"track": ["99999"], "bogus": ["1"]}, ["title"], ["Alpha", "Beta", "Gamma"]),
        ({"state": ["withdrawn"]}, ["title"], []),
    ),
    ids=(
        "empty_filters_keep_all_rows",
        "filter_and_order",
        "unknown_filters_ignored",
        "no_matching_rows",
    ),
)
def test_export_applies_filters_and_ordering(event, filters, ordering, titles):
    user = make_orga_user(event, can_change_submissions=True)
    SubmissionFactory(event=event, title="Beta", state=SubmissionStates.ACCEPTED)
    SubmissionFactory(event=event, title="Alpha", state=SubmissionStates.ACCEPTED)
    SubmissionFactory(event=event, title="Gamma", state=SubmissionStates.REJECTED)

    config = _config(columns=["title"], ordering=ordering, filters=filters)

    content = _render(event, user, config)
    json_content = _render(event, user, {**config, "serializer": "json"})

    assert [row[1] for row in _csv_rows(content)[1:]] == titles
    assert [row["title"] for row in json.loads(json_content)] == titles


def test_export_keeps_columns_hidden_from_the_column_picker(event):
    user = make_orga_user(event, can_change_submissions=True)
    mail = QueuedMailFactory(event=event, subject="Hello")
    config = _config(table="OutboxMailTable", columns=["subject"])

    rows = _csv_rows(_render(event, user, config))

    assert rows[0] == ["ID", "Status", "Subject"]
    assert rows[1] == [str(mail.pk), "draft", "Hello"]


def test_export_reviewer_question_table(event):
    user = make_orga_user(event, can_change_event_settings=True)
    reviewer_question = QuestionFactory(
        event=event, target="reviewer", question="Confidence", variant="number"
    )
    QuestionFactory(event=event, target="submission", question="Diet")
    config = _config(
        table="ReviewerQuestionTable", columns=["question", "variant", "active"]
    )

    rows = _csv_rows(_render(event, user, config))

    assert rows == [
        ["ID", "Custom field", "Field type", "Active"],
        [str(reviewer_question.pk), "Confidence", "number", "Yes"],
    ]


def test_export_speaker_information_table(event):
    user = make_orga_user(event, can_change_submissions=True)
    track = TrackFactory(event=event, name="Security")
    submission_type = SubmissionTypeFactory(event=event, name="Workshop")
    information = SpeakerInformationFactory(
        event=event, title="Slides", text="Upload them.", target_group="confirmed"
    )
    information.limit_tracks.add(track)
    information.limit_types.add(submission_type)
    information.resource.save("template.odp", ContentFile(b"slides"))
    SpeakerInformationFactory(event=event, title="Bare")
    config = _config(
        table="SpeakerInformationTable",
        columns=["title", "text", "target_group", "limit_tracks", "limit_types"],
        serializer_options={"list_delimiter": "comma"},
    )

    rows = _csv_rows(_render(event, user, config))
    json_rows = json.loads(
        _render(
            event,
            user,
            {**config, "columns": ["resource", "limit_tracks"], "serializer": "json"},
        )
    )

    assert rows == [
        [
            "ID",
            "Title",
            "Text",
            "Target group",
            "Limit to tracks",
            "Limit to proposal types",
        ],
        [
            str(information.pk),
            "Slides",
            "Upload them.",
            "Only confirmed speakers",
            "Security",
            "Workshop",
        ],
        [
            str(information.pk + 1),
            "Bare",
            "Important information for speakers.",
            "All accepted speakers",
            "",
            "",
        ],
    ]
    assert json_rows == [
        {
            "ID": information.pk,
            "resource": settings.SITE_URL + information.resource.url,
            "limit_tracks": ["Security"],
        },
        {"ID": information.pk + 1, "resource": None, "limit_tracks": None},
    ]


def test_export_csv_keeps_columns_with_colliding_headers(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    questions = [
        QuestionFactory(event=event, question="Diet", target="submission")
        for _unused in range(2)
    ]
    for question, answer in zip(questions, ("vegan", "carnivore"), strict=True):
        AnswerFactory(question=question, submission=submission, answer=answer)
    config = _config(columns=[f"question_{question.pk}" for question in questions])

    rows = _csv_rows(_render(event, user, config))

    assert rows[0] == ["ID", "Diet", "Diet"]
    assert rows[1] == [submission.code, "vegan", "carnivore"]


def test_export_prepends_id_and_uses_data_values_in_event_timezone():
    event = EventFactory(timezone="Europe/Berlin")
    user = make_orga_user(event, can_change_submissions=True)
    speaker = SpeakerFactory(event=event, name="Ada Lovelace")
    submission = SubmissionFactory(
        event=event,
        title="Talk, with comma",
        abstract="Long text",
        state=SubmissionStates.ACCEPTED,
        do_not_record=False,
    )
    submission.speakers.add(speaker)
    Submission.objects.filter(pk=submission.pk).update(
        created=dt.datetime(2024, 6, 15, 14, 30, tzinfo=dt.UTC)
    )
    config = _config(
        columns=["title", "speakers", "state", "created", "do_not_record", "abstract"]
    )

    table = build_export_table(event, user, config)
    csv_content = _render(event, user, config)
    json_content = _render(event, user, {**config, "serializer": "json"})
    xlsx_content = _render(event, user, {**config, "serializer": "xlsx"})
    sheet_name, sheet, cells = _xlsx_cells(xlsx_content)
    with zipfile.ZipFile(io.BytesIO(xlsx_content)) as archive:
        core = ET.fromstring(archive.read("docProps/core.xml"))

    assert table.export_column_names() == [
        "ID",
        "title",
        "speakers",
        "state",
        "created",
        "do_not_record",
        "abstract",
    ]
    rows = _csv_rows(csv_content)
    assert rows[0] == [
        "ID",
        "Title",
        "Speakers",
        "State",
        "Created",
        "Do not record",
        "Abstract",
    ]
    assert rows[1] == [
        submission.code,
        "Talk, with comma",
        "Ada Lovelace",
        "accepted",
        "2024-06-15T16:30:00+02:00",
        "No",
        "Long text",
    ]
    assert json.loads(json_content) == [
        {
            "ID": submission.code,
            "title": "Talk, with comma",
            "speakers": ["Ada Lovelace"],
            "state": "accepted",
            "created": "2024-06-15T16:30:00+02:00",
            "do_not_record": False,
            "abstract": "Long text",
        }
    ]
    assert sheet_name == "Sessions"
    dc = {"dc": "http://purl.org/dc/elements/1.1/"}
    assert core.findtext("dc:title", namespaces=dc) == "Sessions"
    assert core.findtext("dc:creator", namespaces=dc) == "pretalx"
    assert sheet.find("m:sheetViews/m:sheetView/m:pane", XLSX_NS).get("ySplit") == "1"
    assert sheet.find("m:autoFilter", XLSX_NS).get("ref") == "A1:G2"
    assert [cells[f"{col}1"]["value"] for col in "ABCDEFG"] == rows[0]
    assert all(cells[f"{col}1"]["bold"] for col in "ABCDEFG")
    assert [cells[f"{col}2"]["value"] for col in "ABCDEFG"] == [
        submission.code,
        "Talk, with comma",
        "Ada Lovelace",
        "accepted",
        "45458.6875",
        "0",
        "Long text",
    ]
    assert cells["E2"]["format"] == "yyyy-mm-dd hh:mm"
    assert cells["F2"]["type"] == "b"


@pytest.mark.parametrize(
    ("columns", "expected"),
    (
        (["code", "title"], ["ID", "title"]),
        (["indicator", "actions", "pk", "nonexistent", "title"], ["ID", "title"]),
        ([], ["ID", "title", "speakers", "state", "is_featured"]),
    ),
    ids=("code_suppressed", "structural_and_unknown_dropped", "defaults"),
)
def test_export_column_selection(event, columns, expected):
    user = make_orga_user(event, can_change_submissions=True)
    SubmissionFactory(event=event, title="One")

    table = build_export_table(event, user, _config(columns=columns))

    assert table.export_column_names() == expected


def test_export_drops_columns_the_user_may_not_see(event):
    orga = make_orga_user(event, can_change_submissions=True)
    reviewer = make_orga_user(event, is_reviewer=True, can_change_submissions=False)
    SubmissionFactory(event=event, title="One")

    orga_table = build_export_table(
        event, orga, _config(columns=["title", "internal_notes", "speaker_emails"])
    )
    reviewer_table = build_export_table(
        event, reviewer, _config(columns=["title", "internal_notes", "speaker_emails"])
    )

    assert orga_table.export_column_names() == [
        "ID",
        "title",
        "internal_notes",
        "speaker_emails",
    ]
    assert reviewer_table.export_column_names() == ["ID", "title"]


@pytest.mark.parametrize(
    ("aggregate_method", "aggregate"),
    (("median", "median_score"), ("mean", "mean_score")),
)
def test_export_review_table_with_review_count_filter(
    event, aggregate_method, aggregate
):
    event.review_settings["aggregate_method"] = aggregate_method
    event.save()
    user = make_orga_user(event, can_change_submissions=True)
    category = ReviewScoreCategoryFactory(event=event, is_independent=True)
    reviewed = SubmissionFactory(event=event, title="Reviewed")
    zero = SubmissionFactory(event=event, title="Zero")
    half = SubmissionFactory(event=event, title="Half")
    for submission, scores in (
        (reviewed, (1, 2, 3)),
        (zero, (0, 0)),
        (half, (Decimal("2.25"), Decimal("2.25"))),
    ):
        for index, score in enumerate(scores):
            review = ReviewFactory(
                submission=submission,
                score=score,
                **({"user": user} if index == 0 else {}),
            )
            review.scores.add(ReviewScoreFactory(category=category, value=score))
    SubmissionFactory(event=event, title="Bare")
    independent = f"independent_score_{category.pk}"

    config = _config(
        table="ReviewTable",
        columns=["title", aggregate, "user_score", independent],
        filters={"review-count": ["1,3"]},
        serializer="json",
    )

    content = _render(event, user, config)

    rows = {row["title"]: row for row in json.loads(content)}
    assert rows == {
        "Reviewed": {
            "ID": reviewed.code,
            "title": "Reviewed",
            aggregate: "2.0",
            "user_score": "1.0",
            independent: "2.0",
        },
        "Zero": {
            "ID": zero.code,
            "title": "Zero",
            aggregate: "0.0",
            "user_score": "0.0",
            independent: "0.0",
        },
        "Half": {
            "ID": half.code,
            "title": "Half",
            aggregate: "2.2",
            "user_score": "2.2",
            independent: "2.2",
        },
    }
    table = build_export_table(event, user, config)
    rendered = next(row for row in table.rows if row.record.title == "Half")
    assert {
        name: str(rendered.get_cell(name))
        for name in (aggregate, "user_score", independent)
    } == {name: rows["Half"][name] for name in (aggregate, "user_score", independent)}


@pytest.mark.parametrize(
    ("variant", "answer_kwargs", "csv_value", "json_value"),
    (
        ("string", {"answer": "free text"}, "free text", "free text"),
        ("text", {"answer": "long\ntext"}, "long\ntext", "long\ntext"),
        ("boolean", {"answer": "True"}, "Yes", True),
        ("multiple_choice", {"options": ["one", "two"]}, "one, two", ["one", "two"]),
        ("number", {}, "", None),
        ("number", {"answer": "12.50"}, "12.50", "12.50"),
        ("number", {"answer": "lots"}, "lots", "lots"),
        ("number", {"answer": "NaN"}, "NaN", "NaN"),
        ("number", {"answer": "1e400"}, "1e400", "1e400"),
        ("number", {"answer": "-1e400"}, "'-1e400", "-1e400"),
        ("date", {"answer": "2026-05-04"}, "2026-05-04", "2026-05-04"),
        (
            "datetime",
            {"answer": "2026-05-04T10:30:00+00:00"},
            "2026-05-04T10:30:00+00:00",
            "2026-05-04T10:30:00+00:00",
        ),
        ("date", {"answer": "soon"}, "soon", "soon"),
        (
            "datetime",
            {"answer": "2026-05-04T10:30:00"},
            "2026-05-04T10:30:00+00:00",
            "2026-05-04T10:30:00+00:00",
        ),
        ("file", {"answer": ""}, "", None),
        ("file", {"answer_file": "cv.pdf"}, "<absolute url>", "<absolute url>"),
    ),
    ids=(
        "string",
        "text",
        "boolean",
        "multiple_choice",
        "unanswered",
        "number",
        "number_unparseable",
        "number_nan",
        "number_too_large",
        "number_too_large_negative",
        "date",
        "datetime",
        "unparseable",
        "naive_datetime",
        "file_missing",
        "file",
    ),
)
def test_export_question_columns(event, variant, answer_kwargs, csv_value, json_value):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    question = QuestionFactory(
        event=event, question="Diet", target="submission", variant=variant
    )
    if "options" in answer_kwargs:
        options = [
            AnswerOptionFactory(question=question, answer=label)
            for label in answer_kwargs["options"]
        ]
        AnswerFactory(question=question, submission=submission).options.set(options)
    elif "answer_file" in answer_kwargs:
        answer = AnswerFactory(question=question, submission=submission)
        answer.answer_file.save(answer_kwargs["answer_file"], ContentFile(b"cv"))
        csv_value = json_value = settings.SITE_URL + answer.answer_file.url
    elif answer_kwargs:
        AnswerFactory(question=question, submission=submission, **answer_kwargs)
    config = _config(
        columns=[f"question_{question.pk}"],
        serializer_options={"list_delimiter": "comma"},
    )

    csv_content = _render(event, user, config)
    json_content = _render(event, user, {**config, "serializer": "json"})

    assert _csv_rows(csv_content)[0] == ["ID", "Diet"]
    assert _csv_rows(csv_content)[1][1:] == [csv_value]
    assert json.loads(json_content)[0][f"question_{question.pk}"] == json_value


def test_export_csv_delimiter_option_joins_lists(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    for position, name in enumerate(("Ada", "Grace; Hopper")):
        submission.speakers.add(
            SpeakerFactory(event=event, name=name),
            through_defaults={"position": position},
        )

    newline = _render(event, user, _config(columns=["speakers"]))
    comma = _render(
        event,
        user,
        _config(columns=["speakers"], serializer_options={"list_delimiter": "comma"}),
    )

    semicolon = _render(
        event,
        user,
        _config(columns=["speakers"], serializer_options={"delimiter": ";"}),
    )

    assert _csv_rows(newline)[1] == [submission.code, "Ada\nGrace; Hopper"]
    assert _csv_rows(comma)[1] == [submission.code, "Ada, Grace; Hopper"]
    lines = semicolon.decode("utf-8-sig").splitlines()
    assert lines[0].count(";") == 1
    assert lines[1].startswith(f'{submission.code};"Ada')
    assert list(csv.reader(io.StringIO(semicolon.decode("utf-8-sig")), delimiter=";"))[
        1
    ] == [submission.code, "Ada\nGrace; Hopper"]


@pytest.mark.parametrize(
    ("event_locale", "export_locale"),
    (("en", "de"), ("de", "fr")),
    ids=("export_locale", "unknown_locale_falls_back_to_event"),
)
def test_export_csv_headers_follow_locale(event_locale, export_locale):
    event = EventFactory(locales=["en", "de"], locale=event_locale)
    user = make_orga_user(event, can_change_submissions=True)
    SubmissionFactory(event=event)

    content = _render(
        event,
        user,
        _config(columns=["title"], serializer_options={"locale": export_locale}),
    )

    assert _csv_rows(content)[0] == ["ID", "Titel"]


@pytest.mark.parametrize(
    ("config", "column", "structured"),
    (
        (
            {"table": "TrackTable", "columns": ["name"], "serializer": "json"},
            "name",
            {"en": "Science", "de": "Wissenschaft"},
        ),
        (
            _config(columns=["submission_type"], serializer="json"),
            "submission_type",
            {"en": "Talk", "de": "Vortrag"},
        ),
    ),
    ids=("track_name", "submission_type"),
)
@pytest.mark.parametrize(
    ("locales", "locale", "flat"),
    (
        (["en", "de"], ALL_LOCALES, None),
        (["en", "de"], None, None),
        (["de"], None, None),
        (["en", "de"], "de", "de"),
        (["en", "de"], "fr", "en"),
    ),
    ids=(
        "all_languages",
        "missing_key_stays_structured",
        "single_language_event",
        "chosen_language",
        "unknown_language_falls_back_to_event",
    ),
)
def test_export_json_i18n_values(config, column, structured, locales, locale, flat):
    event = EventFactory(locales=locales, locale=locales[0])
    user = make_orga_user(event, can_change_submissions=True)
    TrackFactory(event=event, name={"en": "Science", "de": "Wissenschaft"})
    submission_type = SubmissionTypeFactory(
        event=event, name={"en": "Talk", "de": "Vortrag"}, default_duration=30
    )
    SubmissionFactory(event=event, submission_type=submission_type)
    options = {} if locale is None else {"locale": locale}

    export = json.loads(_render(event, user, {**config, "serializer_options": options}))

    assert export[0][column] == (structured[flat] if flat else structured)


@pytest.mark.parametrize("item_count", (1, 3))
@pytest.mark.parametrize(
    ("columns", "query_count"),
    ((["title"], 8), (["title", "room", "start", "start_date", "start_time"], 10)),
    ids=("without_slot_columns", "with_slot_columns"),
)
def test_export_slot_columns_need_no_query_per_row(
    event, item_count, columns, query_count, django_assert_num_queries
):
    user = make_orga_user(event, can_change_submissions=True)
    room = RoomFactory(event=event, name="Aula")
    slots = [
        TalkSlotFactory(submission=submission, room=room, is_visible=True)
        for submission in SubmissionFactory.create_batch(
            item_count, event=event, state=SubmissionStates.CONFIRMED
        )
    ]
    freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
    unscheduled = SubmissionFactory(event=event)
    event = refresh(event)
    config = _config(columns=columns, serializer="json")

    with django_assert_num_queries(query_count):
        data = json.loads(_render(event, user, config))

    by_code = {row["ID"]: row for row in data}
    assert len(by_code) == item_count + 1
    unscheduled_row = by_code.pop(unscheduled.code)
    assert all(unscheduled_row[column] is None for column in columns[1:])
    for slot in slots:
        row = by_code[slot.submission.code]
        start = slot.local_start
        assert row.get("room") == ("Aula" if "room" in columns else None)
        assert row.get("start") == (start.isoformat() if "start" in columns else None)
        assert row.get("start_date") == (
            start.date().isoformat() if "start_date" in columns else None
        )
        assert row.get("start_time") == (
            start.time().isoformat() if "start_time" in columns else None
        )


@pytest.mark.parametrize("item_count", (1, 3))
def test_export_speaker_submission_columns_need_no_query_per_row(
    event, item_count, django_assert_num_queries
):
    user = make_orga_user(event, can_change_submissions=True)
    for speaker in SpeakerFactory.create_batch(item_count, event=event):
        for submission in SubmissionFactory.create_batch(2, event=event):
            submission.speakers.add(speaker)
    config = _config(
        table="SpeakerTable",
        columns=["name", "submission_ids", "submission_titles"],
        serializer="json",
    )

    with django_assert_num_queries(6):
        data = json.loads(_render(event, user, config))

    assert len(data) == item_count
    assert all(len(row["submission_ids"]) == 2 for row in data)


@pytest.mark.parametrize(
    ("config", "message"),
    (
        (_config(table="NoSuchTable"), "unknown table"),
        (_config(serializer="pdf"), "unknown format"),
        (_config(table="OutboxMailTable"), "permission denied"),
    ),
)
def test_export_rejects_bad_configuration(event, config, message):
    user = make_orga_user(event, is_reviewer=True, can_change_submissions=False)

    with pytest.raises(ExportError, match=message):
        _render(event, user, config)


@pytest.mark.parametrize(
    ("serializer_class", "value", "expected"),
    (
        (CSVSerializer, dt.date(2024, 6, 15), "2024-06-15"),
        (CSVSerializer, dt.time(16, 30), "16:30:00"),
        (CSVSerializer, None, ""),
        (CSVSerializer, True, "Yes"),
        (CSVSerializer, dt.datetime(2024, 6, 15, 14, 30), "2024-06-15T14:30:00"),  # noqa: DTZ001 -- naive on purpose
        (JSONSerializer, dt.date(2024, 6, 15), "2024-06-15"),
        (JSONSerializer, dt.time(16, 30), "16:30:00"),
        (
            JSONSerializer,
            dt.datetime(2024, 6, 15, 14, 30, tzinfo=ZoneInfo("Europe/Berlin")),
            "2024-06-15T12:30:00+00:00",
        ),
        (JSONSerializer, ZoneInfo("UTC"), "UTC"),
    ),
    ids=(
        "csv_date",
        "csv_time",
        "csv_none",
        "csv_bool",
        "csv_naive_datetime",
        "json_date",
        "json_time",
        "json_aware_datetime",
        "json_fallback_str",
    ),
)
def test_serializer_format_value(event, serializer_class, value, expected):
    serializer = serializer_class(event)

    assert serializer.format_value(value) == expected


@pytest.mark.parametrize("serializer_class", (CSVSerializer, JSONSerializer))
def test_serializer_render_keeps_file_open_when_writing_fails(event, serializer_class):
    class FailingTable:
        def as_values(self):
            yield ["a"]
            yield ["x"]
            yield ["y"]

        def export_column_names(self):
            return ["a"]

    class FailingSerializer(serializer_class):
        def format_value(self, value):
            if value == "y":
                raise ValueError("boom")
            return super().format_value(value)

    file = io.BytesIO()

    with pytest.raises(ValueError, match="boom"):
        FailingSerializer(event).export(FailingTable(), file)

    assert not file.closed
    assert file.getvalue()


def test_xlsx_render_writes_value_types():
    event = EventFactory()

    class Table:
        export_name = None

        def as_values(self):
            yield [
                "date",
                "time",
                "decimal",
                "float",
                "empty first, datetime later",
                "nan",
                "zone",
                "list",
                "formula, then a value wider than the width cap",
                "url",
            ]
            yield [
                dt.date(2024, 6, 15),
                dt.time(16, 30),
                Decimal("1.5"),
                2.25,
                None,
                float("nan"),
                ZoneInfo("UTC"),
                [dt.date(2024, 6, 15), None, True],
                '=HYPERLINK("https://evil.example","x")',
                "https://pretalx.com/",
            ]
            yield (
                [None] * 4
                + [
                    dt.datetime(2024, 6, 15, 16, 30, tzinfo=ZoneInfo("Europe/Berlin")),
                    False,
                ]
                + [None] * 2
                + ["x" * 200, "https://pretalx.com/ and more"]
            )
            yield [
                None,
                None,
                dt.date(1899, 12, 31),
                dt.datetime(1899, 12, 31, 23),  # noqa: DTZ001 -- naive on purpose
                None,
                None,
                "file:///etc/passwd",
                None,
                None,
                "https://pretalx.com/" + "x" * 2100,
            ]

    class HeaderOnlyTable:
        export_name = None

        def as_values(self):
            yield ["ID", "Title"]

    file = io.BytesIO()
    comma_file = io.BytesIO()
    with pytest.warns(UserWarning, match="exceeds Excel's limit for URLs"):
        XLSXSerializer(event).export(Table(), file)
    with pytest.warns(UserWarning, match="exceeds Excel's limit for URLs"):
        XLSXSerializer(event, options={"list_delimiter": "comma"}).export(
            Table(), comma_file
        )

    header_only_file = io.BytesIO()
    XLSXSerializer(event).export(HeaderOnlyTable(), header_only_file)

    sheet_name, sheet, cells = _xlsx_cells(file.getvalue())
    _name, _sheet, comma_cells = _xlsx_cells(comma_file.getvalue())
    _name, header_only_sheet, header_only_cells = _xlsx_cells(
        header_only_file.getvalue()
    )

    assert not file.closed
    assert {
        (col.get("min"), col.get("max")): col.get("width")
        for col in sheet.iterfind("m:cols/m:col", XLSX_NS)
    } == {
        ("1", "1"): "10.42578125",
        ("3", "3"): "10.42578125",
        ("4", "4"): "18.5703125",
        ("5", "5"): "26.7109375",
        ("7", "7"): "17.28515625",
        ("8", "8"): "10.42578125",
        ("9", "10"): "71.42578125",
    }
    assert sheet_name == "Sheet1"
    assert sheet.find("m:autoFilter", XLSX_NS).get("ref") == "A1:J4"
    assert [
        link.get("ref") for link in sheet.iterfind("m:hyperlinks/m:hyperlink", XLSX_NS)
    ] == ["J2"]
    assert cells["J4"]["value"].startswith("https://pretalx.com/xxx")
    assert sheet.find("m:ignoredErrors/m:ignoredError", XLSX_NS).attrib == {
        "sqref": "A1:XFD1048576",
        "numberStoredAsText": "1",
    }
    assert sheet.find("m:sheetPr/m:pageSetUpPr", XLSX_NS).get("fitToPage") == "1"
    assert sheet.find("m:pageSetup", XLSX_NS).attrib == {
        "fitToHeight": "0",
        "orientation": "landscape",
    }
    with zipfile.ZipFile(file) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        styles = ET.fromstring(archive.read("xl/styles.xml"))
    assert workbook.findtext(
        "m:definedNames/m:definedName[@name='_xlnm.Print_Titles']", namespaces=XLSX_NS
    ) == ("Sheet1!$1:$1")
    xfs = styles.findall("m:cellXfs/m:xf", XLSX_NS)
    assert {
        cell.get("r"): xfs[int(cell.get("s", 0))].find(
            "m:alignment[@vertical='top']", XLSX_NS
        )
        is not None
        for cell in sheet.iterfind("m:sheetData/m:row/m:c", XLSX_NS)
    } == dict.fromkeys(cells, True)
    checkbox_style = sheet.find("m:sheetData/m:row/m:c[@r='F3']", XLSX_NS).get("s")
    assert (
        styles.findall("m:cellXfs/m:xf", XLSX_NS)[int(checkbox_style)].find(
            "m:extLst", XLSX_NS
        )
        is not None
    )
    assert header_only_sheet.find("m:autoFilter", XLSX_NS).get("ref") == "A1:B1"
    assert list(header_only_cells) == ["A1", "B1"]
    assert cells["A2"]["value"] == "45458"
    assert cells["A2"]["format"] == "yyyy-mm-dd"
    assert float(cells["B2"]["value"]) == pytest.approx(16.5 / 24)
    assert cells["B2"]["format"] == "hh:mm"
    assert cells["C2"]["value"] == "1.5"
    assert cells["D2"]["value"] == "2.25"
    assert "E2" not in cells
    assert cells["F2"]["value"] == "#NUM!"
    assert cells["G2"]["value"] == "UTC"
    assert float(cells["E3"]["value"]) == pytest.approx(45458 + 14.5 / 24)
    assert cells["F3"]["value"] == "0"
    assert cells["F3"]["type"] == "b"
    assert cells["H2"]["value"] == "2024-06-15\n\nYes"
    assert cells["H2"]["wrap"] is True
    assert comma_cells["H2"] == {
        "value": "2024-06-15, , Yes",
        "type": "inlineStr",
        "format": None,
        "bold": False,
        "wrap": False,
    }
    assert cells["C4"] == {
        "value": "1899-12-31",
        "type": "inlineStr",
        "format": None,
        "bold": False,
        "wrap": False,
    }
    assert cells["D4"]["value"] == "1899-12-31T23:00:00"
    assert cells["D4"]["type"] == "inlineStr"
    assert cells["D4"]["format"] is None
    assert cells["I2"] == {
        "value": '=HYPERLINK("https://evil.example","x")',
        "type": "inlineStr",
        "format": None,
        "bold": False,
        "wrap": False,
    }


@pytest.mark.parametrize(
    ("name", "expected"),
    (
        ("Sessions", "Sessions"),
        ("Custom fields [Reviews]: a/b\\c?*", "Custom fields Reviews abc"),
        ("x" * 40, "x" * 31),
        ("\U0001f600" * 20, "\U0001f600" * 15),
        ("'quoted'", "quoted"),
        ("History", None),
        ("[]", None),
        (None, None),
    ),
)
def test_xlsx_sheet_name(name, expected):
    assert XLSXSerializer.sheet_name(name) == expected
