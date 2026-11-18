from django.urls import path

from . import views

urlpatterns = [
    path("<slug:event>/p/resubmit/", views.ResubmitListView.as_view(), name="list"),
    path(
        "<slug:event>/p/resubmit/<str:code>/",
        views.ResubmitView.as_view(),
        name="resubmit",
    ),
]
