# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Jahongir Rahmonov  =)
# SPDX-FileContributor: Johan Van de Wauw

import json
from collections import defaultdict

from csp.decorators import csp_update
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.forms.models import inlineformset_factory
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView, UpdateView, View
from django_context_decorator import context

from pretalx.cfp.flow import CfPFlow
from pretalx.common.forms import I18nFormSet
from pretalx.common.text.phrases import phrases
from pretalx.common.text.serialize import I18nStrJSONEncoder
from pretalx.common.ui import send_button
from pretalx.common.views.generic import OrgaCRUDView, get_next_url
from pretalx.common.views.mixins import (
    EventPermissionRequired,
    OrderActionMixin,
    PermissionRequired,
)
from pretalx.mail.models import MailTemplateRoles
from pretalx.orga.forms import CfPForm, QuestionForm, SubmissionTypeForm, TrackForm
from pretalx.orga.forms.cfp import (
    AccessCodeSendForm,
    AnswerOptionForm,
    CfPSettingsForm,
    QuestionFilterForm,
    ReminderFilterForm,
    SubmitterAccessCodeForm,
)
from pretalx.orga.tables.cfp import (
    QuestionTable,
    SubmissionTypeTable,
    SubmitterAccessCodeTable,
    TrackTable,
)
from pretalx.submission.models import (
    AnswerOption,
    CfP,
    Question,
    QuestionTarget,
    SubmissionStates,
    SubmissionType,
    SubmitterAccessCode,
    Track,
)
from pretalx.submission.rules import questions_for_user


class CfPTextDetail(PermissionRequired, UpdateView):
    form_class = CfPForm
    model = CfP
    template_name = "orga/cfp/text.html"
    permission_required = "event.update_event"
    write_permission_required = "event.update_event"

    @context
    def tablist(self):
        return {
            "general": _("General information"),
            "fields": _("Fields"),
        }

    @context
    @cached_property
    def sform(self):
        return CfPSettingsForm(
            read_only=(self.permission_action == "view"),
            locales=self.request.event.locales,
            obj=self.request.event,
            data=self.request.POST if self.request.method == "POST" else None,
            prefix="settings",
        )

    @context
    @cached_property
    def different_deadlines(self):
        deadlines = defaultdict(list)
        for session_type in self.request.event.submission_types.filter(
            deadline__isnull=False
        ):
            deadlines[session_type.deadline].append(session_type)
        deadlines.pop(self.request.event.cfp.deadline, None)
        if deadlines:
            return dict(deadlines)

    def get_object(self, queryset=None):
        return self.request.event.cfp

    def get_success_url(self) -> str:
        return self.object.urls.text

    @transaction.atomic
    def form_valid(self, form):
        if not self.sform.is_valid():
            messages.error(self.request, phrases.base.error_saving_changes)
            return self.form_invalid(form)
        messages.success(self.request, phrases.base.saved)
        form.instance.event = self.request.event
        result = super().form_valid(form)
        if form.has_changed():
            form.instance.log_action(
                "pretalx.cfp.update", person=self.request.user, orga=True
            )
        self.sform.save()
        return result


