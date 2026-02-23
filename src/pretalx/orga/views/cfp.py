# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Jahongir Rahmonov  =)
# SPDX-FileContributor: Johan Van de Wauw

import json
from collections import defaultdict

from django.contrib import messages
from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.db.models.deletion import ProtectedError
from django.forms.models import inlineformset_factory
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView, UpdateView, View
from django_context_decorator import context
from i18nfield.strings import LazyI18nString

from pretalx.cfp.flow import CfPFlow, cfp_field_labels
from pretalx.common.forms import I18nFormSet
from pretalx.common.text.phrases import phrases
from pretalx.common.text.serialize import I18nStrJSONEncoder, serialize_i18n
from pretalx.common.ui import send_button
from pretalx.common.views.generic import OrgaCRUDView, get_next_url
from pretalx.common.views.mixins import (
    AsyncFileDownloadMixin,
    EventPermissionRequired,
    OrderActionMixin,
    PermissionRequired,
)
from pretalx.mail.models import MailTemplateRoles
from pretalx.orga.forms import CfPForm, QuestionForm, SubmissionTypeForm, TrackForm
from pretalx.orga.forms.cfp import (
    AccessCodeSendForm,
    AnswerOptionForm,
    CfPFieldConfigForm,
    CfPSettingsForm,
    QuestionFilterForm,
    ReminderFilterForm,
    StepHeaderForm,
    SubmitterAccessCodeForm,
)
from pretalx.orga.tables.cfp import (
    QuestionTable,
    SubmissionTypeTable,
    SubmitterAccessCodeTable,
    TrackTable,
)
from pretalx.orga.utils.i18n import has_i18n_content
from pretalx.person.forms import SpeakerProfileForm
from pretalx.submission.forms import InfoForm, QuestionsForm
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
from pretalx.submission.models.cfp import default_fields
from pretalx.submission.rules import questions_for_user
from pretalx.submission.tasks import export_question_files


class CfPTextDetail(PermissionRequired, UpdateView):
    form_class = CfPForm
    model = CfP
    template_name = "orga/cfp/text.html"
    permission_required = "event.update_event"
    write_permission_required = "event.update_event"

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
            if form.has_changed and not self.formset._should_delete_form(form)  # noqa: SLF001 -- Django formset internal
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
            old_data = old_obj.get_instance_data()

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
                new_data=form.instance.get_instance_data(),
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
            option = get_object_or_404(self.object.options, pk=pk)
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


class QuestionFileDownloadView(AsyncFileDownloadMixin, PermissionRequired, View):
    permission_required = "submission.orga_view_question"

    @cached_property
    def question(self):
        return Question.objects.filter(
            event=self.request.event, pk=self.kwargs.get("pk")
        ).first()

    def get_object(self):
        return self.question

    def get_permission_object(self):
        return self.question

    def get_async_download_filename(self):
        return f"{self.request.event.slug}_question_{self.question.pk}_files.zip"

    def get_error_redirect_url(self):
        return self.question.urls.base

    def start_async_task(self, cached_file):
        return export_question_files.apply_async(
            kwargs={
                "question_id": self.question.pk,
                "cached_file_id": str(cached_file.id),
            }
        )

    def get(self, request, *args, **kwargs):
        if not self.question or self.question.variant != "file":
            messages.error(request, _("This field does not support file downloads."))
            return redirect(request.event.cfp.urls.questions)
        return self.handle_async_download(request)


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
        submissions = submissions.filter(speakers=person)
        for question in questions:
            if question.target == QuestionTarget.SUBMISSION:
                for submission in submissions:
                    answer = question.answers.filter(submission=submission).first()
                    if not answer or not answer.is_answered:
                        missing.append(question)
            elif question.target == QuestionTarget.SPEAKER:
                answer = question.answers.filter(speaker=person).first()
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
        data = {"url": self.request.event.urls.user_submissions.full()}
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
                    person.user,
                    event=self.request.event,
                    context=data,
                    context_kwargs={"user": person.user},
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
                    "submissions", filter=~Q(submissions__state=SubmissionStates.DRAFT)
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
                    "submissions", filter=~Q(submissions__state=SubmissionStates.DRAFT)
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
                request, _("This track is in use in a proposal and cannot be deleted.")
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
        return (
            self.request.event.submitter_access_codes.all()
            .prefetch_related("tracks", "submission_types")
            .annotate(
                has_submissions=Exists(
                    self.request.event.submissions.filter(access_code=OuterRef("pk"))
                )
            )
            .order_by("valid_until")
        )

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
                .exclude(state=SubmissionStates.DRAFT)
                .with_sorted_speakers()
            )
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if (track := self.request.GET.get("track")) and (
            track := self.request.event.tracks.filter(pk=track).first()
        ):
            kwargs["initial"] = kwargs.get("initial", {})
            kwargs["initial"]["tracks"] = [track]
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


