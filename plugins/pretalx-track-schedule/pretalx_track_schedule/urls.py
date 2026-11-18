from django.urls import path

from . import orga_views, views

urlpatterns = [
    path(
        "<slug:event>/p/track-schedule/",
        views.TrackScheduleView.as_view(),
        name="schedule",
    ),
    path(
        "orga/event/<slug:event>/settings/p/track-schedule/",
        orga_views.ColorSettingsView.as_view(),
        name="settings",
    ),
]