class QuestionView(OrderActionMixin, OrgaCRUDView):
    model = Question
    form_class = QuestionForm
    table_class = QuestionTable
    template_namespace = "orga/cfp"
    context_object_name = "question"
    detail_is_update = False
    create_button_label = _("New custom field")

    def get_queryset(self):
        for_answers = self.action == "detail"
        return (
            questions_for_user(
                self.request.event, self.request.user, for_answers=for_answers
            )
            .annotate(answer_count=Count("answers"))
            .order_by("position")
        )

    def get_generic_title(self, instance=None):
        if instance:
            return (
                _("Custom field")
                + f" {phrases.base.quotation_open}{instance.question}{phrases.base.quotation_close}"
            )
        if self.action == "create":
            return _("New custom field")
        return _("Custom fields")

    def get_permission_required(self):
        permission_map = {"list": "orga_list", "detail": "orga_view"}
        permission = permission_map.get(self.action, self.action)
        return self.model.get_perm(permission)

    def get_success_url(self):
        if self.next_url:
            return self.next_url
        if self.action == "delete":
            return self.reverse("list")
        if self.request.user.has_perm("submission.orga_view_question", self.object):
            # Users may have edit permissions but not view permissions, as the
            # detail view includes question answers, which can be limited to
            # be accessed by specific teams.
            return self.reverse("detail", instance=self.object)
        return self.reverse("list")

    @cached_property
    def formset(self):
        formset_class = inlineformset_factory(
            Question,
            AnswerOption,
            form=AnswerOptionForm,
            formset=I18nFormSet,
            can_delete=True,
            extra=0 if self.object else 2,
        )
        return formset_class(
            self.request.POST if self.request.method == "POST" else None,
            queryset=(
                AnswerOption.objects.filter(question=self.object)
                if self.object and self.object.pk
                else AnswerOption.objects.none()
            ),
            event=self.request.event,
        )

    def save_formset(self, obj):
        if not self.formset.is_valid():
            return False
        for form in self.formset.initial_forms:
            if form in self.formset.deleted_forms:
                if not form.instance.pk:
                    continue
                form.instance.delete()
                form.instance.pk = None
            elif form.has_changed():
                form.instance.question = obj
                form.save()

        extra_forms = [
            form
            for form in self.formset.extra_forms
            if form.has_changed and not self.formset._should_delete_form(form)
        ]
        for form in extra_forms:
            form.instance.question = obj
            form.save()

        return True

    @cached_property
    def filter_form(self):
        return QuestionFilterForm(self.request.GET, event=self.request.event)

    @cached_property
    def base_search_url(self):
        if not self.object or self.object.target == "reviewer":
            return
        role = self.request.GET.get("role") or ""
        track = self.request.GET.get("track") or ""
        submission_type = self.request.GET.get("submission_type") or ""
        if self.object.target == "submission":
            url = self.request.event.orga_urls.submissions + "?"
            if role == "accepted":
                url = f"{url}state=accepted&state=confirmed&"
            elif role == "confirmed":
                url = f"{url}state=confirmed&"
            if track:
                url = f"{url}track={track}&"
            if submission_type:
                url = f"{url}submission_type={submission_type}&"
        else:
            url = self.request.event.orga_urls.speakers + "?"
        return f"{url}&question={self.object.id}&"

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)

        if "form" in result:
            result["formset"] = self.formset

        if not self.object or not self.filter_form.is_valid():
            return result

        result.update(self.filter_form.get_question_information(self.object))
        result["grouped_answers_json"] = json.dumps(
            list(result["grouped_answers"]), cls=I18nStrJSONEncoder
        )
        if self.action == "detail":
            result["base_search_url"] = self.base_search_url
            result["filter_form"] = self.filter_form
        return result

    def form_valid(self, form):
        form.instance.event = self.request.event
        created = not form.instance.pk
        self.object = form.instance
        if form.cleaned_data.get("variant") in ("choices", "multiple_choice"):
            changed_options = [
                form.changed_data for form in self.formset if form.has_changed()
            ]
            if form.cleaned_data.get("options") and changed_options:
                messages.error(
                    self.request,
                    _(
                        "You cannot change the options and upload an option file at the same time."
                    ),
                )
                return self.form_invalid(form)

        old_data = {}
        if not created:
            old_obj = self.request.event.questions(manager="all_objects").get(
                pk=form.instance.pk
            )
            old_data = old_obj._get_instance_data()

        result = super().form_valid(form, skip_logging=True)

        stay_on_page = False
        if form.cleaned_data.get("variant") in (
            "choices",
            "multiple_choice",
        ) and not form.cleaned_data.get("options"):
            formset = self.save_formset(self.object)
            if not formset:
                stay_on_page = True

        if not created and (form.has_changed() or self.formset.has_changed()):
            form.instance.log_action(
                ".update",
                person=self.request.user,
                orga=True,
                old_data=old_data,
                new_data=form.instance._get_instance_data(),
            )
        elif created:
            form.instance.log_action(".create", person=self.request.user, orga=True)

        if stay_on_page:
            return self.get(self.request, *self.args, **self.kwargs)
        return result

    def post(self, request, *args, **kwargs):
        order = request.POST.get("order")
        if not order:
            return super().post(request, *args, **kwargs)
        order = order.split(",")
        for index, pk in enumerate(order):
            option = get_object_or_404(
                self.object.options,
                pk=pk,
            )
            option.position = index
            option.save(update_fields=["position"])
        return self.get(request, *args, **kwargs)

    def perform_delete(self):
        try:
            with transaction.atomic():
                self.object.options.all().delete()
                self.object.logged_actions().delete()
                super().perform_delete()
        except ProtectedError:
            self.object.active = False
            self.object.save()
            messages.error(
                self.request,
                _(
                    "You cannot delete a custom field that has any responses. We have deactivated the field instead."
                ),
            )


