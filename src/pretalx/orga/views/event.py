# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: luto

import smtplib
from pathlib import Path

from csp.decorators import csp_update
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.forms.models import inlineformset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy, pgettext, pgettext_lazy
from django.views.generic import (
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)
from django_context_decorator import context
from django_scopes import scope, scopes_disabled
from formtools.wizard.views import SessionWizardView

from pretalx.common.domain.queries.log import event_activity_log
from pretalx.common.fonts import get_font_definitions, get_fonts
from pretalx.common.forms import I18nEventFormSet, save_related_formset
from pretalx.common.forms.log import LogFilterForm
from pretalx.common.models import ActivityLog
from pretalx.common.plugins import get_all_plugins_grouped
from pretalx.common.templatetags.rich_text import render_markdown
from pretalx.common.text.phrases import phrases
from pretalx.common.ui import Button, delete_link
from pretalx.common.views.helpers import is_htmx
from pretalx.common.views.mixins import (
    ActionConfirmMixin,
    EventPermissionRequired,
    Filterable,
    PermissionRequired,
    SensibleBackWizardMixin,
)
from pretalx.event.domain.event import (
    activate_event,
    copy_event_data,
    create_event,
    deactivate_event,
    post_create_event,
    shred_event,
)
from pretalx.event.domain.plugins import apply_plugin_changes
from pretalx.event.domain.team import accept_team_invite
from pretalx.event.interfaces.forms import (
    EventFooterLinkFormset,
    EventForm,
    EventHeaderLinkFormset,
    EventWizardBasicsForm,
    EventWizardDisplayForm,
    EventWizardInitialForm,
    EventWizardPluginForm,
    EventWizardTimelineForm,
)
from pretalx.event.models import Event, TeamInvite
from pretalx.mail.domain.smtp import mail_backend_for_event
from pretalx.mail.interfaces.forms import MailSettingsForm
from pretalx.person.interfaces.forms import UserForm
from pretalx.person.models import User
from pretalx.schedule.interfaces.forms import WidgetGenerationForm, WidgetSettingsForm
from pretalx.submission.domain.review import (
    activate_review_phase,
    validate_review_phases,
)
from pretalx.submission.interfaces.forms import (
    ReviewPhaseForm,
    ReviewScoreCategoryForm,
    ReviewSettingsForm,
)
from pretalx.submission.models import ReviewPhase, ReviewScoreCategory
from pretalx.submission.tasks import task_recalculate_review_scores


class EventSettingsPermission(EventPermissionRequired):
    permission_required = "event.update_event"
    write_permission_required = "event.update_event"

    @property
    def permission_object(self):
        return self.request.event


class FontPreviewCSS(EventSettingsPermission, View):
    def get(self, request, *args, **kwargs):
        fonts = get_fonts(request.event)
        if not fonts:
            return HttpResponse("", content_type="text/css")
        css = get_font_definitions(fonts, list(fonts.keys()))
        return HttpResponse(css, content_type="text/css")


class EventDetail(EventSettingsPermission, UpdateView):
    model = Event
    form_class = EventForm
    template_name = "orga/settings/form.html"

    def get_object(self, queryset=None):
        return self.object

    @cached_property
    def object(self):
        return Event.objects.prefetch_related("extra_links").get(
            pk=self.request.event.pk
        )

    def get_form_kwargs(self, *args, **kwargs):
        response = super().get_form_kwargs(*args, **kwargs)
        response["is_administrator"] = self.request.user.is_administrator
        return response

    @context
    @cached_property
    def header_links_formset(self):
        return EventHeaderLinkFormset(
            self.request.POST if self.request.method == "POST" else None,
            event=self.object,
            prefix="header-links",
            instance=self.object,
        )

    @context
    @cached_property
    def footer_links_formset(self):
        return EventFooterLinkFormset(
            self.request.POST if self.request.method == "POST" else None,
            event=self.object,
            prefix="footer-links",
            instance=self.object,
        )

    @context
    def tablist(self):
        return {
            "general": _("General information"),
            "features": pgettext_lazy("Event settings tab", "Features"),
            "localisation": _("Localisation"),
            "display": _("Display settings"),
            "texts": _("Texts"),
        }

    def get_success_url(self) -> str:
        return self.object.orga_urls.settings

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["submit_buttons"] = [Button()]
        if "heading_font" in self.get_form().fields:
            context["font_preview_url"] = reverse(
                "orga:settings.font-preview.css", kwargs={"event": self.object.slug}
            )
        if self.request.user.is_administrator:
            context["submit_buttons_extra"] = [
                delete_link(
                    self.request.event.orga_urls.delete, label=_("Delete event")
                )
            ]
        return context

    @transaction.atomic
    def form_valid(self, form):
        if (
            not self.footer_links_formset.is_valid()
            or not self.header_links_formset.is_valid()
        ):
            messages.error(self.request, phrases.base.error_saving_changes)
            return self.form_invalid(form)

        result = super().form_valid(form)
        self.footer_links_formset.save()
        self.header_links_formset.save()
        form.instance.log_action(
            "pretalx.event.update", person=self.request.user, orga=True
        )
        messages.success(self.request, phrases.base.saved)
        if form.custom_domain_warning:
            messages.warning(self.request, form.custom_domain_warning)
        return result


