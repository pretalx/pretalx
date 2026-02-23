import datetime as dt

import pytest
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.event.stages import (
    STAGE_ORDER,
    STAGES,
    _is_cfp_open,
    _is_in_preparation,
    _is_in_review,
    _is_in_scheduling_stage,
    _is_in_wrapup,
    _is_running,
    build_event_url,
    get_stages,
    in_stage,
)
from pretalx.submission.models import SubmissionStates
from tests.factories import EventFactory, SubmissionFactory
from tests.utils import refresh

pytestmark = pytest.mark.unit


def _update_event(event, *, is_public=None, from_delta, to_delta):
    """Build kwargs from deltas and delegate to refresh()."""
    _now = now()
    updates = {
        "date_from": (_now + dt.timedelta(days=from_delta)).date(),
        "date_to": (_now + dt.timedelta(days=to_delta)).date(),
    }
    if is_public is not None:
        updates["is_public"] = is_public
    return refresh(event, **updates)


@pytest.mark.django_db
def test_is_in_preparation_when_not_public_and_before_start(event):
    """An unpublished event before its start date is in preparation."""
    event = _update_event(event, is_public=False, from_delta=5, to_delta=7)

    assert _is_in_preparation(event) is True


@pytest.mark.django_db
def test_is_in_preparation_false_when_public(event):
    """A public event is never in preparation, even if before its start date."""
    event = _update_event(event, is_public=True, from_delta=5, to_delta=7)

    assert _is_in_preparation(event) is False


@pytest.mark.django_db
def test_is_in_preparation_false_when_past_start(event):
    """An event past its start date is not in preparation, even when unpublished."""
    event = _update_event(event, is_public=False, from_delta=-1, to_delta=1)

    assert _is_in_preparation(event) is False


@pytest.mark.django_db
def test_is_cfp_open_when_public_and_deadline_not_passed(event):
    event = _update_event(event, is_public=True, from_delta=5, to_delta=7)
    with scope(event=event):
        event.cfp.deadline = now() + dt.timedelta(days=3)
        event.cfp.save()
        assert _is_cfp_open(event) is True


@pytest.mark.django_db
def test_is_cfp_open_false_when_in_preparation(event):
    """If the event is still in preparation, CfP is not considered open."""
    event = _update_event(event, is_public=False, from_delta=5, to_delta=7)
    with scope(event=event):
        event.cfp.deadline = now() + dt.timedelta(days=3)
        event.cfp.save()
        assert _is_cfp_open(event) is False


@pytest.mark.django_db
def test_is_cfp_open_false_when_deadline_passed(event):
    event = _update_event(event, is_public=True, from_delta=5, to_delta=7)
    with scope(event=event):
        event.cfp.deadline = now() - dt.timedelta(days=1)
        event.cfp.save()
        assert _is_cfp_open(event) is False


@pytest.mark.django_db
def test_is_in_review_with_submitted_proposals(event):
    """Review stage: CfP closed, submitted proposals exist, event hasn't started."""
    event = _update_event(event, is_public=True, from_delta=5, to_delta=7)
    with scope(event=event):
        event.cfp.deadline = now() - dt.timedelta(days=1)
        event.cfp.save()
    with scopes_disabled():
        SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        assert _is_in_review(event) is True


@pytest.mark.django_db
def test_is_in_review_false_without_submitted_proposals(event):
    """Without submitted proposals, the event is not in review."""
    event = _update_event(event, is_public=True, from_delta=5, to_delta=7)
    with scope(event=event):
        event.cfp.deadline = now() - dt.timedelta(days=1)
        event.cfp.save()

    with scope(event=event):
        assert _is_in_review(event) is False


@pytest.mark.django_db
def test_is_in_review_false_when_cfp_still_open(event):
    """While CfP is open, the event is not in review even with submissions."""
    event = _update_event(event, is_public=True, from_delta=5, to_delta=7)
    with scope(event=event):
        event.cfp.deadline = now() + dt.timedelta(days=1)
        event.cfp.save()
    with scopes_disabled():
        SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        assert _is_in_review(event) is False


@pytest.mark.django_db
def test_is_running_during_event_dates(event):
    event = _update_event(event, from_delta=-1, to_delta=1)

    assert _is_running(event) is True


@pytest.mark.django_db
def test_is_running_false_before_event(event):
    event = _update_event(event, from_delta=1, to_delta=3)

    assert _is_running(event) is False


@pytest.mark.django_db
def test_is_running_on_boundary_day(event):
    """The event start day and end day both count as 'running'."""
    event = _update_event(event, from_delta=0, to_delta=0)

    assert _is_running(event) is True


@pytest.mark.django_db
def test_is_in_wrapup_after_event_ends(event):
    event = _update_event(event, from_delta=-3, to_delta=-1)

    assert _is_in_wrapup(event) is True


@pytest.mark.django_db
def test_is_in_wrapup_false_during_event(event):
    event = _update_event(event, from_delta=-1, to_delta=1)

    assert _is_in_wrapup(event) is False


