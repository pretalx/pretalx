# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

import pytest

from pretalx.common.models.exports import TableExport
from pretalx.common.receivers import (
    _option_map,
    copy_table_exports,
    remap_columns,
    remap_filters,
)
from pretalx.event.domain.event import copy_event_data
from tests.factories import (
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    ReviewScoreCategoryFactory,
    SubmissionTypeFactory,
    TableExportFactory,
    TagFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


class _Obj:
    def __init__(self, pk):
        self.pk = pk


def test_remap_filters_remaps_known_references_and_drops_unmapped_values():
    filters = {
        "track": ["1", "2", "9"],
        "submission_type": ["5"],
        "tags": ["3", "4"],
        "question_7": ["12", "11", "__answered__", "free"],
        "question_6": ["11", "42"],
        "question_8": ["1"],
        "state": ["accepted"],
        "content_locale": ["de"],
        "q": ["needle"],
    }

    result = remap_filters(
        filters,
        track_map={1: _Obj(10), 2: _Obj(20)},
        submission_type_map={5: _Obj(50)},
        tag_map={3: _Obj(30)},
        question_map={6: _Obj(60), 7: _Obj(70)},
        option_map={6: {}, 7: {11: _Obj(110)}},
    )

    assert result == {
        "track": ["10", "20"],
        "submission_type": ["50"],
        "tags": ["30"],
        "question_70": ["110", "__answered__", "free"],
        "question_60": ["11", "42"],
        "state": ["accepted"],
        "content_locale": ["de"],
        "q": ["needle"],
    }


def test_remap_columns_keeps_direction_and_drops_unmapped_references():
    result = remap_columns(
        [
            "title",
            "-question_7",
            "question_8",
            "score_1",
            "-independent_score_1",
            "independent_score_2",
            "-created",
        ],
        {7: _Obj(70)},
        {1: _Obj(100)},
    )

    assert result == [
        "title",
        "-question_70",
        "score_100",
        "-independent_score_100",
        "-created",
    ]


def test_copy_event_data_copies_table_exports_with_remapped_references():
    source = EventFactory(date_from=dt.date(2024, 1, 1))
    track = TrackFactory(event=source)
    tag = TagFactory(event=source, tag="Sponsored")
    submission_type = SubmissionTypeFactory(event=source)
    question = QuestionFactory(event=source, target="submission", variant="choices")
    option = AnswerOptionFactory(question=question, answer="Vegan")
    number_question = QuestionFactory(
        event=source, target="submission", variant="number"
    )
    TableExportFactory(
        event=source,
        name="Vegans on track",
        columns=["title", f"question_{question.pk}"],
        ordering=[f"-question_{question.pk}"],
        filters={
            "track": [str(track.pk)],
            "submission_type": [str(submission_type.pk)],
            f"question_{question.pk}": [str(option.pk)],
            f"question_{number_question.pk}": [str(option.pk)],
            "tags": [str(tag.pk)],
            "state": ["accepted"],
        },
    )
    TableExportFactory(event=source, name="Stale tag", filters={"tags": ["999999"]})
    quality = ReviewScoreCategoryFactory(event=source, name="Quality")
    fit = ReviewScoreCategoryFactory(event=source, name="Fit")
    TableExportFactory(
        event=source,
        name="Review scores",
        table="ReviewExportTable",
        columns=["submission_code", f"score_{quality.pk}", f"score_{fit.pk}"],
        ordering=[f"-score_{quality.pk}"],
    )
    target = EventFactory(date_from=dt.date(2025, 1, 1))

    copy_event_data(target, source)

    copied = TableExport.objects.get(event=target, name="Vegans on track")
    scores = TableExport.objects.get(event=target, name="Review scores")
    assert TableExport.objects.get(event=target, name="Stale tag").filters == {}
    new_track = target.tracks.get()
    new_tag = target.tags.get()
    new_type = target.submission_types.get(name=submission_type.name)
    new_question = target.questions.get(question=question.question)
    new_number_question = target.questions.get(question=number_question.question)
    new_option = new_question.options.get()
    new_quality = target.score_categories.get(name="Quality")
    new_fit = target.score_categories.get(name="Fit")
    assert copied.name == "Vegans on track"
    assert copied.columns == ["title", f"question_{new_question.pk}"]
    assert copied.ordering == [f"-question_{new_question.pk}"]
    assert new_tag.pk != tag.pk
    assert copied.filters == {
        "track": [str(new_track.pk)],
        "submission_type": [str(new_type.pk)],
        f"question_{new_question.pk}": [str(new_option.pk)],
        f"question_{new_number_question.pk}": [str(option.pk)],
        "tags": [str(new_tag.pk)],
        "state": ["accepted"],
    }
    assert new_quality.pk != quality.pk
    assert scores.columns == [
        "submission_code",
        f"score_{new_quality.pk}",
        f"score_{new_fit.pk}",
    ]
    assert scores.ordering == [f"-score_{new_quality.pk}"]
    assert TableExport.objects.filter(event=source).count() == 3


def test_option_map_pairs_options_by_identifier():
    source = QuestionFactory(target="submission", variant="choices")
    target = QuestionFactory(target="submission", variant="choices")
    old_a = AnswerOptionFactory(question=source, answer="A", identifier="a")
    old_b = AnswerOptionFactory(question=source, answer="B", identifier="b")
    AnswerOptionFactory(question=source, answer="Gone", identifier="gone")
    new_b = AnswerOptionFactory(question=target, answer="B", identifier="b")
    new_a = AnswerOptionFactory(question=target, answer="A", identifier="a")

    assert _option_map({source.pk: target, 999999: _Obj(1)}) == {
        source.pk: {old_a.pk: new_a, old_b.pk: new_b}
    }


def test_copy_table_exports_ignores_unknown_source(event):
    copy_table_exports(
        sender=event,
        other="no-such-event",
        question_map={},
        track_map={},
        submission_type_map={},
        tag_map={},
        score_category_map={},
    )

    assert TableExport.objects.filter(event=event).count() == 0
