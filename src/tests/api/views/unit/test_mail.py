import pytest
from django_scopes import scopes_disabled

from pretalx.api.views.mail import MailTemplateViewSet
from tests.factories import MailTemplateFactory
from tests.utils import make_api_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_mail_template_viewset_get_queryset_returns_event_templates():
    """get_queryset returns mail templates belonging to the view's event."""
    with scopes_disabled():
        template = MailTemplateFactory()
        other_template = MailTemplateFactory()
    request = make_api_request(event=template.event)
    view = make_view(MailTemplateViewSet, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert template in qs
    assert other_template not in qs


@pytest.mark.django_db
def test_mail_template_viewset_get_queryset_orders_by_pk():
    """get_queryset returns templates ordered by primary key."""
    with scopes_disabled():
        t1 = MailTemplateFactory()
        t2 = MailTemplateFactory(event=t1.event)
    request = make_api_request(event=t1.event)
    view = make_view(MailTemplateViewSet, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    # Filter to just the templates we created (event has auto-created templates too)
    our_templates = [t for t in qs if t.pk in (t1.pk, t2.pk)]
    assert our_templates == [t1, t2]