def get_field_label(field_key, model):
    if label := cfp_field_labels().get(field_key):
        return label
    try:
        field = model._meta.get_field(field_key)
    except FieldDoesNotExist:
        return field_key.replace("_", " ").title()
    else:
        return field.verbose_name


class CfPEditorMixin:
    @cached_property
    def flow(self):
        return self.request.event.cfp_flow

    @cached_property
    def auto_field_states(self):
        auto_hidden = {}
        auto_required = set()

        submission_type_count = self.request.event.submission_types.filter(
            requires_access_code=False
        ).count()
        if submission_type_count <= 1:
            auto_hidden["submission_type"] = _("only one option available")
        else:
            auto_required.add("submission_type")
        if len(self.request.event.content_locales) <= 1:
            auto_hidden["content_locale"] = _("only one language configured")
        if not self.request.event.get_feature_flag("use_tracks"):
            auto_hidden["track"] = _("tracks are disabled")
        elif not self.request.event.tracks.exists():
            auto_hidden["track"] = _("no tracks exist")
        if not self.request.event.tags.filter(is_public=True).exists():
            auto_hidden["tags"] = _("no public tags exist")

        return auto_hidden, auto_required

    @property
    def auto_hidden(self):
        return self.auto_field_states[0]

    @property
    def auto_required(self):
        return self.auto_field_states[1]

    def get_step_context(self, step_id):
        step = self.flow.steps_dict.get(step_id)
        if not step:
            return {"error": "Step not found", "step_id": step_id}

        step_config = self.flow.get_step_config(step_id)
        ctx = {
            "step_id": step_id,
            "step": step,
            "step_title": step_config.get("title", getattr(step, "_title", step.label)),
            "step_text": step_config.get("text", getattr(step, "_text", "")),
        }

        if step_id == CfPFlow.STEP_USER:
            ctx["is_static"] = True
            ctx["fields"] = []
            ctx["available_fields"] = []
        elif step_id == CfPFlow.STEP_QUESTIONS:
            ctx["is_questions"] = True
            ctx["fields"] = []
            ctx["available_fields"] = []
            for target, prefix in [
                (QuestionTarget.SUBMISSION, "submission"),
                (QuestionTarget.SPEAKER, "speaker"),
            ]:
                ctx[f"{prefix}_questions"] = self._get_questions_by_target(
                    target, active=True
                )
                ctx[f"inactive_{prefix}_questions"] = self._get_questions_by_target(
                    target, active=False
                )
        else:
            ctx["is_static"] = False
            ctx["fields"] = self._get_step_fields(step, step_config)
            ctx["available_fields"] = self._get_available_fields(step)
        return ctx

    def _get_step_fields(self, step, step_config):
        fields_config = step_config.get("fields", [])
        step_fields = getattr(step, "field_keys", [])
        always_required = getattr(step, "always_required_fields", set())
        auto_required = self.auto_required | always_required

        form = self._get_preview_form(step)
        ordered_keys = self._get_ordered_field_keys(
            fields_config, step_fields, always_required
        )

        result = []
        for key in ordered_keys:
            if key not in step_fields:
                continue
            field_data = self._build_field_data(
                key, fields_config, step, form, auto_required
            )
            if field_data:
                result.append(field_data)
        return result

    def _get_preview_form(self, step):
        if step.identifier == "info":
            return InfoForm(event=self.request.event, readonly=True)
        if step.identifier == "profile":
            return SpeakerProfileForm(event=self.request.event, read_only=True)
        return None

    def _get_ordered_field_keys(self, fields_config, step_fields, always_required=None):
        always_required = always_required or set()
        if fields_config:
            ordered_keys = [f.get("key") for f in fields_config if f.get("key")]
            for key in step_fields:
                if key not in ordered_keys:
                    if key in always_required:
                        ordered_keys.insert(0, key)
                    else:
                        ordered_keys.append(key)
        else:
            ordered_keys = list(step_fields)
        return ordered_keys

    def _build_field_data(self, key, fields_config, step, form, auto_required):
        auto_hidden_reason = self.auto_hidden.get(key)
        is_auto_required = key in auto_required

        cfp = self.request.event.cfp
        field_settings = cfp.fields.get(key, default_fields().get(key, {}))
        visibility = field_settings.get("visibility", "do_not_ask")

        if is_auto_required:
            visibility = "required"
        elif visibility == "do_not_ask" and not auto_hidden_reason:
            return None

        custom_config = next((f for f in fields_config if f.get("key") == key), {})
        custom_label = custom_config.get("label") or ""
        custom_help_text = custom_config.get("help_text") or ""

        if isinstance(custom_label, dict):
            custom_label = LazyI18nString(custom_label)
        if isinstance(custom_help_text, dict):
            custom_help_text = LazyI18nString(custom_help_text)

        label = (
            custom_label
            if has_i18n_content(custom_label)
            else get_field_label(key, step.label_model)
        )

        form_field = None
        if form and key in form.fields:
            form_field = form[key]
            if has_i18n_content(custom_label):
                form_field.label = custom_label
            if has_i18n_content(custom_help_text):
                form_field.help_text = custom_help_text

        return {
            "key": key,
            "label": label,
            "help_text": custom_help_text,
            "visibility": visibility,
            "min_length": field_settings.get("min_length"),
            "max_length": field_settings.get("max_length"),
            "max": field_settings.get("max"),
            "is_question": False,
            "form_field": form_field,
            "auto_hidden_reason": auto_hidden_reason,
            "is_auto_required": is_auto_required,
        }

    def _get_available_fields(self, step):
        always_required = getattr(step, "always_required_fields", set())
        step_fields = [
            f for f in getattr(step, "field_keys", []) if f not in always_required
        ]
        cfp = self.request.event.cfp
        result = []
        for key in step_fields:
            field_settings = cfp.fields.get(key, default_fields().get(key, {}))
            if field_settings.get("visibility", "do_not_ask") == "do_not_ask":
                result.append(
                    {
                        "key": key,
                        "label": get_field_label(key, step.label_model),
                        "is_question": False,
                    }
                )
        return result

    def _get_questions_by_target(self, target, active=True):
        manager = Question.objects if active else Question.all_objects
        questions = manager.filter(
            event=self.request.event, target=target, active=active
        ).order_by("position")

        form = None
        if active and questions.exists():
            form = QuestionsForm(event=self.request.event, target=target, readonly=True)

        result = []
        for question in questions:
            data = {
                "key": f"question_{question.pk}",
                "label": str(question.question),
                "is_question": True,
                "question_id": question.pk,
            }
            if active:
                data["help_text"] = (
                    str(question.help_text) if question.help_text else ""
                )
                data["visibility"] = "required" if question.required else "optional"
                field_name = f"question_{question.pk}"
                if form and field_name in form.fields:
                    data["form_field"] = form[field_name]
            result.append(data)
        return result


