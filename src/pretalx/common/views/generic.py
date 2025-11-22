# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Florian Moesch

import datetime as dt
from contextlib import suppress
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.core.paginator import InvalidPage, Paginator
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import NoReverseMatch, path, reverse
from django.utils.decorators import classonlymethod
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.module_loading import import_string
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, View
from django.views.generic.detail import SingleObjectTemplateResponseMixin
from django.views.generic.edit import ModelFormMixin, ProcessFormView
from django_context_decorator import context
from django_tables2.views import SingleTableMixin

from pretalx.cfp.forms.auth import ResetForm
from pretalx.common.exceptions import SendMailException
from pretalx.common.forms.mixins import PretalxI18nModelForm
from pretalx.common.text.phrases import phrases
from pretalx.common.ui import Button, back_button, delete_button
from pretalx.common.views.mixins import Filterable, PaginationMixin
from pretalx.person.forms import UserForm
from pretalx.person.models import User


def get_next_url(request, omit_params=None):
    params = request.GET.copy()
    omit_params = omit_params or []
    for param in omit_params:
        params.pop(param, None)
    if not (url := params.pop("next", [""])[0]):
        return
    if not url_has_allowed_host_and_scheme(url, allowed_hosts=None):
        return
    if params:
        return f"{url}?{params.urlencode()}"
    return url


class FormSignalMixin:
    extra_forms_signal = None

    @cached_property
    def extra_forms(self):
        if not self.extra_forms_signal:
            return []
        signal = import_string(self.extra_forms_signal)
        sender = getattr(self.request, "event", None)
        kwargs = self.get_form_kwargs()
        forms = []
        for _receiver, response in signal.send_robust(
            sender=sender, request=self.request, **kwargs
        ):
            if isinstance(response, Exception):
                continue
            if isinstance(response, list):
                forms.extend(response)
            elif response:
                forms.append(response)
        return forms

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["extra_forms"] = self.extra_forms
        return result

    def form_valid(self, form, **kwargs):
        result = super().form_valid(form, **kwargs)
        for f in self.extra_forms:
            if not f.is_valid():
                if f.errors:
                    messages.error(self.request, f.errors[0])
            else:
                try:
                    f.save()
                except Exception:
                    message = _("Some changes could not be saved.")
                    if label := getattr(f, "label", None):
                        message = f"[{label}] {message}"
                    messages.error(self.request, message)
        return result


class FormLoggingMixin:
    messages = {
        "create": phrases.base.saved,
        "update": phrases.base.saved,
        "delete": phrases.base.deleted,
    }

    def get_log_kwargs(self):
        return {"person": self.request.user, "orga": True}

    def get_log_action(self):
        return f".{self.action}"

    def form_valid(self, form, skip_logging=False):
        if skip_logging:
            form.save()
            self.object = form.instance
            return redirect(self.get_success_url())

        old_data = None
        if (
            self.object
            and hasattr(self.object, "_get_instance_data")
            and self.object.pk
        ):
            old_object = self.object.__class__.objects.get(pk=self.object.pk)
            old_data = old_object._get_instance_data()

        form.save()
        self.object = form.instance

        action = getattr(self, "action", getattr(self, "permission_action", None))
        if message := self.messages.get(action):
            messages.success(self.request, message)

        if form.has_changed() and hasattr(self.object, "log_action"):
            new_data = None
            if hasattr(self.object, "_get_instance_data"):
                new_data = self.object._get_instance_data()

            log_kwargs = self.get_log_kwargs()
            if old_data is not None and new_data is not None:
                log_kwargs["old_data"] = old_data
                log_kwargs["new_data"] = new_data

            self.object.log_action(self.get_log_action(), **log_kwargs)
        return redirect(self.get_success_url())


class CreateOrUpdateView(
    SingleObjectTemplateResponseMixin,
    FormLoggingMixin,
    FormSignalMixin,
    ModelFormMixin,
    ProcessFormView,
):
    def set_object(self):
        with suppress(self.model.DoesNotExist, AttributeError):
            self.object = self.get_object()

    def get(self, request, *args, **kwargs):
        self.set_object()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.set_object()
        return super().post(request, *args, **kwargs)

    def get_log_action(self):
        return ".create" if self.permission_action == "create" else ".update"


