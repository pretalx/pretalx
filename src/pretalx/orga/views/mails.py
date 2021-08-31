from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, ListView, TemplateView, View
from django_context_decorator import context

from pretalx.common.mail import TolerantDict
from pretalx.common.mixins.views import (
    ActionFromUrl,
    EventPermissionRequired,
    Filterable,
    PermissionRequired,
    Sortable,
)
from pretalx.common.templatetags.rich_text import rich_text
from pretalx.common.utils import language
from pretalx.common.views import CreateOrUpdateView
from pretalx.mail.models import MailTemplate, QueuedMail
from pretalx.orga.forms.mails import MailDetailForm, MailTemplateForm, WriteMailForm


class OutboxList(EventPermissionRequired, Sortable, Filterable, ListView):
    model = QueuedMail
    context_object_name = "mails"
    template_name = "orga/mails/outbox_list.html"
    default_filters = (
        "to__icontains",
        "subject__icontains",
        "to_users__name__icontains",
        "to_users__email__icontains",
    )
    sortable_fields = ("to", "subject")
    paginate_by = 25
    permission_required = "orga.view_mails"

    def get_queryset(self):
        qs = (
            self.request.event.queued_mails.prefetch_related("to_users")
            .filter(sent__isnull=True)
            .order_by("-id")
        )
        qs = self.filter_queryset(qs)
        qs = self.sort_queryset(qs)
        return qs


class SentMail(EventPermissionRequired, Sortable, Filterable, ListView):
    model = QueuedMail
    context_object_name = "mails"
    template_name = "orga/mails/sent_list.html"
    default_filters = (
        "to__icontains",
        "subject__icontains",
        "to_users__name__icontains",
        "to_users__email__icontains",
    )
    sortable_fields = ("to", "subject", "sent")
    paginate_by = 25
    permission_required = "orga.view_mails"

    def get_queryset(self):
        qs = (
            self.request.event.queued_mails.prefetch_related("to_users")
            .filter(sent__isnull=False)
            .order_by("-sent")
        )
        qs = self.filter_queryset(qs)
        qs = self.sort_queryset(qs)
        return qs


class OutboxSend(EventPermissionRequired, TemplateView):
    permission_required = "orga.send_mails"
    template_name = "orga/mails/confirm.html"

    @context
    def question(self):
        return _("Do you really want to send {count} mails?").format(
            count=self.queryset.count()
        )

    def dispatch(self, request, *args, **kwargs):
        if "pk" in self.kwargs:
            try:
                mail = self.request.event.queued_mails.get(pk=self.kwargs.get("pk"))
            except QueuedMail.DoesNotExist:
                messages.error(
                    request,
                    _(
                        "This mail either does not exist or cannot be discarded because it was sent already."
                    ),
                )
                return redirect(self.request.event.orga_urls.outbox)
            if mail.sent:
                messages.error(request, _("This mail had been sent already."))
            else:
                mail.send(requestor=self.request.user)
                messages.success(request, _("The mail has been sent."))
            return redirect(self.request.event.orga_urls.outbox)
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def queryset(self):
        qs = self.request.event.queued_mails.filter(sent__isnull=True)
        pks = self.request.GET.get("pks") or ""
        if pks:
            pks = pks.split(",")
            qs = qs.filter(pk__in=pks)
        return qs

    def post(self, request, *args, **kwargs):
        qs = self.queryset
        count = qs.count()
        for mail in qs:
            mail.send(requestor=self.request.user)
        messages.success(
            request, _("{count} mails have been sent.").format(count=count)
        )
        return redirect(self.request.event.orga_urls.outbox)


class MailDelete(PermissionRequired, TemplateView):
    permission_required = "orga.purge_mails"
    template_name = "orga/mails/confirm.html"

    def get_permission_object(self):
        return self.request.event

    @context
    def question(self):
        return _("Do you really want to delete this mail?")

    def post(self, request, *args, **kwargs):
        try:
            mail = self.request.event.queued_mails.get(
                sent__isnull=True, pk=self.kwargs.get("pk")
            )
        except QueuedMail.DoesNotExist:
            messages.error(
                request,
                _(
                    "This mail either does not exist or cannot be discarded because it was sent already."
                ),
            )
            return redirect(self.request.event.orga_urls.outbox)
        mail.log_action("pretalx.mail.delete", person=self.request.user, orga=True)
        mail.delete()
        messages.success(request, _("The mail has been deleted."))
        return redirect(request.event.orga_urls.outbox)