class CfPQuestionToggle(PermissionRequired, View):
    permission_required = "submission.update_question"

    def get_object(self) -> Question:
        return Question.all_objects.filter(
            event=self.request.event, pk=self.kwargs.get("pk")
        ).first()

    def dispatch(self, request, *args, **kwargs):
        super().dispatch(request, *args, **kwargs)
        question = self.get_object()

        question.active = not question.active
        question.save(update_fields=["active"])
        return redirect(question.urls.base)


class CfPQuestionRemind(EventPermissionRequired, FormView):
    template_name = "orga/cfp/question/remind.html"
    permission_required = "submission.update_question"
    form_class = ReminderFilterForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        return kwargs

    @staticmethod
    def get_missing_answers(*, questions, person, submissions):
        missing = []
        submissions = submissions.filter(speakers__in=[person])
        for question in questions:
            if question.target == QuestionTarget.SUBMISSION:
                for submission in submissions:
                    answer = question.answers.filter(submission=submission).first()
                    if not answer or not answer.is_answered:
                        missing.append(question)
            elif question.target == QuestionTarget.SPEAKER:
                answer = question.answers.filter(person=person).first()
                if not answer or not answer.is_answered:
                    missing.append(question)
        return missing

    @context
    def submit_buttons(self):
        return [send_button()]

    @context
    def reminder_template(self):
        return self.request.event.get_mail_template(MailTemplateRoles.QUESTION_REMINDER)

    def form_invalid(self, form):
        messages.error(self.request, _("Could not send mails, error in configuration."))
        return super().form_invalid(form)

    def form_valid(self, form):
        submissions = form.get_submissions()
        people = self.request.event.submitters.filter(submissions__in=submissions)
        questions = form.cleaned_data["questions"] or form.get_question_queryset()
        data = {
            "url": self.request.event.urls.user_submissions.full(),
        }
        for person in people:
            missing = self.get_missing_answers(
                questions=questions, person=person, submissions=submissions
            )
            if missing:
                data["questions"] = "\n".join(
                    f"- {question.question}" for question in missing
                )
                self.request.event.get_mail_template(
                    MailTemplateRoles.QUESTION_REMINDER
                ).to_mail(
                    person,
                    event=self.request.event,
                    context=data,
                    context_kwargs={"user": person},
                )
        return super().form_valid(form)

    def get_success_url(self):
        return self.request.event.orga_urls.outbox


class SubmissionTypeView(OrderActionMixin, OrgaCRUDView):
    model = SubmissionType
    form_class = SubmissionTypeForm
    table_class = SubmissionTypeTable
    template_namespace = "orga/cfp"
    create_button_label = _("New type")

    def get_queryset(self):
        return (
            self.request.event.submission_types.all()
            .order_by("default_duration")
            .annotate(
                submission_count=Count(
                    "submissions",
                    filter=~Q(
                        submissions__state__in=[
                            SubmissionStates.DELETED,
                            SubmissionStates.DRAFT,
                        ]
                    ),
                )
            )
        )

    def get_permission_required(self):
        permission_map = {"list": "orga_list", "detail": "orga_detail"}
        permission = permission_map.get(self.action, self.action)
        return self.model.get_perm(permission)

    def get_generic_title(self, instance=None):
        if instance:
            return (
                _("Session type")
                + f" {phrases.base.quotation_open}{instance.name}{phrases.base.quotation_close}"
            )
        if self.action == "create":
            return _("New session type")
        return _("Session types")

    def delete_handler(self, request, *args, **kwargs):
        try:
            return super().delete_handler(request, *args, **kwargs)
        except ProtectedError:
            messages.error(
                request,
                _("This session type is in use in a proposal and cannot be deleted."),
            )
            return self.delete_view(request, *args, **kwargs)


class SubmissionTypeDefault(PermissionRequired, View):
    permission_required = "submission.update_submissiontype"

    def get_object(self):
        return get_object_or_404(
            self.request.event.submission_types, pk=self.kwargs.get("pk")
        )

    def dispatch(self, request, *args, **kwargs):
        super().dispatch(request, *args, **kwargs)
        submission_type = self.get_object()
        self.request.event.cfp.default_type = submission_type
        self.request.event.cfp.save(update_fields=["default_type"])
        submission_type.log_action(
            "pretalx.submission_type.make_default", person=self.request.user, orga=True
        )
        messages.success(request, _("The session type has been made default."))
        url = get_next_url(request)
        return redirect(url or self.request.event.cfp.urls.types)