class GenericLoginView(FormView):
    form_class = UserForm

    @context
    def password_reset_link(self):
        return self.get_password_reset_link()

    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_anonymous:
            try:
                return redirect(self.get_success_url())
            except Exception:
                return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    @classmethod
    def get_next_url_or_fallback(cls, request, fallback, ignore_next=False):
        """Reused in logout()"""
        if not ignore_next and (next_url := get_next_url(request)):
            return next_url
        url = fallback
        params = request.GET.copy()
        params.pop("next", None)  # remove unsafe next param if any
        params = ("?" + params.urlencode()) if params else ""
        return url + params

    def get_success_url(self, ignore_next=False):
        return self.get_next_url_or_fallback(
            self.request, self.success_url, ignore_next=ignore_next
        )

    @context
    @cached_property
    def success_url(self):
        return self.get_success_url()

    def get_redirect(self):
        try:
            return redirect(self.get_success_url())
        except NoReverseMatch:
            return redirect(self.get_success_url(ignore_next=True))

    def form_valid(self, form):
        pk = form.save()
        user = User.objects.filter(pk=pk).first()
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_redirect()


class GenericResetView(FormView):
    form_class = ResetForm

    def form_valid(self, form):
        user = form.cleaned_data["user"]
        one_day_ago = now() - dt.timedelta(hours=24)

        # We block password resets if the user has reset their password already in the
        # past 24 hours.
        # We permit the reset if the password reset time is in the future, as this can
        # only be due to the way we handle speaker invitations at the moment.
        if not user or (
            user.pw_reset_time and (one_day_ago < user.pw_reset_time < now())
        ):
            messages.success(self.request, phrases.cfp.auth_password_reset)
            return redirect(self.get_success_url())

        try:
            user.reset_password(
                event=getattr(self.request, "event", None),
                orga="orga" in self.request.resolver_match.namespaces,
            )
        except SendMailException:  # pragma: no cover
            messages.error(self.request, phrases.base.error_sending_mail)
            return self.get(self.request, *self.args, **self.kwargs)

        messages.success(self.request, phrases.cfp.auth_password_reset)
        user.log_action("pretalx.user.password.reset")

        return redirect(self.get_success_url())


CRUDHandlerMap = {
    "list": {"get": "list"},
    "detail": {"get": "detail"},
    "create": {"get": "form_view", "post": "form_handler"},
    "update": {"get": "form_view", "post": "form_handler"},
    "delete": {"get": "delete_view", "post": "delete_handler"},
}