class EventLive(EventSettingsPermission, TemplateView):
    template_name = "orga/event/live.html"

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        warnings = []
        suggestions = []
        if (
            not self.request.event.cfp.text
            or len(str(self.request.event.cfp.text)) < 50
        ):
            warnings.append(
                {
                    "text": _("The CfP doesn’t have a full text yet."),
                    "url": self.request.event.cfp.urls.text,
                }
            )
        if (
            not self.request.event.landing_page_text
            or len(str(self.request.event.landing_page_text)) < 50
        ):
            warnings.append(
                {
                    "text": _("The event doesn’t have a landing page text yet."),
                    "url": self.request.event.orga_urls.settings,
                }
            )
        if (
            self.request.event.get_feature_flag("use_tracks")
            and self.request.event.cfp.request_track
            and self.request.event.tracks.count() < 2
        ):
            suggestions.append(
                {
                    "text": _(
                        "You want submitters to choose the tracks for their proposals, but you do not offer tracks for selection. Add at least one track!"
                    ),
                    "url": self.request.event.cfp.urls.tracks,
                }
            )
        if self.request.event.submission_types.count() == 1:
            suggestions.append(
                {
                    "text": _("You have configured only one session type so far."),
                    "url": self.request.event.cfp.urls.types,
                }
            )
        if not self.request.event.questions.exists():
            suggestions.append(
                {
                    "text": _("You have configured no custom fields yet."),
                    "url": self.request.event.cfp.urls.new_question,
                }
            )
        result["warnings"] = warnings
        result["suggestions"] = suggestions
        button_kwargs = {"name": "action", "icon": None}
        if self.request.event.is_public:
            button_kwargs["value"] = "deactivate"
            button_kwargs["color"] = "danger"
            button_kwargs["label"] = _("Go offline")
        else:
            button_kwargs["value"] = "activate"
            button_kwargs["label"] = pgettext(
                "event visibility: make publicly accessible", "Go live"
            )
        result["submit_buttons"] = [Button(**button_kwargs)]
        return result

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        event = request.event
        action = request.POST.get("action")
        if action == "activate":
            if event.is_public:
                messages.success(request, _("This event was already live."))
            else:
                exceptions, extra_messages = activate_event(
                    event, user=request.user, request=request
                )
                if exceptions:
                    messages.error(
                        request,
                        mark_safe("\n".join(render_markdown(e) for e in exceptions)),  # noqa: S308  -- render_markdown sanitises
                    )
                else:
                    messages.success(request, _("This event is now public."))
                    for message in extra_messages:
                        messages.success(request, message)
        elif not event.is_public:
            messages.success(request, _("This event was already hidden."))
        else:
            deactivate_event(event, user=request.user)
            messages.success(request, _("This event is now hidden."))
        return redirect(event.orga_urls.base)


class EventHistory(Filterable, EventSettingsPermission, ListView):
    template_name = "orga/event/history.html"
    model = ActivityLog
    context_object_name = "log_entries"
    paginate_by = 200
    filter_form_class = LogFilterForm

    def get_queryset(self):
        return self.filter_queryset(event_activity_log(self.request.event))


