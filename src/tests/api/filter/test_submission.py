import pytest
from django_scopes import scopes_disabled

from pretalx.api.filters.submission import SubmissionFilter
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import SubmissionFactory, TrackFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_submission_filter_filters_by_state(event):
    with scopes_disabled():
        sub_submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

        fs = SubmissionFilter(
            data={"state": [SubmissionStates.SUBMITTED]},
            queryset=event.submissions.all(),
        )

    assert list(fs.qs) == [sub_submitted]


@pytest.mark.django_db
def test_submission_filter_filters_by_multiple_states(event):
    with scopes_disabled():
        sub1 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        sub2 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        SubmissionFactory(event=event, state=SubmissionStates.REJECTED)

        fs = SubmissionFilter(
            data={"state": [SubmissionStates.SUBMITTED, SubmissionStates.ACCEPTED]},
            queryset=event.submissions.all(),
        )

    assert set(fs.qs) == {sub1, sub2}


@pytest.mark.django_db
def test_submission_filter_filters_by_track(event):
    with scopes_disabled():
        track = TrackFactory(event=event)
        sub_with_track = SubmissionFactory(event=event, track=track)
        SubmissionFactory(event=event)

        fs = SubmissionFilter(
            data={"track": str(track.pk)}, queryset=event.submissions.all()
        )

    assert list(fs.qs) == [sub_with_track]


@pytest.mark.django_db
def test_submission_filter_filters_by_is_featured(event):
    with scopes_disabled():
        sub_featured = SubmissionFactory(event=event, is_featured=True)
        SubmissionFactory(event=event, is_featured=False)

        fs = SubmissionFilter(
            data={"is_featured": "true"}, queryset=event.submissions.all()
        )

    assert list(fs.qs) == [sub_featured]


@pytest.mark.django_db
def test_submission_filter_filters_by_submission_type(event):
    with scopes_disabled():
        sub = SubmissionFactory(event=event)
        other_event_sub = SubmissionFactory()

        fs = SubmissionFilter(
            data={"submission_type": str(sub.submission_type.pk)},
            queryset=Submission.objects.filter(pk__in=[sub.pk, other_event_sub.pk]),
        )

    assert list(fs.qs) == [sub]