class CfPFlowEditor(CfPEditorMixin, EventPermissionRequired, TemplateView):
    template_name = "orga/cfp/editor.html"
    permission_required = "event.update_event"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["steps"] = [
            {
                "identifier": step.identifier,
                "label": step.label,
                "icon": step.icon,
                "is_static": step.identifier
                in (CfPFlow.STEP_USER, CfPFlow.STEP_QUESTIONS),
            }
            for step in self.flow.steps
            if step.identifier == CfPFlow.STEP_USER or hasattr(step, "form_class")
        ]
        active_step = self.request.GET.get("step", CfPFlow.STEP_INFO)
        ctx["active_step"] = active_step
        ctx.update(self.get_step_context(active_step))
        return ctx


class CfPEditorStep(CfPEditorMixin, EventPermissionRequired, TemplateView):
    template_name = "orga/cfp/editor.html"
    permission_required = "event.update_event"

    def get_template_names(self):
        if self.request.GET.get("edit_header") == "1":
            return [f"{self.template_name}#step-header-edit"]
        return [f"{self.template_name}#step-content-full"]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        step_id = self.kwargs["step"]

        form = StepHeaderForm(request.POST, event=request.event)
        if not form.is_valid():
            step = self.flow.steps_dict.get(step_id)
            ctx = self.get_context_data(**kwargs)
            ctx["step"] = step
            ctx["step_id"] = step_id
            ctx["form"] = form
            return render(request, "orga/cfp/editor.html#step-header-edit", ctx)

        title = form.cleaned_data.get("title", "")
        text = form.cleaned_data.get("text", "")
        self.flow.update_step_header(step_id, title, text)

        ctx = self.get_step_context(step_id)
        return render(request, "orga/cfp/editor.html#step-content-inner", ctx)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        step_id = self.kwargs["step"]

        if self.request.GET.get("edit_header") != "1":
            ctx.update(self.get_step_context(step_id))
            return ctx

        step = self.flow.steps_dict.get(step_id)
        if not step:
            ctx["error"] = "Step not found"
            return ctx

        step_config = self.flow.get_step_config(step_id)
        default_title = getattr(step, "_title", step.label)
        default_text = getattr(step, "_text", "")
        step_title = step_config.get("title", default_title)
        step_text = step_config.get("text", default_text)

        ctx["step"] = step
        ctx["step_id"] = step_id
        ctx["step_title"] = step_title
        ctx["step_text"] = step_text
        ctx["default_title"] = default_title
        ctx["default_text"] = default_text
        ctx["form"] = StepHeaderForm(
            initial={
                "title": step_title if step_title != default_title else "",
                "text": step_text if step_text != default_text else "",
            },
            event=self.request.event,
        )
        return ctx


