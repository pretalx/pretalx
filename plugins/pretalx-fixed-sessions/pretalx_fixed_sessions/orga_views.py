from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.views.generic import FormView, TemplateView

from pretalx.common.views.mixins import EventPermissionRequired

from .content import apply_to_existing, is_active
from .forms import FixedAnswersForm, FixedSessionForm, NewFixedSessionForm
from .models import FixedSession
from .signals import PERMISSION


class FixedSessionMixin(EventPermissionRequired):
    permission_required = PERMISSION

    def dispatch(self, request, *args, **kwargs):
        if not is_active(request.event):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    @property
    def list_url(self):
        return reverse(
            "plugins:pretalx_fixed_sessions:list",
            kwargs={"event": self.request.event.slug},
        )


class FixedSessionListView(FixedSessionMixin, TemplateView):
    template_name = "pretalx_fixed_sessions/list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = self.request.event
        fixed = {
            f.submission_type_id: f
            for f in FixedSession.objects.filter(submission_type__event=event)
        }
        context["types"] = [
            {
                "type": submission_type,
                "fixed": fixed.get(submission_type.pk),
                "proposals": submission_type.submissions.count(),
            }
            for submission_type in event.submission_types.order_by("default_duration")
        ]
        return context


class FixedSessionFormView(FixedSessionMixin, FormView):
    template_name = "pretalx_fixed_sessions/form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        kwargs["instance"] = self.instance
        return kwargs

    submission_type = None

    @cached_property
    def answers_form(self):
        return FixedAnswersForm(
            data=self.request.POST if self.request.method == "POST" else None,
            event=self.request.event,
            submission_type=self.submission_type,
            fixed=self.instance,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["list_url"] = self.list_url
        context["fixed"] = self.instance
        context["answers_form"] = self.answers_form
        return context

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        # Validate both, so both show their errors
        if form.is_valid() & self.answers_form.is_valid():
            return self.form_valid(form)
        return self.form_invalid(form)

    def form_valid(self, form):
        with transaction.atomic():
            fixed = form.save()
            self.answers_form.save(fixed)
            count = apply_to_existing(fixed)
            self.request.event.log_action(
                "pretalx_fixed_sessions.applied",
                person=self.request.user,
                orga=True,
                data={
                    "session_type": str(fixed.submission_type.name),
                    "proposals_changed": count,
                },
            )
        messages.success(
            self.request,
            _("Saved. {count} proposal(s) were updated.").format(count=count),
        )
        return redirect(self.list_url)


class FixedSessionCreateView(FixedSessionFormView):
    form_class = NewFixedSessionForm
    instance = None


class FixedSessionEditView(FixedSessionFormView):
    form_class = FixedSessionForm

    @cached_property
    def submission_type(self):
        return get_object_or_404(
            self.request.event.submission_types, pk=self.kwargs["type_id"]
        )

    @cached_property
    def instance(self):
        return FixedSession.objects.filter(
            submission_type=self.submission_type
        ).first() or FixedSession(
            submission_type=self.submission_type, title=str(self.submission_type.name)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["submission_type"] = self.submission_type
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "remove":
            if self.instance.pk:
                self.instance.delete()
                request.event.log_action(
                    "pretalx_fixed_sessions.removed",
                    person=request.user,
                    orga=True,
                    data={"session_type": str(self.submission_type.name)},
                )
                messages.success(
                    request,
                    _("Speakers can now edit the content of these proposals again."),
                )
            return redirect(self.list_url)
        return super().post(request, *args, **kwargs)