class CRUDView(PaginationMixin, FormLoggingMixin, Filterable, View):
    """
    Provides a list, create, detail and update, delete view.

    For use with standard /orga/ views, permissions, logging, and
    tables, use the OrgaCRUDView subclass below.

    Implementation partially vendored from the excellent Neapolitan
    project (MIT licenced) by Carlton Gibson, with thanks for both
    the inspiration and implementation.
    """

    model = None
    queryset = None  # Defaults to model.all()
    object = None
    form_class = None
    template_namespace = None
    context_object_name = None  # Defaults to a model-derived name
    url_base = None
    url_name = None
    lookup_field = "pk"
    path_converter = "int"
    detail_is_update = True
    show_history = True

    def permission_denied(self):
        if (
            getattr(self.request, "event", None)
            and self.request.user.is_anonymous
            and "cfp" in self.request.resolver_match.namespaces
        ):
            params = "&" + self.request.GET.urlencode() if self.request.GET else ""
            return redirect(
                self.request.event.urls.login
                + f"?next={quote(self.request.path)}"
                + params
            )
        raise Http404()

    @cached_property
    def is_generic(self):
        return self.action in ("list", "create")

    def dispatch(self, request, *args, **kwargs):
        if not self.is_generic:
            self.object = self.get_object()
        if not self.has_permission(self.get_permission_required()):
            return self.permission_denied()
        return super().dispatch(request, *args, **kwargs)

    def get_table_data(self):
        return self.filter_queryset(self.get_queryset())

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        filtered_queryset = self.get_table_data()
        if not getattr(self, "table_class", None) and (
            paginate_by := self.get_paginate_by()
        ):
            page = self.paginate_queryset(filtered_queryset, paginate_by)
            self.object_list = page.object_list
            context = self.get_context_data(
                page_obj=page,
                paginator=page.paginator,
                queryset=queryset,
            )
        else:
            # Tables handle their own pagination, but we pass the object list
            # to the template regardless
            self.object_list = filtered_queryset
            context = self.get_context_data(queryset=queryset)
        return self.render_to_response(context)

    def detail(self, request, *args, **kwargs):
        context = self.get_context_data(instance=self.object)
        return self.render_to_response(context)

    def form_view(self, request, *args, **kwargs):
        """GET handler for create and update views."""
        form = self.get_form(instance=self.object)
        context = self.get_context_data(instance=self.object, form=form)
        return self.render_to_response(context)

    @transaction.atomic
    def form_handler(self, request, *args, **kwargs):
        """POST handler for create and update views."""
        form = self.get_form(
            instance=self.object, data=request.POST, files=request.FILES
        )
        if form.is_valid():
            return self.form_valid(form)
        return self.form_invalid(form)

    def delete_view(self, request, *args, **kwargs):
        """GET handler for delete view"""
        context = self.get_context_data(instance=self.object)
        return self.render_to_response(context)

    def perform_delete(self):
        self.object.delete(log_kwargs=self.get_log_kwargs())
        if message := self.messages.get(self.action):
            messages.success(self.request, message)

    @transaction.atomic
    def delete_handler(self, request, *args, **kwargs):
        """POST handler for delete view"""
        self.perform_delete()
        return HttpResponseRedirect(self.get_success_url())

    def get_queryset(self):
        if self.queryset is not None:
            return self.queryset._clone()
        return self.model._default_manager.all()

    def get_object(self):
        queryset = self.get_queryset()
        lookup = {self.lookup_field: self.kwargs[self.lookup_field]}
        return get_object_or_404(queryset, **lookup)

    def get_form_class(self):
        return self.form_class

    def get_form_kwargs(self):
        kwargs = {}
        event = getattr(self.request, "event", None)
        if event and issubclass(self.form_class, PretalxI18nModelForm):
            kwargs["locales"] = event.locales
        return kwargs

    def get_form(self, instance, data=None, files=None, **kwargs):
        cls = self.get_form_class()
        return cls(
            instance=instance,
            data=data,
            files=files,
            **self.get_form_kwargs(),
            **kwargs,
        )

    def form_invalid(self, form):
        context = self.get_context_data(instance=self.object, form=form)
        return self.render_to_response(context)

    @cached_property
    def next_url(self):
        return get_next_url(self.request)

    def get_success_url(self):
        if self.next_url:
            return self.next_url
        if self.action == "delete" or self.detail_is_update:
            return self.reverse("list")
        return self.reverse("detail", instance=self.object)

    def paginate_queryset(self, queryset, page_size):
        paginator = Paginator(queryset, page_size)
        page_number = self.request.GET.get("page") or 1
        if page_number == "last":
            page_number = paginator.num_pages
        else:
            try:
                page_number = int(page_number)
            except ValueError:
                page_number = 1

        try:
            return paginator.page(page_number)
        except InvalidPage:
            return paginator.page(1)

    def get_context_object_name(self):
        if self.context_object_name is not None:
            name = self.context_object_name
        else:
            name = self.model._meta.object_name.lower()
        if name and self.action == "list":
            return f"{name}_list"
        return name

    def get_reverse_kwargs(self, action, instance=None):
        if instance:
            return {self.lookup_field: getattr(instance, self.lookup_field)}
        return {}

    def reverse(self, action, instance=None):
        url_name = f"{self.url_name}.{action}"
        if self.namespace:
            url_name = f"{self.namespace}:{url_name}"
        return reverse(url_name, kwargs=self.get_reverse_kwargs(action, instance))

    def get_generic_title(self, instance=None):
        if instance:
            return str(instance)
        return self.model._meta.object_name

    @property
    def create_button_label(self):
        return _("New")

    def get_generic_permission_object(self):
        """Used to determine non-object permissions like list, create, and generic delete"""
        raise NotImplementedError

    def get_permission_object(self):
        return self.object

    def get_permission_required(self):
        return self.model.get_perm(self.action)

    @cached_property
    def permission_object(self):
        if self.is_generic:
            return self.get_generic_permission_object()
        return self.get_permission_object()

    def has_permission(self, permission):
        return self.request.user.has_perm(permission, self.permission_object)

    @cached_property
    def has_create_permission(self):
        return self.has_permission(self.model.get_perm("create"))

    @cached_property
    def has_update_permission(self):
        return self.has_permission(self.model.get_perm("update"))

    @cached_property
    def has_delete_permission(self):
        return self.has_permission(self.model.get_perm("delete"))

    def get_back_button(self):
        return back_button(self.next_url or self.reverse("list"))

    def get_context_data(self, **kwargs):
        kwargs["view"] = self
        kwargs["action"] = self.action
        if self.has_create_permission:
            with suppress(NoReverseMatch):
                kwargs["create_url"] = self.reverse("create")
        kwargs["has_update_permission"] = self.has_update_permission
        kwargs["has_delete_permission"] = self.has_delete_permission
        kwargs["generic_title"] = self.get_generic_title(instance=self.object)
        kwargs["create_button_label"] = self.create_button_label

        if self.object:
            kwargs["object"] = self.object
            if name := self.get_context_object_name():
                kwargs[name] = self.object

        elif getattr(self, "object_list", None) is not None:
            kwargs["object_list"] = self.object_list
            kwargs["has_create_permission"] = self.has_create_permission
            if name := self.get_context_object_name():
                kwargs[name] = self.object_list

        if kwargs.get("form"):
            kwargs["submit_buttons_extra"] = [self.get_back_button()]
            kwargs["submit_buttons"] = [Button()]
        elif self.action == "delete":
            kwargs["submit_buttons_extra"] = [self.get_back_button()]
            kwargs["submit_buttons"] = [delete_button()]
        if self.action == "detail":
            kwargs["show_history"] = self.show_history and self.has_update_permission
        elif self.action == "update":
            kwargs["show_history"] = (
                self.show_history
                and self.has_update_permission
                and self.detail_is_update
            )
        return kwargs

    def get_template_names(self):
        namespace = self.template_namespace or "common"
        object_name = self.model._meta.object_name.lower()
        templates = [
            f"{namespace}/{object_name}/{self.action}.html",
            f"{namespace}/{object_name}_{self.action}.html",
        ]
        if self.action in ("create", "update"):
            # Make it easy to use a shared base form template for create and update.
            # Useful for including the same static files in each
            templates += [
                f"{namespace}/{object_name}/_form.html",
                f"{namespace}/{object_name}_form.html",
            ]
        # Finally, fall back to the generic template for this action
        templates.append(f"common/generic/{self.action}.html")
        return templates

    def render_to_response(self, context):
        return TemplateResponse(
            request=self.request, template=self.get_template_names(), context=context
        )

    @classonlymethod
    def as_view(cls, action, url_name, namespace):
        def view(request, *args, **kwargs):
            self = cls()
            self.action = action
            self.url_name = url_name
            self.namespace = namespace
            self.setup(request, *args, **kwargs)
            crud_map = CRUDHandlerMap.get(action).copy()
            if extra_actions := getattr(cls, "extra_actions", {}).get(action):
                crud_map.update(extra_actions)
            for verb, method in crud_map.items():
                setattr(self, verb, getattr(self, method))
            return self.dispatch(request, *args, **kwargs)

        view.view_class = cls
        view.__module__ = cls.__module__
        # Copy possible attributes set by decorators, e.g. @csrf_exempt, from
        # the dispatch method.
        view.__dict__.update(cls.dispatch.__dict__)
        return view

    @classonlymethod
    def get_url_pattern(cls, url_base, action):
        if action == "list":
            return f"{url_base}/"
        if action == "create":
            return f"{url_base}/new/"
        url_base = f"{url_base}/<{cls.path_converter}:{cls.lookup_field}>"
        if action == "detail" or (action == "update" and cls.detail_is_update):
            return f"{url_base}/"
        if action == "update":
            return f"{url_base}/edit/"
        if action == "delete":
            return f"{url_base}/delete/"

    @classonlymethod
    def get_urls(cls, url_base, url_name, namespace=None, actions=None):
        actions = actions or CRUDHandlerMap.keys()
        if cls.detail_is_update:
            actions = [action for action in actions if action != "detail"]
        return [
            path(
                cls.get_url_pattern(url_base, action),
                cls.as_view(action=action, url_name=url_name, namespace=namespace),
                name=f"{url_name}.{action}",
            )
            for action in actions
        ]


