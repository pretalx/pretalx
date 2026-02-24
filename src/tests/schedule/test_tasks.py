import pytest

from pretalx.event.models import Event
from pretalx.schedule.services import has_unreleased_schedule_changes
from pretalx.schedule.tasks import task_update_unreleased_schedule_changes

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(("value", "expected"), ((None, False), (True, True)))
@pytest.mark.usefixtures("locmem_cache")
@pytest.mark.django_db
def test_task_update_unreleased_schedule_changes_sets_cache(event, value, expected):
    """The celery task resolves the event slug, calls the service function,
    and stores the correct value in the event cache."""
    task_update_unreleased_schedule_changes(event=event.slug, value=value)

    assert has_unreleased_schedule_changes(event) == expected


@pytest.mark.django_db
def test_task_update_unreleased_schedule_changes_nonexistent_event():
    with pytest.raises(Event.DoesNotExist):
        task_update_unreleased_schedule_changes(event="nonexistent-slug")