class OutboxPurge(PermissionRequired, TemplateView):
    permission_required = "orga.purge_mails"
    template_name = "orga/mails/confirm.html"

    def get_permission_object(self):
        return self.request.event

    @context
    def question(self):
        return _("Do you really want to purge {count} mails?").format(
            count=self.queryset.count()
        )

    @cached_property
    def queryset(self):
        qs = self.request.event.queued_mails.filter(sent__isnull=True)
        return qs

    def post(self, request, *args, **kwargs):
        qs = self.queryset
        count = qs.count()
        qs.delete()
        messages.success(
            request, _("{count} mails have been purged.").format(count=count)
        )
        return redirect(self.request.event.orga_urls.outbox)


class MailDetail(PermissionRequired, ActionFromUrl, CreateOrUpdateView):
    model = QueuedMail
    form_class = MailDetailForm
    template_name = "orga/mails/outbox_form.html"
    write_permission_required = "orga.edit_mails"
    permission_required = "orga.view_mails"

    def get_object(self) -> QueuedMail:
        return self.request.event.queued_mails.filter(pk=self.kwargs.get("pk")).first()

    def get_success_url(self):
        return self.object.event.orga_urls.outbox

    def form_valid(self, form):
        form.instance.event = self.request.event
        result = super().form_valid(form)
        if form.has_changed():
            action = "pretalx.mail." + ("update" if self.object else "create")
            form.instance.log_action(action, person=self.request.user, orga=True)
        action = form.data.get("form", "save")
        if action == "send":
            form.instance.send()
            messages.success(self.request, _("The email has been sent."))
        else:  # action == 'save'
            messages.success(
                self.request,
                _(
                    "The email has been saved. When you send it, the updated text will be used."
                ),
            )
        return result


class MailCopy(PermissionRequired, View):
    permission_required = "orga.send_mails"

    def get_object(self) -> QueuedMail:
        return get_object_or_404(
            self.request.event.queued_mails, pk=self.kwargs.get("pk")
        )

    def dispatch(self, request, *args, **kwargs):
        mail = self.get_object()
        new_mail = mail.copy_to_draft()
        messages.success(request, _("The mail has been copied, you can edit it now."))
        return redirect(new_mail.urls.edit)


class ComposeMail(EventPermissionRequired, FormView):
    form_class = WriteMailForm
    template_name = "orga/mails/send_form.html"
    permission_required = "orga.send_mails"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        initial = kwargs.get("initial", {})
        if "template" in self.request.GET:
            template = MailTemplate.objects.filter(
                pk=self.request.GET.get("template")
            ).first()
            if template:
                initial["subject"] = template.subject
                initial["text"] = template.text
                initial["reply_to"] = template.reply_to
        if "submission" in self.request.GET:
            submission = self.request.event.submissions.filter(
                code=self.request.GET.get("submission")
            ).first()
            if submission:
                initial["submissions"] = submission.code
        if "email" in self.request.GET:
            initial["additional_recipients"] = self.request.GET.get("email")
        kwargs["initial"] = initial
        return kwargs

    def get_success_url(self):
        return self.request.event.orga_urls.compose_mails

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx["output"] = getattr(self, "output", None)
        ctx["mail_count"] = getattr(self, "mail_count", None)
        return ctx

    def form_valid(self, form):
        preview = self.request.POST.get("action") == "preview"
        if preview:
            self.output = {}
            # Only approximate, good enough. Doesn't run deduplication, so it doesn't have to
            # run rendering for all placeholders for all people, either.
            result = form.get_recipient_submissions()
            if not len(result):
                messages.error(
                    self.request,
                    _("There are no proposals or sessions matching this selection."),
                )
                return self.get(self.request, *self.args, **self.kwargs)
            for locale in self.request.event.locales:
                with language(locale):
                    context_dict = TolerantDict()
                    for k, v in form.get_valid_placeholders().items():
                        context_dict[
                            k
                        ] = '<span class="placeholder" title="{}">{}</span>'.format(
                            _(
                                "This value will be replaced based on dynamic parameters."
                            ),
                            v.render_sample(self.request.event),
                        )

                    subject = bleach.clean(
                        form.cleaned_data["subject"].localize(locale), tags=[]
                    )
                    preview_subject = subject.format_map(context_dict)
                    message = form.cleaned_data["text"].localize(locale)
                    preview_text = rich_text(message.format_map(context_dict))

                    self.output[locale] = {
                        "subject": _("Subject: {subject}").format(
                            subject=preview_subject
                        ),
                        "html": preview_text,
                    }
                    self.mail_count = len(result)
            return self.get(self.request, *self.args, **self.kwargs)

        result = form.save()
        messages.success(
            self.request,
            _(
                "{count} emails have been saved to the outbox – you can make individual changes there or just send them all."
            ).format(count=len(result)),
        )
        return super().form_valid(form)


