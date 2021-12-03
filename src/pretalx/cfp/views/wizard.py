import logging

from csp.decorators import csp_update
from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View

from pretalx.cfp.views.event import EventPageMixin
from pretalx.common.exceptions import SendMailException
from pretalx.common.phrases import phrases
from pretalx.mail.models import MailTemplate


class SubmitStartView(EventPageMixin, View):
    @staticmethod
    def get(request, *args, **kwargs):
        url = reverse(
            "cfp:event.submit",
            kwargs={
                "event": request.event.slug,
                "step": list(request.event.cfp_flow.steps_dict.keys())[0],
                "tmpid": get_random_string(length=6),
            },
        )
        if request.GET:
            url += f"?{request.GET.urlencode()}"
        return redirect(url)


@method_decorator(csp_update(IMG_SRC="https://www.gravatar.com"), name="dispatch")
class SubmitWizard(EventPageMixin, View):
    @transaction.atomic
    def dispatch(self, request, *args, **kwargs):
        self.event = self.request.event
        request.access_code = None
        if "access_code" in request.GET:
            access_code = request.event.submitter_access_codes.filter(
                code__iexact=request.GET["access_code"]
            ).first()
            if access_code and access_code.is_valid:
                request.access_code = access_code
        if not request.event.cfp.is_open and not request.access_code:
            messages.error(request, phrases.cfp.submissions_closed)
            return redirect(
                reverse("cfp:event.start", kwargs={"event": request.event.slug})
            )
        for step in request.event.cfp_flow.steps:
            if not step.is_applicable(request):
                continue
            if step.identifier == kwargs["step"]:
                break
            step.is_before = True
            step.resolved_url = step.get_step_url(request)
        if getattr(step, "is_before", False):  # The current step URL is incorrect
            raise Http404()
        handler = getattr(step, request.method.lower(), self.http_method_not_allowed)
        result = handler(request)
        if request.method == "GET" or (
            step.get_next_applicable(request) or not step.is_completed(request)
        ):
            return result
        return self.done(request)

    def done(self, request):
        # We are done, or at least we finished the last step. Time to check results.
        valid_steps = []
        for step in request.event.cfp_flow.steps:
            if step.is_applicable(request):
                if not step.is_completed(request):
                    return redirect(step.get_step_url(request))
                valid_steps.append(step)

        # We are done, or at least the data checks out. Time to save results.
        request.event.cfp_flow.steps_dict["user"].done(request)
        for step in valid_steps:
            if not step.identifier == "user":
                step.done(request)

        try:
            request.event.ack_template.to_mail(
                user=request.user,
                event=request.event,
                context_kwargs={"user": request.user, "submission": request.submission},
                skip_queue=True,
                locale=request.submission.get_email_locale(request.user.locale),
                full_submission_content=True,
            )
            if request.event.mail_settings["mail_on_new_submission"]:
                MailTemplate(
                    event=request.event,
                    subject=str(_("New proposal: {title}")).format(
                        title=request.submission.title
                    ),
                    text=request.event.settings.mail_text_new_submission,
                ).to_mail(
                    user=request.event.email,
                    event=request.event,
                    context_kwargs={
                        "user": request.user,
                        "submission": request.submission,
                    },
                    context={"orga_url": request.submission.orga_urls.base.full()},
                    skip_queue=True,
                    locale=request.event.locale,
                )
        except SendMailException as exception:
            logging.getLogger("").warning(str(exception))
            messages.warning(request, phrases.cfp.submission_email_fail)

        return redirect(
            reverse("cfp:event.user.submissions", kwargs={"event": request.event.slug})
        )