class CfPEditorReorder(EventPermissionRequired, View):
    permission_required = "event.update_event"

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        step_id = self.kwargs["step"]
        order = request.POST.get("order", "")

        if not order:
            return JsonResponse({"error": "No order provided"}, status=400)

        field_order = order.split(",")

        if step_id in (
            CfPFlow.STEP_QUESTIONS_SUBMISSION,
            CfPFlow.STEP_QUESTIONS_SPEAKER,
        ):
            target = (
                QuestionTarget.SUBMISSION
                if step_id == CfPFlow.STEP_QUESTIONS_SUBMISSION
                else QuestionTarget.SPEAKER
            )
            for index, key in enumerate(field_order):
                if key.startswith("question_"):
                    question_id_str = key.replace("question_", "")
                    try:
                        question_id = int(question_id_str)
                    except ValueError:
                        continue
                    try:
                        question = Question.objects.get(
                            pk=question_id, event=request.event, target=target
                        )
                        question.position = index
                        question.save(update_fields=["position"])
                    except Question.DoesNotExist:
                        pass
            return JsonResponse({"success": True})

        request.event.cfp_flow.update_field_order(step_id, field_order)
        return JsonResponse({"success": True})


class CfPEditorFieldToggle(CfPEditorMixin, EventPermissionRequired, View):
    permission_required = "event.update_event"

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        step_id = self.kwargs["step"]
        action = self.kwargs["action"]
        field_key = request.POST.get("field")

        if not field_key:
            return JsonResponse({"error": "No field provided"}, status=400)

        if action not in ("add", "remove"):
            return JsonResponse({"error": "Invalid action"}, status=400)

        if field_key.startswith("question_"):
            question_id = field_key.replace("question_", "")
            manager = Question.all_objects if action == "add" else Question.objects
            try:
                question = manager.get(pk=question_id, event=request.event)
                question.active = action == "add"
                question.save()
            except Question.DoesNotExist:
                return JsonResponse({"error": "Question not found"}, status=404)
        else:
            if field_key not in default_fields():
                return JsonResponse({"error": "Invalid field key"}, status=400)

            cfp = request.event.cfp
            if field_key not in cfp.fields:
                cfp.fields[field_key] = default_fields().get(field_key, {}).copy()

            cfp.fields[field_key]["visibility"] = (
                "optional" if action == "add" else "do_not_ask"
            )
            cfp.save()

        ctx = self.get_step_context(step_id)
        return render(request, "orga/cfp/editor.html#step-content-full", ctx)