class EventHistoryDetail(EventSettingsPermission, DetailView):
    template_name = "orga/event/history_detail.html"
    model = ActivityLog
    context_object_name = "log"
    pk_url_kwarg = "pk"

    def get_queryset(self):
        return ActivityLog.objects.filter(event=self.request.event)

    @cached_property
    def is_htmx(self):
        return is_htmx(self.request)

    def get_template_names(self):
        if self.is_htmx:
            return ["orga/event/history_detail_content.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_htmx_request"] = self.is_htmx
        return context


class EventReviewSettings(EventSettingsPermission, FormView):
    form_class = ReviewSettingsForm
    template_name = "orga/settings/review.html"

    def get_success_url(self) -> str:
        return self.request.event.orga_urls.review_settings

    @context
    def tablist(self):
        return {
            "general": _("General information"),
            "scores": _("Review scoring"),
            "phases": _("Review phases"),
        }

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["obj"] = self.request.event
        kwargs["attribute_name"] = "settings"
        kwargs["locales"] = self.request.event.locales
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        try:
            phases = self.save_phases()
            scores = self.save_scores()
        except ValidationError as e:
            messages.error(self.request, e.message)
            return self.get(self.request, *self.args, **self.kwargs)
        if not phases or not scores:
            return self.get(self.request, *self.args, **self.kwargs)
        form.save()
        if any(f.affects_review_scores for f in self.scores_formset.initial_forms):
            task_recalculate_review_scores.apply_async(
                kwargs={"event_id": self.request.event.pk}, ignore_result=True
            )
        return super().form_valid(form)

    @context
    @cached_property
    def phases_formset(self):
        formset_class = inlineformset_factory(
            Event,
            ReviewPhase,
            form=ReviewPhaseForm,
            formset=I18nEventFormSet,
            can_delete=True,
            extra=0,
        )
        return formset_class(
            self.request.POST if self.request.method == "POST" else None,
            queryset=ReviewPhase.objects.filter(
                event=self.request.event
            ).select_related("event"),
            event=self.request.event,
            prefix="phase",
        )

    def save_phases(self):
        if not self.phases_formset.is_valid():
            return False

        with transaction.atomic():
            save_related_formset(
                self.phases_formset, parent=self.request.event, fk_field="event"
            )

            # Now that everything is saved, check that the phase windows
            # line up. Raised inside the transaction so a violation rolls
            # the in-progress save back.
            validate_review_phases(self.request.event)
        return True

    @context
    @cached_property
    def scores_formset(self):
        formset_class = inlineformset_factory(
            Event,
            ReviewScoreCategory,
            form=ReviewScoreCategoryForm,
            formset=I18nEventFormSet,
            can_delete=True,
            extra=0,
        )
        return formset_class(
            self.request.POST if self.request.method == "POST" else None,
            queryset=ReviewScoreCategory.objects.filter(event=self.request.event)
            .select_related("event")
            .prefetch_related("scores"),
            event=self.request.event,
            prefix="scores",
        )

    def save_scores(self):
        if not self.scores_formset.is_valid():
            return False
        save_related_formset(
            self.scores_formset, parent=self.request.event, fk_field="event"
        )
        return True


class PhaseActivate(EventSettingsPermission, View):
    def get_object(self):
        return get_object_or_404(
            ReviewPhase, event=self.request.event, pk=self.kwargs.get("pk")
        )

    def post(self, request, *args, **kwargs):
        phase = self.get_object()
        if phase.is_active:
            phase.is_active = False
            phase.save()
        else:
            activate_review_phase(phase, person=request.user)
        return redirect(self.request.event.orga_urls.review_settings)


