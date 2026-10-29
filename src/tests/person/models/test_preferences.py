# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.db.utils import IntegrityError

from tests.factories import UserEventPreferencesFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("preferences", "path", "expected"),
    (
        ({"color": "blue"}, "color", "blue"),
        (
            {"tables": {"SubmissionTable": {"columns": ["title", "state"]}}},
            "tables.SubmissionTable.columns",
            ["title", "state"],
        ),
        ({}, "missing", None),
        ({"tables": {}}, "tables.SubmissionTable.columns", None),
        ({"tables": "flat_value"}, "tables.SubmissionTable", None),
    ),
    ids=[
        "simple_key",
        "nested_key",
        "missing_key",
        "missing_nested_key",
        "intermediate_leaf_node",
    ],
)
def test_preferences_get(preferences, path, expected):
    prefs = UserEventPreferencesFactory(preferences=preferences)
    assert prefs.get(path) == expected


@pytest.mark.parametrize(
    ("initial", "path", "value", "expected_at_path"),
    (
        ({}, "color", "red", "red"),
        ({}, "tables.SubmissionTable.columns", ["title"], ["title"]),
        ({"color": "blue"}, "color", "red", "red"),
        (
            {"tables": {"old_key": "old_value"}},
            "tables",
            {"new_key": "new_value"},
            {"new_key": "new_value"},
        ),
        (
            {"tables": "old_value"},
            "tables",
            {"new_key": "new_value"},
            {"new_key": "new_value"},
        ),
    ),
    ids=[
        "simple_key",
        "nested_creates_intermediate",
        "overwrites_leaf",
        "dict_overwrites_dict",
        "leaf_to_dict",
    ],
)
def test_preferences_set(initial, path, value, expected_at_path):
    prefs = UserEventPreferencesFactory(preferences=initial)
    prefs.set(path, value)
    assert prefs.get(path) == expected_at_path


@pytest.mark.parametrize(
    ("initial", "path", "value"),
    (
        ({"tables": {"SubmissionTable": {}}}, "tables", "flat_value"),
        ({"tables": "flat_value"}, "tables.SubmissionTable.columns", ["title"]),
    ),
    ids=["dict_with_non_dict", "intermediate_leaf"],
)
def test_preferences_set_raises_on_type_conflict(initial, path, value):
    prefs = UserEventPreferencesFactory(preferences=initial)
    with pytest.raises(TypeError):
        prefs.set(path, value)


@pytest.mark.parametrize(
    ("commit", "expected"), ((True, {"color": "green"}), (False, {}))
)
def test_preferences_set_commit_controls_persistence(event, commit, expected):
    prefs = UserEventPreferencesFactory(event=event, preferences={})
    prefs.set("color", "green", commit=commit)

    prefs.refresh_from_db()
    assert prefs.preferences == expected


@pytest.mark.parametrize(
    ("initial", "path", "expected_remaining"),
    (
        ({"color": "blue", "size": "large"}, "color", {"size": "large"}),
        (
            {"tables": {"col1": "a", "col2": "b"}},
            "tables.col1",
            {"tables": {"col2": "b"}},
        ),
        ({"tables": {"SubmissionTable": {"columns": ["title"]}}}, "tables", {}),
        ({"color": "blue"}, "nonexistent", {"color": "blue"}),
        ({}, "a.b.c", {}),
    ),
    ids=[
        "existing_key",
        "nested_key",
        "branch",
        "missing_key_silent",
        "missing_nested_key_silent",
    ],
)
def test_preferences_clear(initial, path, expected_remaining):
    prefs = UserEventPreferencesFactory(preferences=initial)
    prefs.clear(path)
    assert prefs.preferences == expected_remaining


@pytest.mark.parametrize(
    ("commit", "expected"), ((True, {}), (False, {"color": "blue"}))
)
def test_preferences_clear_commit_controls_persistence(event, commit, expected):
    prefs = UserEventPreferencesFactory(event=event, preferences={"color": "blue"})
    prefs.clear("color", commit=commit)

    prefs.refresh_from_db()
    assert prefs.preferences == expected


def test_preferences_unique_constraint():
    prefs = UserEventPreferencesFactory()
    with pytest.raises(IntegrityError):
        UserEventPreferencesFactory(user=prefs.user, event=prefs.event)
