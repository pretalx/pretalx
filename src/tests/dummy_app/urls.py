from django.http import HttpResponse
from django.urls import path


def dummy_view(request, **kwargs):
    return HttpResponse("ok")


urlpatterns = [path("<slug:event>/test-plugin/", dummy_view, name="test-view")]