class TrackView(OrderActionMixin, OrgaCRUDView):
    model = Track
    form_class = TrackForm
    table_class = TrackTable
    template_namespace = "orga/cfp"
    create_button_label = _("New track")

    def get_queryset(self):
        return (
            self.request.event.tracks.all()
            .annotate(
                submission_count=Count(
                    "submissions",
                    filter=~Q(
                        submissions__state__in=[
                            SubmissionStates.DELETED,
                            SubmissionStates.DRAFT,
                        ]
                    ),
                )
            )
            .order_by("position")
        )

    def get_permission_required(self):
        permission_map = {"list": "orga_list", "detail": "orga_view"}
        permission = permission_map.get(self.action, self.action)
        return self.model.get_perm(permission)

    def get_generic_title(self, instance=None):
        if instance:
            return (
                _("Track")
                + f" {phrases.base.quotation_open}{instance.name}{phrases.base.quotation_close}"
            )
        if self.action == "create":
            return _("New track")
        return _("Tracks")

    def delete_handler(self, request, *args, **kwargs):
        try:
            return super().delete_handler(request, *args, **kwargs)
        except ProtectedError:
            messages.error(
                request,
                _("This track is in use in a proposal and cannot be deleted."),
            )
            return self.delete_view(request, *args, **kwargs)


class AccessCodeView(OrderActionMixin, OrgaCRUDView):
    model = SubmitterAccessCode
    form_class = SubmitterAccessCodeForm
    table_class = SubmitterAccessCodeTable
    template_namespace = "orga/cfp"
    context_object_name = "access_code"
    lookup_field = "code"
    path_converter = "str"
    create_button_label = _("New access code")

    def get_queryset(self):
        return self.request.event.submitter_access_codes.all().order_by("valid_until")

    def get_generic_title(self, instance=None):
        if instance:
            return (
                _("Access code")
                + f" {phrases.base.quotation_open}{instance.code}{phrases.base.quotation_close}"
            )
        if self.action == "create":
            return _("New access code")
        return _("Access codes")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.action in ("detail", "update"):
            context["submissions"] = (
                self.object.submissions.all()
                .exclude(state__in=[SubmissionStates.DRAFT, SubmissionStates.DELETED])
                .prefetch_related("speakers")
            )
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if (track := self.request.GET.get("track")) and (
            track := self.request.event.tracks.filter(pk=track).first()
        ):
            kwargs["initial"] = kwargs.get("initial", {})
            kwargs["initial"]["track"] = track
        return kwargs

    def delete_handler(self, request, *args, **kwargs):
        try:
            return super().delete_handler(request, *args, **kwargs)
        except ProtectedError:
            messages.error(
                request,
                _(
                    "This access code has been used for a proposal and cannot be deleted. To disable it, you can set its validity date to the past."
                ),
            )
            return self.delete_view(request, *args, **kwargs)


class AccessCodeSend(PermissionRequired, UpdateView):
    model = SubmitterAccessCode
    form_class = AccessCodeSendForm
    context_object_name = "access_code"
    template_name = "orga/cfp/submitteraccesscode/send.html"
    permission_required = "submission.view_submitteraccesscode"

    def get_success_url(self) -> str:
        return self.request.event.cfp.urls.access_codes

    def get_object(self):
        return self.request.event.submitter_access_codes.filter(
            code__iexact=self.kwargs.get("code")
        ).first()

    @context
    def submit_buttons(self):
        return [send_button()]

    def get_permission_object(self):
        return self.get_object()

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["user"] = self.request.user
        return result

    def form_valid(self, form):
        result = super().form_valid(form)
        messages.success(self.request, _("The access code has been sent."))
        code = self.get_object()
        code.log_action(
            "pretalx.access_code.send",
            person=self.request.user,
            orga=True,
            data={"email": form.cleaned_data["to"]},
        )
        return result


@method_decorator(csp_update({"script-src": "'self' 'unsafe-eval'"}), name="dispatch")
class CfPFlowEditor(EventPermissionRequired, TemplateView):
    template_name = "orga/cfp/flow.html"
    permission_required = "event.update_event"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_configuration"] = self.request.event.cfp_flow.get_editor_config(
            json_compat=True
        )
        ctx["event_configuration"] = {
            "header_pattern": self.request.event.display_settings["header_pattern"]
            or "bg-primary",
            "header_image": (
                self.request.event.header_image.url
                if self.request.event.header_image
                else None
            ),
            "logo_image": (
                self.request.event.logo.url if self.request.event.logo else None
            ),
            "primary_color": self.request.event.visible_primary_color,
            "locales": self.request.event.locales,
        }
        return ctx

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body.decode())
        except Exception:
            return JsonResponse({"error": "Invalid data"}, status=400)

        flow = CfPFlow(self.request.event)
        if "action" in data and data["action"] == "reset":
            flow.reset()
        else:
            flow.save_config(data)
        return JsonResponse({"success": True})
