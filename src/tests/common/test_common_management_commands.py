# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import os
import subprocess
from contextlib import suppress

import pytest
import responses
from django.core import mail as djmail
from django.core.management import call_command
from django_scopes import scope

from pretalx.event.models import Event


@pytest.mark.django_db
@responses.activate
def test_common_runperiodic():
    responses.add(
        responses.POST,
        "https://pretalx.com/.update_check/",
        json="{}",
        status=404,
        content_type="application/json",
    )
    call_command("runperiodic")


@pytest.mark.skipif(
    "CI" not in os.environ or not os.environ["CI"],
    reason="Having Faker installed increases test runtime, so we just test this on CI.",
)
@pytest.mark.parametrize("stage", ("cfp", "review", "over", "schedule"))
@pytest.mark.django_db
def test_common_test_event(administrator, stage):
    call_command("create_test_event", stage=stage)
    assert Event.objects.get(slug="democon")


@pytest.mark.skipif(
    "CI" not in os.environ or not os.environ["CI"],
    reason="Having Faker installed increases test runtime, so we just test this on CI.",
)
@pytest.mark.django_db
def test_common_test_event_with_seed(administrator):
    call_command("create_test_event", seed=1)
    assert Event.objects.get(slug="democon")


@pytest.mark.skipif(
    "CI" not in os.environ or not os.environ["CI"],
    reason="Having Faker installed increases test runtime, so we just test this on CI.",
)
@pytest.mark.django_db
def test_common_test_event_without_user():
    call_command("create_test_event")
    assert Event.objects.count() == 0


@pytest.mark.django_db
def test_common_uncallable(event):
    with pytest.raises(OSError):  # noqa: PT011
        call_command("init")
    with pytest.raises(Exception):  # noqa: PT011, B017
        call_command("shell", "--unsafe-disable-scopes")


@pytest.mark.django_db
def test_common_custom_migrate_does_not_blow_up():
    call_command("migrate")


@pytest.mark.django_db
def test_common_custom_makemessages_does_not_blow_up():
    call_command("makemessages", "--keep-pot", locale=["de_DE"])
    with suppress(Exception):
        subprocess.run(
            [
                "git",
                "checkout",
                "--",
                "pretalx/locale/de_DE",
                "pretalx/locale/django.pot",
            ],
            check=False,
        )


@pytest.mark.django_db
def test_common_move_event(event, slot):
    with scope(event=event):
        old_start = event.date_from
        first_start = slot.start
    call_command(
        "move_event",
        event=event.slug,
        date=(event.date_from + dt.timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    with scope(event=event):
        event.refresh_from_db()
        new_start = event.date_from
        assert new_start != old_start
        slot.refresh_from_db()
        assert slot.start != first_start
    call_command("move_event", event=event.slug)
    with scope(event=event):
        event.refresh_from_db()
        assert event.date_from == old_start


@pytest.mark.django_db
def test_generate_api_docs():
    # Just make sure there is no exception
    call_command("spectacular")


@pytest.mark.django_db
def test_sendtestemail(settings):
    djmail.outbox = []
    call_command("sendtestemail", "test@example.com")
    assert len(djmail.outbox) == 1
    mail = djmail.outbox[0]
    assert mail.to == ["test@example.com"]
    assert mail.from_email == f"pretalx <{settings.MAIL_FROM}>"
    assert "test" in mail.subject
    assert "pretalx" in mail.body


@pytest.mark.django_db
def test_sendtestemail_failure(mocker):
    djmail.outbox = []
    mocker.patch(
        "pretalx.common.mail.mail_send_task.apply",
        side_effect=Exception("connection refused"),
    )
    call_command("sendtestemail", "test@example.com")
    assert djmail.outbox == []