class EventMailSettings(EventSettingsPermission, FormView):
    form_class = MailSettingsForm
    template_name = "orga/settings/mail.html"

    def get_success_url(self) -> str:
        return self.request.event.orga_urls.mail_settings

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["obj"] = self.request.event
        kwargs["locales"] = self.request.event.locales
        return kwargs

    @context
    def submit_buttons(self):
        return [
            Button(
                name="test", value="1", label=_("Save and test custom SMTP connection")
            ),
            Button(color="info", icon=None),
        ]

    def form_valid(self, form):
        form.save()

        if self.request.POST.get("test", "0").strip() == "1":
            backend = mail_backend_for_event(self.request.event, force_custom=True)
            try:
                backend.test(self.request.event.mail_settings["mail_from"])
            except (OSError, smtplib.SMTPException) as e:
                messages.warning(
                    self.request,
                    _("An error occurred while contacting the SMTP server: %s")
                    % str(e),
                )
            else:
                if form.cleaned_data.get("smtp_use_custom"):
                    messages.success(
                        self.request,
                        _(
                            "Yay, your changes have been saved and the connection attempt to "
                            "your SMTP server was successful."
                        ),
                    )
                else:
                    messages.success(
                        self.request,
                        _(
                            "We’ve been able to contact the SMTP server you configured. "
                            "Remember to check the “use custom SMTP server” checkbox, "
                            "otherwise your SMTP server will not be used."
                        ),
                    )
        else:
            messages.success(self.request, phrases.base.saved)

        return super().form_valid(form)


class InvitationView(FormView):
    template_name = "orga/invitation.html"
    form_class = UserForm

    @context
    @cached_property
    def invitation(self):
        return get_object_or_404(TeamInvite, token__iexact=self.kwargs.get("code"))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        kwargs["password_reset_link"] = reverse("orga:auth.reset")
        return kwargs

    def post(self, *args, **kwargs):
        if not self.request.user.is_anonymous:
            accept_team_invite(self.invitation, user=self.request.user)
            messages.info(self.request, _("You are now part of the team!"))
            return redirect(reverse("orga:event.list"))
        return super().post(*args, **kwargs)

    def form_valid(self, form):
        form.save()
        user = User.objects.filter(pk=form.cleaned_data.get("user_id")).first()
        if not user:  # pragma: no cover -- race condition guard: user was just created by form.save()
            messages.error(
                self.request,
                _(
                    "There was a problem with your authentication. Please contact the organiser for further help."
                ),
            )
            return redirect(self.request.event.urls.base)

        accept_team_invite(self.invitation, user=user)
        messages.info(self.request, _("You are now part of the team!"))
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect(reverse("orga:event.list"))


def condition_plugins(wizard):
    return bool(get_all_plugins_grouped())


