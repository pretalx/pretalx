from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.views.generic import FormView, TemplateView

from pretalx.cfp.views.event import LoggedInEventPageMixin
from pretalx.common.views.redirect import get_login_redirect

from .forms import ResubmitForm
from .resubmit import can_resubmit_to, eligible_sources, resubmit


class ResubmitMixin(LoggedInEventPageMixin):
    def handle_no_permission(self):
        # pretalx only sends anonymous users to the login page on its own CfP
        # pages and answers 404 on plugin pages
        if self.request.user.is_anonymous:
            return get_login_redirect(self.request)
        return super().handle_no_permission()

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not can_resubmit_to(request.event):
            messages.error(request, _("This event is not accepting proposals right now."))
            return redirect(request.event.urls.user_submissions)
        return super().dispatch(request, *args, **kwargs)


class ResubmitListView(ResubmitMixin, TemplateView):
    """The speaker's proposals that can be resubmitted, reachable from the
    event's start and CfP pages: pretalx only links "Your proposals" there once
    the event has proposals."""

    template_name = "pretalx_resubmit/list.html"

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "sources": eligible_sources(self.request.event, self.request.user),
        }


class ResubmitView(ResubmitMixin, FormView):
    template_name = "pretalx_resubmit/resubmit.html"
    form_class = ResubmitForm

    @cached_property
    def source(self):
        code = self.kwargs["code"].upper()
        for submission in eligible_sources(self.request.event, self.request.user):
            if submission.code == code:
                return submission
        raise Http404

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "event": self.request.event, "source": self.source}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "source": self.source}

    def form_valid(self, form):
        submission = resubmit(
            self.source,
            event=self.request.event,
            user=self.request.user,
            submission_type=form.cleaned_data["submission_type"],
            track=form.cleaned_data.get("track"),
            content_locale=form.cleaned_data["content_locale"],
        )
        messages.success(
            self.request,
            _(
                "Your proposal was submitted. Please check it below and answer any "
                "questions this event asks, and invite your co-speakers again if "
                "you have any."
            ),
        )
        return redirect(submission.urls.user_base)
