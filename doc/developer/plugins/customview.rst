.. SPDX-FileCopyrightText: 2018-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

.. highlight:: python
   :linenothreshold: 5

.. _`customview`:

Creating custom views
=====================

This page describes how to provide a custom view from within your plugin. Before you start
reading this page, please read and understand how :ref:`URL handling <urlconf>` works in
pretalx.

.. _urlconf:

Organiser panel views
---------------------

If you want to add a custom view to the organiser area of an event, register an URL in your
``urls.py`` that lives in the ``/orga/`` subpath::

    from django.urls import re_path

    from pretalx.event.models.event import SLUG_REGEX

    from . import views

    urlpatterns = [
        re_path(
            rf"^orga/event/(?P<event>{SLUG_REGEX})/p/myplugin/$",
            views.admin_view,
            name="backend",
        ),
        re_path(
            rf"^(?P<event>{SLUG_REGEX})/p/myplugin/$",
            views.frontend_view,
            name="frontend",
        ),
        re_path(
            rf"^p/myplugin/$",
            views.global_view,
            name="global-frontend",
        ),
    ]

If you just created your `urls.py` file and you already had the development
server running, you’ll now have to restart it for the new file to be
recognised.

If your view is event-specific, you have to name one parameter in your URL
``event``. By convention, all plugin URLs except for backend URLs start with
a ``/p/`` to avoid namespace collisions with event names and reserved URLs.

You can then write a regular view. Our middleware will automatically detect the
``/orga/`` subpath and will ensure the following points if this is an URL with
the ``event`` parameter:

* The user has logged in
* The ``request.event`` attribute contains the current event
* The user has permission to view the current event

If you want to require specific permission types, we provide you with a decorator or a mixin for
your views::

    from pretalx.common.mixins.views import PermissionRequired

    class AdminView(PermissionRequired, View):
        permission_required = "submission.orga_list_submission"


There is also a signal that allows you to add the view to the event sidebar navigation like this::


    from django.dispatch import receiver
    from django.urls import resolve, reverse
    from django.utils.translation import ugettext_lazy as _

    from pretalx.orga.signals import nav_event


    @receiver(nav_event, dispatch_uid="friends_tickets_nav")
    def navbar_info(sender, request, **kwargs):
        url = resolve(request.path_info)
        if not request.user.has_perm("event.orga_access_event", request.event):
            return []
        return [{
            "label": _("My plugin view"),
            "icon": "heart",
            "url": reverse("plugins:myplugin:index", kwargs={
                "event": request.event.slug,
            }),
            "active": url.namespace == "plugins:myplugin" and url.url_name == "view",
        }]


Frontend views
--------------

Frontend views work pretty much like organiser area views. Take care that your
URL starts with ``fr"^(?P<event>[{SLUG_REGEX}]+)/p/mypluginname"`` for event
related URLs or ``f"^p/mypluginname"`` for global views. You can then write a
regular view. It will be automatically ensured that:

* The requested event exists
* The requested event is visible (either by being public, or if an organiser looks at it)
* The request involves the correct domain for the event
* The ``request.event`` attribute contains the correct ``Event`` object
* The organiser has enabled the plugin
* The locale middleware has processed the request


API views
---------

You can also expose `Django REST Framework`_ API endpoints from your plugin.
Register your URLs with the ``api/events/<event>/p/<pluginname>/`` prefix using
a DRF `Router <Routers_>`_::

    from rest_framework import routers

    from pretalx.event.models.event import SLUG_REGEX

    from .api import MyViewSet

    router = routers.SimpleRouter()
    router.register(
        f"api/events/(?P<event>{SLUG_REGEX})/p/myplugin",
        MyViewSet,
        basename="myplugin",
    )
    urlpatterns += router.urls

Your view should use ``ApiPermission & PluginPermission`` as its permission
classes. Set ``plugin_required`` to your plugin's name so that the endpoint is
only available for events that have your plugin enabled. Access control is
handled by ``rules_permissions`` on your model::

    from rest_framework import serializers, viewsets
    from rules.contrib.models import RulesModelBase, RulesModelMixin

    from pretalx.api.permissions import ApiPermission, PluginPermission


    class MyModel(RulesModelMixin, models.Model, metaclass=RulesModelBase):
        class Meta:
            rules_permissions = {
                "list": my_list_rule,
                "create": my_create_rule,
                "update": my_create_rule,
            }


    class MySerializer(serializers.ModelSerializer):
        class Meta:
            model = MyModel
            fields = ["id", "name"]


    class MyViewSet(viewsets.ModelViewSet):
        serializer_class = MySerializer
        queryset = MyModel.objects.none()
        permission_classes = [ApiPermission & PluginPermission]
        plugin_required = "pretalx_myplugin"

        def get_queryset(self):
            return MyModel.objects.filter(event=self.request.event)

Token-based API authentication (``Authorization: Token <key>``) works
automatically — the ``ApiPermission`` class skips the fine-grained endpoint
permission check for plugin views that don't participate in the core endpoint
system, while still enforcing event access and object-level permissions via
Django rules.


.. _Django REST Framework: http://www.django-rest-framework.org/
.. _ViewSets: http://www.django-rest-framework.org/api-guide/viewsets/
.. _Routers: http://www.django-rest-framework.org/api-guide/routers/
