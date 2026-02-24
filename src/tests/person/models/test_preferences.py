import pytest
from django.db.utils import IntegrityError

from tests.factories import UserEventPreferencesFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_preferences_str(event):
    prefs = UserEventPreferencesFactory(event=event)
    assert str(prefs) == f"Preferences for {prefs.user} and {prefs.event}"


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
@pytest.mark.django_db
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
@pytest.mark.django_db
def test_preferences_set(initial, path, value, expected_at_path):
    prefs = UserEventPreferencesFactory(preferences=initial)
    prefs.set(path, value)
    assert prefs.get(path) == expected_at_path


@pytest.mark.django_db
def test_preferences_set_raises_on_overwrite_dict_with_non_dict():
    """Cannot overwrite a branch node with a scalar value."""
    prefs = UserEventPreferencesFactory(preferences={"tables": {"SubmissionTable": {}}})
    with pytest.raises(TypeError):
        prefs.set("tables", "flat_value")


@pytest.mark.django_db
def test_preferences_set_raises_on_intermediate_leaf():
    """Cannot create keys under an existing leaf node."""
    prefs = UserEventPreferencesFactory(preferences={"tables": "flat_value"})
    with pytest.raises(TypeError):
        prefs.set("tables.SubmissionTable.columns", ["title"])


@pytest.mark.django_db
def test_preferences_set_with_commit(event):
    prefs = UserEventPreferencesFactory(event=event, preferences={})
    prefs.set("color", "green", commit=True)

    prefs.refresh_from_db()
    assert prefs.preferences["color"] == "green"


@pytest.mark.django_db
def test_preferences_set_without_commit_does_not_persist(event):
    prefs = UserEventPreferencesFactory(event=event, preferences={})
    prefs.set("color", "green", commit=False)

    prefs.refresh_from_db()
    assert prefs.preferences == {}


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
@pytest.mark.django_db
def test_preferences_clear(initial, path, expected_remaining):
    prefs = UserEventPreferencesFactory(preferences=initial)
    prefs.clear(path)
    assert prefs.preferences == expected_remaining


@pytest.mark.django_db
def test_preferences_clear_with_commit(event):
    prefs = UserEventPreferencesFactory(event=event, preferences={"color": "blue"})
    prefs.clear("color", commit=True)

    prefs.refresh_from_db()
    assert "color" not in prefs.preferences


@pytest.mark.django_db
def test_preferences_clear_without_commit_does_not_persist(event):
    prefs = UserEventPreferencesFactory(event=event, preferences={"color": "blue"})
    prefs.clear("color", commit=False)

    prefs.refresh_from_db()
    assert prefs.preferences["color"] == "blue"


@pytest.mark.django_db
def test_preferences_unique_constraint():
    """Only one preference per user/event pair."""
    prefs = UserEventPreferencesFactory()
    with pytest.raises(IntegrityError):
        UserEventPreferencesFactory(user=prefs.user, event=prefs.event)
