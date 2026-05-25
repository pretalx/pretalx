# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import mail as djmail
from django_scopes import scope

from pretalx.common.exceptions import SubmissionError
from pretalx.submission.domain.access_code import (
    can_delete_access_code,
    delete_orphan_access_codes,
    redeem_access_code,
    send_access_code,
)
from pretalx.submission.models import SubmitterAccessCode
from tests.factories import (
    EventFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_send_access_code_dispatches_and_logs():
    code = SubmitterAccessCodeFactory()
    user = UserFactory()
    djmail.outbox = []

    with scope(event=code.event):
        send_access_code(
            code,
            user=user,
            recipient="a@example.com",
            subject="Subject",
            text="Body text",
        )

        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == ["a@example.com"]
        assert djmail.outbox[0].subject == "Subject"

        log = code.logged_actions().get(action_type="pretalx.access_code.send")
        assert log.person == user
        assert log.is_orga_action is True
        assert log.data == {"email": "a@example.com"}


def test_can_delete_access_code_true_when_unused():
    code = SubmitterAccessCodeFactory()

    with scope(event=code.event):
        assert can_delete_access_code(code) is True


def test_can_delete_access_code_false_when_referenced_by_submission():
    code = SubmitterAccessCodeFactory()
    with scope(event=code.event):
        SubmissionFactory(event=code.event, access_code=code)

        assert can_delete_access_code(code) is False


def test_delete_orphan_access_codes_removes_codes_with_only_one_track():
    event = EventFactory()
    track = TrackFactory(event=event)
    code = SubmitterAccessCodeFactory(event=event)
    code.tracks.add(track)

    delete_orphan_access_codes(track.submitter_access_codes, "tracks")

    assert not SubmitterAccessCode.objects.filter(pk=code.pk).exists()


def test_delete_orphan_access_codes_keeps_codes_with_multiple_tracks():
    event = EventFactory()
    track1 = TrackFactory(event=event)
    track2 = TrackFactory(event=event)
    code = SubmitterAccessCodeFactory(event=event)
    code.tracks.add(track1, track2)

    delete_orphan_access_codes(track1.submitter_access_codes, "tracks")

    assert SubmitterAccessCode.objects.filter(pk=code.pk).exists()


def test_redeem_access_code_only_redeemed_up_to_maximum():
    code = SubmitterAccessCodeFactory(maximum_uses=1)
    first_copy = SubmitterAccessCode.objects.get(pk=code.pk)
    second_copy = SubmitterAccessCode.objects.get(pk=code.pk)

    with scope(event=code.event):
        redeem_access_code(first_copy)
        with pytest.raises(SubmissionError):
            redeem_access_code(second_copy)

    code.refresh_from_db()
    assert code.redeemed == 1


def test_delete_orphan_access_codes_works_for_submission_types():
    event = EventFactory()
    stype = SubmissionTypeFactory(event=event)
    code = SubmitterAccessCodeFactory(event=event)
    code.submission_types.add(stype)

    delete_orphan_access_codes(stype.submitter_access_codes, "submission_types")

    assert not SubmitterAccessCode.objects.filter(pk=code.pk).exists()
