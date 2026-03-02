# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now
from django_scopes import scope

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

pytestmark = pytest.mark.unit


def _make_event(*, is_public=True, from_delta, to_delta, cfp_deadline=None):
    """Create an event via factory with delta-based dates."""
    _now = now()
    kwargs = {
        "is_public": is_public,
        "date_from": (_now + dt.timedelta(days=from_delta)).date(),
        "date_to": (_now + dt.timedelta(days=to_delta)).date(),
    }
    if cfp_deadline is not None:
        kwargs["cfp__deadline"] = cfp_deadline
    return EventFactory(**kwargs)


@pytest.mark.django_db
def test_is_in_preparation_when_not_public_and_before_start():
    event = _make_event(is_public=False, from_delta=5, to_delta=7)

    assert _is_in_preparation(event) is True


@pytest.mark.django_db
def test_is_in_preparation_false_when_public():
    event = _make_event(is_public=True, from_delta=5, to_delta=7)

    assert _is_in_preparation(event) is False


@pytest.mark.django_db
def test_is_in_preparation_false_when_past_start():
    event = _make_event(is_public=False, from_delta=-1, to_delta=1)

    assert _is_in_preparation(event) is False


@pytest.mark.django_db
def test_is_cfp_open_when_public_and_deadline_not_passed():
    event = _make_event(
        is_public=True,
        from_delta=5,
        to_delta=7,
        cfp_deadline=now() + dt.timedelta(days=3),
    )
    with scope(event=event):
        assert _is_cfp_open(event) is True


@pytest.mark.django_db
def test_is_cfp_open_false_when_in_preparation():
    event = _make_event(
        is_public=False,
        from_delta=5,
        to_delta=7,
        cfp_deadline=now() + dt.timedelta(days=3),
    )
    with scope(event=event):
        assert _is_cfp_open(event) is False


@pytest.mark.django_db
def test_is_cfp_open_false_when_deadline_passed():
    event = _make_event(
        is_public=True,
        from_delta=5,
        to_delta=7,
        cfp_deadline=now() - dt.timedelta(days=1),
    )
    with scope(event=event):
        assert _is_cfp_open(event) is False


@pytest.mark.django_db
def test_is_in_review_with_submitted_proposals():
    event = _make_event(
        is_public=True,
        from_delta=5,
        to_delta=7,
        cfp_deadline=now() - dt.timedelta(days=1),
    )
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        assert _is_in_review(event) is True


@pytest.mark.django_db
def test_is_in_review_false_without_submitted_proposals():
    event = _make_event(
        is_public=True,
        from_delta=5,
        to_delta=7,
        cfp_deadline=now() - dt.timedelta(days=1),
    )

    with scope(event=event):
        assert _is_in_review(event) is False


@pytest.mark.django_db
def test_is_in_review_false_when_cfp_still_open():
    event = _make_event(
        is_public=True,
        from_delta=5,
        to_delta=7,
        cfp_deadline=now() + dt.timedelta(days=1),
    )
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        assert _is_in_review(event) is False


@pytest.mark.django_db
def test_is_running_during_event_dates():
    event = _make_event(from_delta=-1, to_delta=1)

    assert _is_running(event) is True


@pytest.mark.django_db
def test_is_running_false_before_event():
    event = _make_event(from_delta=1, to_delta=3)

    assert _is_running(event) is False


@pytest.mark.django_db
def test_is_running_on_boundary_day():
    """The event start day and end day both count as 'running'."""
    event = _make_event(from_delta=0, to_delta=0)

    assert _is_running(event) is True


@pytest.mark.django_db
def test_is_in_wrapup_after_event_ends():
    event = _make_event(from_delta=-3, to_delta=-1)

    assert _is_in_wrapup(event) is True


@pytest.mark.django_db
def test_is_in_wrapup_false_during_event():
    event = _make_event(from_delta=-1, to_delta=1)

    assert _is_in_wrapup(event) is False


@pytest.mark.django_db
def test_is_in_scheduling_stage_after_review_before_event():
    event = _make_event(
        is_public=True,
        from_delta=5,
        to_delta=7,
        cfp_deadline=now() - dt.timedelta(days=1),
    )
    with scope(event=event):
        assert _is_in_scheduling_stage(event) is True


@pytest.mark.django_db
def test_is_in_scheduling_stage_false_when_running():
    event = _make_event(is_public=True, from_delta=-1, to_delta=1)

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
    target, is_public, from_delta, to_delta, deadline_delta, has_submissions
):
    _now = now()
    event = _make_event(
        is_public=is_public,
        from_delta=from_delta,
        to_delta=to_delta,
        cfp_deadline=_now + dt.timedelta(days=deadline_delta),
    )
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
def test_get_stages_marks_current_stage():
    event = _make_event(
        is_public=True,
        from_delta=5,
        to_delta=7,
        cfp_deadline=now() + dt.timedelta(days=3),
    )

    with scope(event=event):
        stages = get_stages(event)

    assert stages["CFP_OPEN"]["phase"] == "current"
    assert stages["PREPARATION"]["phase"] == "done"
    assert stages["REVIEW"]["phase"] == "todo"
    assert stages["SCHEDULE"]["phase"] == "todo"


@pytest.mark.django_db
def test_get_stages_resolves_link_urls():
    event = _make_event(is_public=False, from_delta=5, to_delta=7)

    with scope(event=event):
        stages = get_stages(event)

    preparation = stages["PREPARATION"]
    assert all("url" in link for link in preparation["links"])
    for link in preparation["links"]:
        assert isinstance(link["url"], str), "URL should be resolved to a string"


@pytest.mark.django_db
def test_get_stages_links_without_url_are_preserved():
    event = _make_event(is_public=True, from_delta=-1, to_delta=1)

    with scope(event=event):
        stages = get_stages(event)

    event_links = stages["EVENT"]["links"]
    assert any("url" not in link for link in event_links)


@pytest.mark.django_db
def test_get_stages_does_not_mutate_original():
    event = _make_event(from_delta=5, to_delta=7)

    with scope(event=event):
        stages = get_stages(event)

    assert "phase" not in STAGES["PREPARATION"]
    assert "phase" in stages["PREPARATION"]