class CfPEditorField(CfPEditorMixin, EventPermissionRequired, TemplateView):
    template_name = "orga/cfp/editor.html#field-modal"
    permission_required = "event.update_event"

    def dispatch(self, request, *args, **kwargs):
        field_key = kwargs.get("field_key")
        if field_key not in default_fields():
            return JsonResponse({"error": "Invalid field key"}, status=404)
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def step_id(self):
        return self.kwargs["step"]

    @cached_property
    def field_key(self):
        return self.kwargs["field_key"]

    @cached_property
    def step(self):
        return self.flow.steps_dict.get(self.step_id)

    @cached_property
    def field_label(self):
        if self.step:
            return get_field_label(self.field_key, self.step.label_model)
        return self.field_key

    def _build_form_initial(self):
        cfp = self.request.event.cfp
        field_settings = cfp.fields.get(
            self.field_key, default_fields().get(self.field_key, {})
        )
        custom_config = self.flow.get_field_config(self.step_id, self.field_key)

        return {
            "label": custom_config.get("label", ""),
            "help_text": custom_config.get("help_text", ""),
            "visibility": field_settings.get("visibility", "optional"),
            "min_length": field_settings.get("min_length"),
            "max_length": field_settings.get("max_length"),
            "max": field_settings.get("max"),
            "min_number": field_settings.get("min"),
            "max_number": field_settings.get("max"),
        }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["step_id"] = self.step_id
        ctx["field_key"] = self.field_key
        ctx["field_label"] = self.field_label
        ctx["form"] = CfPFieldConfigForm(
            initial=self._build_form_initial(),
            field_key=self.field_key,
            event=self.request.event,
        )
        return ctx

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        cfp = request.event.cfp
        form = CfPFieldConfigForm(
            request.POST, field_key=self.field_key, event=request.event
        )

        if not form.is_valid():
            ctx = {
                "step_id": self.step_id,
                "field_key": self.field_key,
                "field_label": self.field_label,
                "form": form,
            }
            return render(request, "orga/cfp/editor.html#field-modal", ctx)

        if self.field_key not in cfp.fields:
            cfp.fields[self.field_key] = default_fields().get(self.field_key, {}).copy()

        cfp.fields[self.field_key]["visibility"] = form.cleaned_data["visibility"]

        if "min_length" in form.fields:
            cfp.fields[self.field_key]["min_length"] = form.cleaned_data.get(
                "min_length"
            )
        if "max_length" in form.fields:
            cfp.fields[self.field_key]["max_length"] = form.cleaned_data.get(
                "max_length"
            )
        if "max" in form.fields:
            cfp.fields[self.field_key]["max"] = form.cleaned_data.get("max")
        if "min_number" in form.fields:
            cfp.fields[self.field_key]["min"] = form.cleaned_data.get("min_number")
        if "max_number" in form.fields:
            cfp.fields[self.field_key]["max"] = form.cleaned_data.get("max_number")

        cfp.save()

        label = serialize_i18n(form.cleaned_data.get("label", ""))
        help_text = serialize_i18n(form.cleaned_data.get("help_text", ""))
        self.flow.update_field_config(self.step_id, self.field_key, label, help_text)

        ctx = self.get_step_context(self.step_id)
        response = render(request, "orga/cfp/editor.html#step-content-inner", ctx)
        response["HX-Trigger"] = "closeModal"
        return response


class CfPEditorQuestion(EventPermissionRequired, TemplateView):
    template_name = "orga/cfp/editor.html#question-modal"
    permission_required = "event.update_event"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        question_id = self.kwargs["question_id"]

        question = get_object_or_404(
            Question.objects.filter(event=self.request.event), pk=question_id
        )

        ctx["question"] = question
        return ctx


class CfPEditorReset(EventPermissionRequired, View):
    permission_required = "event.update_event"

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        flow = request.event.cfp_flow
        flow.reset()
        cfp = request.event.cfp
        cfp.fields = default_fields()
        cfp.save()
        messages.success(request, _("CfP configuration has been reset to defaults."))
        return redirect(request.event.cfp.urls.editor)
