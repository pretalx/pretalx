# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import csv
import datetime as dt
import io
import json
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.core.files.base import ContentFile

from pretalx.common.signals import (
    register_exportable_tables,
    register_table_serializers,
)
from pretalx.common.tables.export import (
    CSVSerializer,
    ExportError,
    JSONSerializer,
    TableSerializer,
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
    RoomFactory,
    SpeakerFactory,
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


def test_table_serializers_offer_csv_and_json(event):
    assert get_table_serializers(event) == {
        "csv": CSVSerializer,
        "json": JSONSerializer,
    }
    assert get_table_serializer(event, "csv") is CSVSerializer
    assert get_table_serializer(event, "xlsx") is None
    assert CSVSerializer.default_options(event) == {
        "delimiter": ",",
        "list_delimiter": "newline",
    }
    assert JSONSerializer.default_options(event) == {}


@pytest.mark.parametrize(
    ("locales", "has_locale"), ((["en"], False), (["en", "de"], True))
)
def test_csv_serializer_offers_locale_only_with_several_languages(locales, has_locale):
    event = EventFactory(locales=locales, locale="en")

    fields = CSVSerializer.option_fields(event)

    assert ("locale" in fields) is has_locale
    assert list(fields) == (["locale"] if has_locale else []) + [
        "delimiter",
        "list_delimiter",
    ]
    assert CSVSerializer.default_options(event).get("locale") == (
        "en" if has_locale else None
    )
    assert "locale" not in JSONSerializer.option_fields(event)


def test_table_serializers_add_plugin_formats_without_replacing_core(
    event, register_signal_handler
):
    class XLSXSerializer(TableSerializer):
        identifier = "xlsx"

    class FakeCSVSerializer(TableSerializer):
        identifier = "csv"

    for serializer in (None, XLSXSerializer, FakeCSVSerializer):
        register_signal_handler(
            register_table_serializers,
            lambda signal, sender, serializer=serializer, **kwargs: serializer,
        )

    assert get_table_serializers(event) == {
        "csv": CSVSerializer,
        "json": JSONSerializer,
        "xlsx": XLSXSerializer,
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
    }
    FeedbackFactory(talk=SubmissionFactory(event=other))
    SubmitterAccessCodeFactory(event=other)
    TrackFactory(event=other)
    TagFactory(event=other)
    RoomFactory(event=other)
    QuestionFactory(event=other, target="speaker")
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


def test_export_review_table_with_review_count_filter(event):
    user = make_orga_user(event, can_change_submissions=True)
    reviewed = SubmissionFactory(event=event, title="Reviewed")
    ReviewFactory(submission=reviewed)
    ReviewFactory(submission=reviewed)
    SubmissionFactory(event=event, title="Bare")

    content = _render(
        event,
        user,
        _config(
            table="ReviewTable", columns=["title"], filters={"review-count": ["1,2"]}
        ),
    )

    assert [row[1] for row in _csv_rows(content)[1:]] == ["Reviewed"]


@pytest.mark.parametrize(
    ("variant", "answer_kwargs", "csv_value", "json_value"),
    (
        ("string", {"answer": "free text"}, "free text", "free text"),
        ("text", {"answer": "long\ntext"}, "long\ntext", "long\ntext"),
        ("boolean", {"answer": "True"}, "Yes", True),
        ("multiple_choice", {"options": ["one", "two"]}, "one, two", ["one", "two"]),
        ("number", {}, "", None),
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
    for name in ("Ada", "Grace; Hopper"):
        submission.speakers.add(SpeakerFactory(event=event, name=name))

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
    "locales",
    (["en", "de"], ["de"]),
    ids=("multilingual_event", "single_language_event"),
)
def test_export_json_keeps_structured_i18n(config, column, structured, locales):
    event = EventFactory(locales=locales, locale=locales[-1])
    user = make_orga_user(event, can_change_submissions=True)
    TrackFactory(event=event, name={"en": "Science", "de": "Wissenschaft"})
    submission_type = SubmissionTypeFactory(
        event=event, name={"en": "Talk", "de": "Vortrag"}, default_duration=30
    )
    SubmissionFactory(event=event, submission_type=submission_type)

    export = json.loads(
        _render(event, user, {**config, "serializer_options": {"locale": "de"}})
    )

    assert export[0][column] == structured


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
        (_config(serializer="xlsx"), "unknown format"),
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
