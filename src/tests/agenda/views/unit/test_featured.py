import pytest
from django_scopes import scope, scopes_disabled

from pretalx.agenda.views.featured import FeaturedView
from pretalx.submission.models import SubmissionStates
from tests.factories import SubmissionFactory
from tests.utils import make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_featured_view_talks_returns_only_featured(event):
    """Only submissions with is_featured=True are included."""
    with scopes_disabled():
        featured = SubmissionFactory(
            event=event, is_featured=True, state=SubmissionStates.CONFIRMED
        )
        SubmissionFactory(
            event=event, is_featured=False, state=SubmissionStates.CONFIRMED
        )

    request = make_request(event)
    view = make_view(FeaturedView, request)

    with scope(event=event):
        result = list(view.talks())

    assert result == [featured]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state",
    (SubmissionStates.REJECTED, SubmissionStates.CANCELED, SubmissionStates.WITHDRAWN),
    ids=["rejected", "canceled", "withdrawn"],
)
def test_featured_view_talks_excludes_hidden_states(event, state):
    """Featured submissions in rejected/canceled/withdrawn states are excluded."""
    with scopes_disabled():
        SubmissionFactory(event=event, is_featured=True, state=state)

    request = make_request(event)
    view = make_view(FeaturedView, request)

    with scope(event=event):
        result = list(view.talks())

    assert result == []


@pytest.mark.django_db
def test_featured_view_talks_ordered_by_title(event):
    """Featured talks are returned ordered alphabetically by title."""
    with scopes_disabled():
        talk_b = SubmissionFactory(
            event=event,
            is_featured=True,
            title="Beta Talk",
            state=SubmissionStates.CONFIRMED,
        )
        talk_a = SubmissionFactory(
            event=event,
            is_featured=True,
            title="Alpha Talk",
            state=SubmissionStates.CONFIRMED,
        )

    request = make_request(event)
    view = make_view(FeaturedView, request)

    with scope(event=event):
        result = list(view.talks())

    assert result == [talk_a, talk_b]
