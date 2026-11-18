from django.urls import path

from . import orga_views

urlpatterns = [
    path(
        "orga/event/<slug:event>/settings/p/fixed-sessions/",
        orga_views.FixedSessionListView.as_view(),
        name="list",
    ),
    path(
        "orga/event/<slug:event>/settings/p/fixed-sessions/new/",
        orga_views.FixedSessionCreateView.as_view(),
        name="create",
    ),
    path(
        "orga/event/<slug:event>/settings/p/fixed-sessions/<int:type_id>/",
        orga_views.FixedSessionEditView.as_view(),
        name="edit",
    ),
]
