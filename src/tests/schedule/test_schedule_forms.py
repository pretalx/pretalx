# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest
from django.forms import ValidationError
from django.utils import timezone
from django_scopes import scope

from pretalx.common.forms.fields import AvailabilitiesField
from pretalx.schedule.models import Availability, Room

timezone.activate(ZoneInfo("UTC"))


@pytest.fixture
def availabilities_field(event):
    event.date_from = dt.date(2017, 1, 1)
    event.date_to = dt.date(2017, 1, 2)

    return AvailabilitiesField(
        event=event,
        instance=None,
        required=False,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "json,error",
    (
        ("{{{", "not valid json"),  # invalid json
        ("[]", "format"),  # not a dict
        ("42", "format"),  # not a dict
        ("{}", "format"),  # no "availabilities"
        ('{"availabilities": {}}', "format"),  # availabilities not a list
    ),
)
def test_parse_availabilities_json_fail(availabilities_field, json, error):
    with pytest.raises(ValidationError) as excinfo:
        availabilities_field._parse_availabilities_json(json)

    assert error in str(excinfo.value)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "json",
    (
        ('{"availabilities": []}'),
        ('{"availabilities": [1]}'),
    ),
)
def test_parse_availabilities_json_success(availabilities_field, json):
    availabilities_field._parse_availabilities_json(json)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "avail",
    (
        ([]),  # not a dict
        (42),  # not a dict
        ({}),  # missing attributes
        ({"start": True}),  # missing attributes
        ({"end": True}),  # missing attributes
        ({"start": True, "end": True, "foo": True}),  # extra attributes
    ),
)
def test_validate_availability_fail_format(availabilities_field, avail):
    with pytest.raises(ValidationError) as excinfo:
        availabilities_field._validate_availability(avail)

    assert "format" in str(excinfo.value)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "avail",
    (
        ({"start": True, "end": True}),  # wrong type
        ({"start": "", "end": ""}),  # empty
        ({"start": "2017", "end": "2017"}),  # missing month
    ),
)
def test_validate_availability_fail_date(availabilities_field, avail):
    with pytest.raises(ValidationError) as excinfo:
        availabilities_field._validate_availability(avail)

    assert "invalid date" in str(excinfo.value)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "avail",
    (
        ({"start": "2017-01-01 10:00:00", "end": "2017-01-01 12:00:00"}),  # same day
        ({"start": "2017-01-01 10:00:00", "end": "2017-01-02 12:00:00"}),  # next day
        (
            {"start": "2017-01-01 00:00:00", "end": "2017-01-02 00:00:00"}
        ),  # all day start
        ({"start": "2017-01-02 00:00:00", "end": "2017-01-03 00:00:00"}),  # all day end
    ),
)
def test_validate_availability_success(availabilities_field, avail):
    availabilities_field._validate_availability(avail)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "avail",
    (
        (
            {"start": "2017-01-01 00:00:00", "end": "2017-01-01 08:00:00"}
        ),  # local time, start
        (
            {"start": "2017-01-02 05:00:00", "end": "2017-01-03 00:00:00"}
        ),  # local time, end
        (
            {"start": "2017-01-01 00:00:00-05:00", "end": "2017-01-01 00:00:00-05:00"}
        ),  # explicit timezone, start
        (
            {"start": "2017-01-02 05:00:00-05:00", "end": "2017-01-03 00:00:00-05:00"}
        ),  # explicit timezone, end
        (
            {"start": "2017-01-01 05:00:00+00:00", "end": "2017-01-01 00:00:00-05:00"}
        ),  # UTC, start
        (
            {"start": "2017-01-02 05:00:00-00:00", "end": "2017-01-03 05:00:00-00:00"}
        ),  # UTC, end
    ),
)
def test_validate_availability_tz_success(availabilities_field, avail):
    availabilities_field.event.timezone = "America/New_York"
    availabilities_field.event.save()
    availabilities_field._validate_availability(avail)