class TemplateList(EventPermissionRequired, TemplateView):
    template_name = "orga/mails/template_list.html"
    permission_required = "orga.view_mail_templates"

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        accept = self.request.event.accept_template
        ack = self.request.event.ack_template
        reject = self.request.event.reject_template
        update = self.request.event.update_template
        remind = self.request.event.question_template
        result["accept"] = MailTemplateForm(
            instance=accept, read_only=True, event=self.request.event
        )
        result["ack"] = MailTemplateForm(
            instance=ack, read_only=True, event=self.request.event
        )
        result["reject"] = MailTemplateForm(
            instance=reject, read_only=True, event=self.request.event
        )
        result["update"] = MailTemplateForm(
            instance=update, read_only=True, event=self.request.event
        )
        result["remind"] = MailTemplateForm(
            instance=remind, read_only=True, event=self.request.event
        )
        pks = [
            template.pk if template else None
            for template in [accept, ack, reject, update, remind]
        ]
        result["other"] = [
            MailTemplateForm(
                instance=template, read_only=True, event=self.request.event
            )
            for template in self.request.event.mail_templates.exclude(
                pk__in=[pk for pk in pks if pk]
            ).exclude(is_auto_created=True)
        ]
        return result


class TemplateDetail(PermissionRequired, ActionFromUrl, CreateOrUpdateView):
    model = MailTemplate
    form_class = MailTemplateForm
    template_name = "orga/mails/template_form.html"
    permission_required = "orga.view_mail_templates"
    write_permission_required = "orga.edit_mail_templates"

    @context
    def placeholders(self):
        template = self.object
        if template and template in template.event.fixed_templates:
            result = {}
            if template == template.event.update_template:
                result = [item for item in result if item["name"] == "event_name"]
                result.append(
                    {
                        "name": "notifications",
                        "explanation": _("A list of notifications for this speaker"),
                    }
                )
            elif template == template.event.question_template:
                result = [item for item in result if item["name"] in ["event_name"]]
                result.append(
                    {
                        "name": "url",
                        "explanation": _("The link to the user's list of proposals"),
                    }
                )
                result.append(
                    {
                        "name": "questions",
                        "explanation": _(
                            "The list of questions that the user has not answered, as bullet points"
                        ),
                    }
                )
            return result
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        return kwargs

    def get_object(self) -> MailTemplate:
        return MailTemplate.objects.filter(
            event=self.request.event, pk=self.kwargs.get("pk"), is_auto_created=False
        ).first()

    @cached_property
    def object(self):
        return self.get_object()

    @property
    def permission_object(self):
        return self.object or self.request.event

    def get_permission_object(self):
        return self.permission_object

    def get_success_url(self):
        return self.request.event.orga_urls.mail_templates

    def form_valid(self, form):
        form.instance.event = self.request.event
        if form.has_changed():
            action = "pretalx.mail_template." + ("update" if self.object else "create")
            form.instance.log_action(action, person=self.request.user, orga=True)
        messages.success(
            self.request,
            "The template has been saved - note that already pending emails that are based on this template will not be changed!",
        )
        return super().form_valid(form)


class TemplateDelete(PermissionRequired, View):
    permission_required = "orga.edit_mail_templates"

    def get_object(self) -> MailTemplate:
        return get_object_or_404(
            MailTemplate.objects.all(),
            event=self.request.event,
            pk=self.kwargs.get("pk"),
        )

    def dispatch(self, request, *args, **kwargs):
        super().dispatch(request, *args, **kwargs)
        template = self.get_object()
        template.log_action(
            "pretalx.mail_template.delete", person=self.request.user, orga=True
        )
        template.delete()
        messages.success(request, "The template has been deleted.")
        return redirect(request.event.orga_urls.mail_templates)
