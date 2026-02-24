import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.schedule.utils import guess_schedule_version
from tests.factories import EventFactory, ScheduleFactory

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("previous_version", "expected"),
    (
        (None, "0.1"),
        ("0.1", "0.2"),
        ("0,2", "0,3"),
        ("0-3", "0-4"),
        ("0_4", "0_5"),
        ("1.0.1", "1.0.2"),
        ("something.1", "something.2"),
        ("Nichtnumerisch", ""),
        ("1.something", ""),
    ),
)
@pytest.mark.django_db
def test_guess_schedule_version(previous_version, expected):
    with scopes_disabled():
        event = EventFactory()
        if previous_version:
            ScheduleFactory(event=event, version=previous_version, published=now())
        assert guess_schedule_version(event) == expected