@pytest.mark.django_db
def test_is_in_scheduling_stage_after_review_before_event(event):
    """Scheduling stage: no submitted proposals, CfP closed, event not yet started."""
    event = _update_event(event, is_public=True, from_delta=5, to_delta=7)
    with scope(event=event):
        event.cfp.deadline = now() - dt.timedelta(days=1)
        event.cfp.save()
        assert _is_in_scheduling_stage(event) is True


@pytest.mark.django_db
def test_is_in_scheduling_stage_false_when_running(event):
    event = _update_event(event, is_public=True, from_delta=-1, to_delta=1)

    with scope(event=event):
        assert _is_in_scheduling_stage(event) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    (
        "target",
        "is_public",
        "from_delta",
        "to_delta",
        "deadline_delta",
        "has_submissions",
    ),
    (
        ("PREPARATION", False, 2, 3, 1, False),
        ("PREPARATION", False, 2, 3, 1, True),
        ("CFP_OPEN", True, 2, 3, 1, False),
        ("CFP_OPEN", True, 2, 3, 1, True),
        ("REVIEW", True, 2, 3, -1, True),
        ("SCHEDULE", True, 2, 3, -1, False),
        ("EVENT", True, -2, 3, -1, False),
        ("EVENT", True, -2, 3, -1, True),
        ("EVENT", True, 0, 0, -1, False),
        ("EVENT", True, 0, 0, -1, True),
        ("WRAPUP", True, -2, -1, -1, True),
        ("WRAPUP", True, -2, -1, -1, False),
    ),
)
def test_in_stage_returns_correct_stage(
    event, target, is_public, from_delta, to_delta, deadline_delta, has_submissions
):
    """Each parametrized combination of dates/settings maps to exactly one stage."""
    _now = now()
    event.is_public = is_public
    event.date_from = (_now + dt.timedelta(days=from_delta)).date()
    event.date_to = (_now + dt.timedelta(days=to_delta)).date()
    event.save()
    with scope(event=event):
        event.cfp.deadline = _now + dt.timedelta(days=deadline_delta)
        event.cfp.save()
    with scopes_disabled():
        event = refresh(event)
        if has_submissions:
            SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        for stage in STAGE_ORDER:
            assert in_stage(event, stage) == (stage == target), (
                f"Expected {target} but in_stage returned "
                f"{'True' if stage != target else 'False'} for {stage}"
            )
            if stage == target and target != "WRAPUP":
                break


def test_stage_order_has_six_stages():
    assert len(STAGE_ORDER) == 6


def test_stage_order_matches_stages_keys():
    assert set(STAGE_ORDER) == set(STAGES.keys())


def test_all_stages_have_required_keys():
    for stage_name, stage in STAGES.items():
        assert "name" in stage, f"{stage_name} missing 'name'"
        assert "method" in stage, f"{stage_name} missing 'method'"
        assert "icon" in stage, f"{stage_name} missing 'icon'"
        assert "links" in stage, f"{stage_name} missing 'links'"


@pytest.mark.parametrize(
    ("attrs", "expected"),
    ((["name"], "test"), (["inner", "value"], "resolved")),
    ids=("single_attribute", "chained_attributes"),
)
def test_build_event_url_resolves_attribute_chain(attrs, expected):
    class Inner:
        value = "resolved"

    class Obj:
        name = "test"
        inner = Inner()

    assert build_event_url(Obj(), attrs) == expected


@pytest.mark.django_db
def test_get_stages_marks_current_stage(event):
    """The active stage gets phase='current', earlier stages 'done',
    later stages 'todo'."""
    event = _update_event(event, is_public=True, from_delta=5, to_delta=7)
    with scope(event=event):
        event.cfp.deadline = now() + dt.timedelta(days=3)
        event.cfp.save()

        stages = get_stages(event)

    assert stages["CFP_OPEN"]["phase"] == "current"
    assert stages["PREPARATION"]["phase"] == "done"
    assert stages["REVIEW"]["phase"] == "todo"
    assert stages["SCHEDULE"]["phase"] == "todo"


@pytest.mark.django_db
def test_get_stages_resolves_link_urls(event):
    """All PREPARATION links have url keys that get resolved to strings."""
    event = _update_event(event, is_public=False, from_delta=5, to_delta=7)

    with scope(event=event):
        stages = get_stages(event)

    preparation = stages["PREPARATION"]
    assert all("url" in link for link in preparation["links"])
    for link in preparation["links"]:
        assert isinstance(link["url"], str), "URL should be resolved to a string"


@pytest.mark.django_db
def test_get_stages_links_without_url_are_preserved(event):
    """Links without a url key (informational items) are kept as-is."""
    event = _update_event(event, is_public=True, from_delta=-1, to_delta=1)

    with scope(event=event):
        stages = get_stages(event)

    event_links = stages["EVENT"]["links"]
    assert any("url" not in link for link in event_links)


@pytest.mark.django_db
def test_get_stages_does_not_mutate_original():
    """get_stages() deep-copies STAGES, so the module-level dict is not modified."""
    with scopes_disabled():
        event = EventFactory(
            date_from=(now() + dt.timedelta(days=5)).date(),
            date_to=(now() + dt.timedelta(days=7)).date(),
        )

    with scope(event=event):
        stages = get_stages(event)

    assert "phase" not in STAGES["PREPARATION"]
    assert "phase" in stages["PREPARATION"]