class OrgaTableMixin(SingleTableMixin):
    table_class = None
    DEFAULT_PAGINATION = 50

    def get_paginate_by(self, queryset=None):
        # TODO: remove most of this method including the fallback to
        # session-based handling in 2026, data should have been migrated
        # by active use (and if not, it can’t have mattered that much)
        if not (default := getattr(self, "_table_page_size", None)):
            skey = "stored_page_size_" + self.request.resolver_match.url_name
            default = (
                self.request.session.get(skey)
                or getattr(self, "paginate_by", None)
                or self.DEFAULT_PAGINATION
            )

        if self.request.GET.get("page_size"):
            try:
                if max_page_size := getattr(
                    self, "max_page_size", settings.MAX_PAGINATION_LIMIT
                ):
                    size = min(max_page_size, int(self.request.GET.get("page_size")))
                else:
                    size = int(self.request.GET.get("page_size"))

                if (
                    self.request.user.is_authenticated
                    and (table := getattr(self, "table", None))
                    and (event := getattr(table, "event", None))
                ):
                    preferences = self.request.user.get_event_preferences(event)
                    preferences.set(f"tables.{table.name}.page_size", size, commit=True)
                else:
                    skey = "stored_page_size_" + self.request.resolver_match.url_name
                    self.request.session[skey] = size

                return size
            except ValueError:
                return default
        return default

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        kwargs["event"] = getattr(self.request, "event", None)
        kwargs["user"] = getattr(self.request, "user", None)
        return kwargs

    def get_table(self, *args, **kwargs):
        if not self.table_class:
            return
        table = super().get_table(*args, **kwargs)
        page_size = table.configure(self.request)
        self._table_page_size = page_size
        return table


