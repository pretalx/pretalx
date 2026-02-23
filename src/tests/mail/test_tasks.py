import datetime as dt

import pytest
from django.utils.timezone import now

from pretalx.mail.models import QueuedMail, QueuedMailStates
from pretalx.mail.tasks import mark_stale_sending_mails_as_failed
from tests.factories import QueuedMailFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_stale_sending_mail_marked_as_failed(event):
    """Mails stuck in SENDING state for over an hour are marked as failed
    with a timeout error."""
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)
    QueuedMail.objects.filter(pk=mail.pk).update(updated=now() - dt.timedelta(hours=2))

    mark_stale_sending_mails_as_failed(None)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.DRAFT
    assert mail.has_error is True
    assert "Timed out" in mail.error_data["error"]
    assert mail.error_data["type"] == "TimeoutError"


@pytest.mark.django_db
def test_recent_sending_mail_not_marked_as_failed(event):
    """Mails that entered SENDING state recently are left alone."""
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    mark_stale_sending_mails_as_failed(None)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENDING
    assert mail.has_error is False
