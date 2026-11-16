from django.urls import path

from . import orga_views, views

urlpatterns = [
    path(
        "orga/event/<slug:event>/p/pretix-tickets/",
        orga_views.TicketCheckView.as_view(),
        name="tickets",
    ),
    path(
        "<slug:event>/p/pretix-sso/login/",
        views.LoginStartView.as_view(),
        name="login",
    ),
    path(
        "p/pretix-sso/callback/",
        views.CallbackView.as_view(),
        name="callback",
    ),
]