class OrgaCRUDView(OrgaTableMixin, FormSignalMixin, CRUDView):

    @cached_property
    def event(self):
        return getattr(self.request, "event", None)

    @cached_property
    def organiser(self):
        return getattr(self.request, "organiser", None)

    def get_reverse_kwargs(self, *args, **kwargs):
        result = super().get_reverse_kwargs(*args, **kwargs)
        if self.event:
            result["event"] = self.event.slug
        elif self.organiser:
            result["organiser"] = self.organiser.slug
        return result

    def get_form_kwargs(self, *args, **kwargs):
        result = super().get_form_kwargs(*args, **kwargs)
        if self.event:
            result["event"] = self.event
        elif self.organiser:
            result["organiser"] = self.organiser
        return result

    def get_log_kwargs(self):
        result = super().get_log_kwargs()
        result["orga"] = True
        return result

    def get_generic_permission_object(self):
        if self.event:
            return self.event
        return getattr(self.request, "organiser", None)

    @transaction.atomic
    def form_valid(self, form, **kwargs):
        if self.event:
            form.instance.event = self.request.event
        return super().form_valid(form, **kwargs)

    def get_template_names(self):
        result = super().get_template_names()
        return result[:-1] + [f"orga/generic/{self.action}.html"]

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        kwargs["has_update_permission"] = self.has_update_permission
        kwargs["has_delete_permission"] = self.has_delete_permission
        return kwargs