@pytest.mark.django_db
def test_validate_availability_daylightsaving(availabilities_field):
    # https://github.com/pretalx/pretalx/issues/460
    availabilities_field.event.timezone = "Europe/Berlin"
    availabilities_field.event.date_from = dt.date(2018, 10, 22)
    availabilities_field.event.date_to = dt.date(2018, 10, 28)
    availabilities_field.event.save()
    availabilities_field._validate_availability(
        {"start": "2018-10-22 00:00:00", "end": "2018-10-29 00:00:00"}
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "strdate,expected",
    (
        ("2017-01-01 10:00:00", dt.datetime(2017, 1, 1, 10)),
        ("2017-01-01 10:00:00-05:00", dt.datetime(2017, 1, 1, 10)),
        ("2017-01-01 10:00:00-04:00", dt.datetime(2017, 1, 1, 9)),
    ),
)
def test_parse_datetime(availabilities_field, strdate, expected):
    availabilities_field.event.timezone = "America/New_York"
    availabilities_field.event.save()
    del availabilities_field.event.tz

    assert availabilities_field.event.tz == ZoneInfo("America/New_York")
    expected = expected.replace(tzinfo=ZoneInfo("America/New_York"))
    actual = availabilities_field._parse_datetime(strdate)
    assert actual == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    "json,error",
    (
        ("{{", "not valid json"),
        ('{"availabilities": [1]}', "format"),
    ),
)
def test_clean_availabilities_fail(availabilities_field, json, error):
    with pytest.raises(ValidationError) as excinfo:
        availabilities_field.clean(json)

    assert error in str(excinfo.value)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "json,expected",
    (
        ('{"availabilities": []}', []),
        (
            '{"availabilities": [{"start": "2017-01-01 10:00:00", "end": "2017-01-01 12:00:00"},'
            '{"start": "2017-01-02 11:00:00", "end": "2017-01-02 13:00:00"}]}',
            [
                Availability(
                    start=dt.datetime(2017, 1, 1, 10), end=dt.datetime(2017, 1, 1, 12)
                ),
                Availability(
                    start=dt.datetime(2017, 1, 2, 11), end=dt.datetime(2017, 1, 2, 13)
                ),
            ],
        ),
    ),
)
def test_clean_availabilities_success(availabilities_field, json, expected):
    actual = availabilities_field.clean(json)

    assert len(actual) == len(expected)

    for act, exp in zip(actual, expected):
        assert act.start.replace(tzinfo=None) == exp.start
        assert act.end.replace(tzinfo=None) == exp.end
        assert act.event_id == availabilities_field.event.id
        assert act.id is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "avail,expected",
    (
        (
            Availability(
                start=dt.datetime(2017, 1, 1, 10, tzinfo=ZoneInfo("UTC")),
                end=dt.datetime(2017, 1, 1, 12, tzinfo=ZoneInfo("UTC")),
            ),
            {
                "start": "2017-01-01T10:00:00+00:00",
                "end": "2017-01-01T12:00:00+00:00",
                "allDay": False,
            },
        ),
        (
            Availability(
                start=dt.datetime(2017, 1, 1, 10, tzinfo=ZoneInfo("UTC")),
                end=dt.datetime(2017, 1, 2, tzinfo=ZoneInfo("UTC")),
            ),
            {
                "start": "2017-01-01T10:00:00+00:00",
                "end": "2017-01-02T00:00:00+00:00",
                "allDay": False,
            },
        ),
        (
            Availability(
                start=dt.datetime(2017, 1, 1, tzinfo=ZoneInfo("UTC")),
                end=dt.datetime(2017, 1, 1, 10, tzinfo=ZoneInfo("UTC")),
            ),
            {
                "start": "2017-01-01T00:00:00+00:00",
                "end": "2017-01-01T10:00:00+00:00",
                "allDay": False,
            },
        ),
        (
            Availability(
                start=dt.datetime(2017, 1, 1, 10, tzinfo=ZoneInfo("UTC")),
                end=dt.datetime(2017, 1, 2, tzinfo=ZoneInfo("UTC")),
            ),
            {
                "start": "2017-01-01T10:00:00+00:00",
                "end": "2017-01-02T00:00:00+00:00",
                "allDay": False,
            },
        ),
        (
            Availability(
                start=dt.datetime(2017, 1, 1, tzinfo=ZoneInfo("UTC")),
                end=dt.datetime(2017, 1, 2, tzinfo=ZoneInfo("UTC")),
            ),
            {
                "start": "2017-01-01T00:00:00+00:00",
                "end": "2017-01-02T00:00:00+00:00",
                "allDay": True,
            },
        ),
    ),
)
def test_serialize_availability(avail, expected):
    with timezone.override(ZoneInfo("UTC")):
        actual = avail.serialize(full=True)
    del actual["id"]
    assert actual == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    "avails,expected,tzname",
    (
        (
            [
                Availability(
                    start=dt.datetime(2017, 1, 1, 10, tzinfo=ZoneInfo("UTC")),
                    end=dt.datetime(2017, 1, 1, 12, tzinfo=ZoneInfo("UTC")),
                )
            ],
            {
                "availabilities": [
                    {
                        "id": 1,
                        "start": "2017-01-01T10:00:00+00:00",
                        "end": "2017-01-01T12:00:00+00:00",
                        "allDay": False,
                    }
                ],
                "event": {
                    "timezone": "UTC",
                    "date_from": "2017-01-01",
                    "date_to": "2017-01-02",
                },
            },
            "UTC",
        ),
        (
            [],
            {
                "availabilities": [],
                "event": {
                    "timezone": "UTC",
                    "date_from": "2017-01-01",
                    "date_to": "2017-01-02",
                },
            },
            "UTC",
        ),
        (
            None,
            {
                "availabilities": [],
                "event": {
                    "timezone": "UTC",
                    "date_from": "2017-01-01",
                    "date_to": "2017-01-02",
                },
            },
            "UTC",
        ),
        (
            None,
            {
                "availabilities": [],
                "event": {
                    "timezone": "America/New_York",
                    "date_from": "2017-01-01",
                    "date_to": "2017-01-02",
                },
            },
            "America/New_York",
        ),
    ),
)
def test_serialize(availabilities_field, avails, expected, tzname):
    with scope(event=availabilities_field.event), timezone.override(ZoneInfo("UTC")):
        availabilities_field.event.timezone = tzname
        availabilities_field.event.save()

        if avails is not None:
            instance = Room.objects.create(event_id=availabilities_field.event.id)
            for avail in avails:
                avail.event_id = availabilities_field.event.id
                avail.room_id = instance.id
                avail.save()
        else:
            instance = None

        if avails:
            for a, j in zip(avails, expected["availabilities"]):
                j["id"] = a.pk

        actual = json.loads(
            availabilities_field._serialize(availabilities_field.event, instance)
        )
        assert actual == expected