class EventWizard(PermissionRequired, SensibleBackWizardMixin, SessionWizardView):
    permission_required = "event.create_event"
    file_storage = FileSystemStorage(location=Path(settings.MEDIA_ROOT) / "new_event")
    form_list = [
        ("initial", EventWizardInitialForm),
        ("basics", EventWizardBasicsForm),
        ("timeline", EventWizardTimelineForm),
        ("display", EventWizardDisplayForm),
        ("plugins", EventWizardPluginForm),
    ]
    condition_dict = {"plugins": condition_plugins}

    def get_template_names(self):
        return [
            f"orga/event/wizard/{self.steps.current}.html",
            "orga/event/wizard/base.html",
        ]

    def get_context_data(self, *args, **kwargs):
        result = super().get_context_data(*args, **kwargs)
        result["submit_buttons"] = [Button(label=_("Next step"), icon=None)]
        if step := result["wizard"]["steps"].prev:
            result["submit_buttons_extra"] = [
                Button(
                    label=_("Previous step"),
                    color="info",
                    name="wizard_goto_step",
                    value=step,
                    icon=None,
                )
            ]
        return result

    @context
    def organiser(self):
        return (
            self.get_cleaned_data_for_step("initial").get("organiser")
            if self.steps.current != "initial"
            else None
        )

    def render(self, form=None, **kwargs):
        if (  # pragma: no cover -- guards against lost session data mid-wizard
            self.steps.current != "initial"
            and self.get_cleaned_data_for_step("initial") is None
        ):
            return self.render_goto_step("initial")
        if self.steps.current == "timeline":
            fdata = self.get_cleaned_data_for_step("basics")
            year = now().year % 100
            if (
                fdata
                and str(year) not in fdata["slug"]
                and str(year + 1) not in fdata["slug"]
            ):
                messages.warning(
                    self.request,
                    str(
                        _(
                            "Please consider including your event’s year in the slug, e.g. myevent{number}."
                        )
                    ).format(number=year),
                )
        elif self.steps.current == "display":
            date_to = self.get_cleaned_data_for_step("timeline").get("date_to")
            if date_to and date_to < now().date():
                messages.warning(
                    self.request,
                    _("Did you really mean to make your event take place in the past?"),
                )
        return super().render(form, **kwargs)

    def get_form_kwargs(self, step=None):
        kwargs = {"user": self.request.user}
        if step != "initial":
            fdata = self.get_cleaned_data_for_step("initial")
            kwargs.update(fdata or {})
        if step in ("display", "plugins"):
            basics_data = self.get_cleaned_data_for_step("basics")
            if basics_data and basics_data.get("copy_from_event"):
                kwargs["copy_from_event"] = basics_data["copy_from_event"]
        return kwargs

    @transaction.atomic()
    def done(self, form_list, *args, **kwargs):
        steps = {}
        for step in ("initial", "basics", "timeline", "display", "plugins"):
            try:
                steps[step] = self.get_cleaned_data_for_step(step)
            except KeyError:  # pragma: no cover -- handles skipped conditional wizard steps (e.g. plugins)
                steps[step] = {}

        with scopes_disabled():
            event = create_event(
                organiser=steps["initial"]["organiser"],
                locales=steps["initial"]["locales"],
                user=self.request.user,
                name=steps["basics"]["name"],
                slug=steps["basics"]["slug"],
                timezone=steps["basics"]["timezone"],
                email=steps["basics"]["email"],
                locale=steps["basics"]["locale"],
                primary_color=steps["display"]["primary_color"],
                logo=steps["display"]["logo"],
                date_from=steps["timeline"]["date_from"],
                date_to=steps["timeline"]["date_to"],
            )
        with scope(event=event):
            post_create_event(
                event,
                user=self.request.user,
                deadline=steps["timeline"].get("deadline"),
                display_settings={
                    "header_pattern": steps["display"].get("header_pattern")
                },
            )

        logdata = {}
        for form in form_list:
            logdata.update(form.cleaned_data)
        with scope(event=event):
            copy_from_event = steps["basics"].get("copy_from_event")
            if copy_from_event:
                copy_event_data(
                    event=event,
                    source=copy_from_event,
                    skip_attributes=[
                        "locale",
                        "locales",
                        "primary_color",
                        "timezone",
                        "email",
                        "deadline",
                        "plugins",
                    ],
                )

            if steps[
                "plugins"
            ]:  # pragma: no branch -- always true when plugins step is shown; empty dict only when step is conditionally skipped
                selected_plugins = steps["plugins"].get("plugins") or []
                apply_plugin_changes(event, selected_plugins)

        return redirect(event.orga_urls.base + "?congratulations")


class EventDelete(PermissionRequired, ActionConfirmMixin, TemplateView):
    permission_required = "person.administrator_user"
    model = Event
    action_text = (
        _(
            "ALL related data, such as proposals, and speaker profiles, and "
            "uploads, will also be deleted and cannot be restored."
        )
        + " "
        + phrases.base.delete_warning
    )

    def get_object(self):
        return self.request.event

    def action_object_name(self):
        return ngettext_lazy("Event", "Events", 1) + f": {self.get_object().name}"

    @property
    def action_back_url(self):
        return self.get_object().orga_urls.settings

    def post(self, request, *args, **kwargs):
        shred_event(self.get_object(), person=self.request.user)
        return redirect(reverse("orga:event.list"))


@method_decorator(csp_update({"script-src": "'self' 'unsafe-eval'"}), name="dispatch")
class WidgetSettings(EventSettingsPermission, FormView):
    form_class = WidgetSettingsForm
    template_name = "orga/settings/widget.html"

    def form_valid(self, form):
        form.save()
        messages.success(self.request, phrases.base.saved)
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["obj"] = self.request.event
        return kwargs

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["extra_form"] = WidgetGenerationForm(instance=self.request.event)
        result["generate_submit"] = [
            Button(_id="generate-widget", _type=None, label=_("Generate widget"))
        ]
        return result

    def get_success_url(self) -> str:
        return self.request.event.orga_urls.widget_settings
