# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from pretalx.common.views.redirect import get_login_redirect
from pretalx.person.domain.verification import (
    KIND_CHANGE,
    KIND_VERIFY,
    AlreadyVerifiedError,
    ExpiredVerificationTokenError,
    InvalidVerificationTokenError,
    PendingEmailExpiredError,
    PendingEmailTakenError,
    SendCooldownError,
    confirm_verification,
    correct_unverified_email,
    parse_verification_token,
    pending_email_expired,
    send_cooldown_remaining,
    send_verification_mail,
)
from pretalx.person.enums import EmailVerificationState
from pretalx.person.interfaces.forms import EmailCorrectionForm


class GenericVerificationView(TemplateView):
    orga = False

    @cached_property
    def event(self):
        return getattr(self.request, "event", None)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return get_login_redirect(request)
        if request.user.email_verification_state != EmailVerificationState.UNVERIFIED:
            next_url = request.session.pop("verification_next", None)
            return redirect(next_url or self.get_verified_url())
        return super().dispatch(request, *args, **kwargs)

    def get_verified_url(self):
        raise NotImplementedError

    @cached_property
    def cooldown(self):
        return send_cooldown_remaining(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("form", EmailCorrectionForm(user=self.request.user))
        context["cooldown"] = self.cooldown
        context["acknowledged_submission"] = self.request.session.pop(
            "verification_submission", None
        )
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "resend":
            return self._resend()
        return self._correct()

    def _resend(self):
        try:
            send_verification_mail(
                self.request.user, KIND_VERIFY, event=self.event, orga=self.orga
            )
        except SendCooldownError as error:
            messages.error(self.request, error.message)
        else:
            messages.success(
                self.request,
                _("We have sent you an email with a fresh confirmation link."),
            )
        return redirect(self.request.path)

    def _correct(self):
        form = EmailCorrectionForm(self.request.POST, user=self.request.user)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        try:
            correct_unverified_email(
                self.request.user,
                form.cleaned_data["email"],
                event=self.event,
                orga=self.orga,
            )
        except SendCooldownError as error:
            form.add_error(None, error.message)
            return self.render_to_response(self.get_context_data(form=form))
        except PendingEmailTakenError:
            # Address registered concurrently since form validation
            form.add_error(
                "email",
                _("There already exists an account for this email address.")
                + " "
                + _("Please choose a different email address."),
            )
            return self.render_to_response(self.get_context_data(form=form))
        messages.success(
            self.request,
            _(
                "We have updated your email address and sent a confirmation "
                "link to the new address."
            ),
        )
        return redirect(self.request.path)


class GenericVerifyView(TemplateView):
    def resolve_token(self):
        try:
            user, kind = parse_verification_token(self.kwargs["token"])
        except ExpiredVerificationTokenError:
            return None, None, "expired"
        except InvalidVerificationTokenError:
            return None, None, "invalid"
        if kind == KIND_CHANGE and pending_email_expired(user):
            return user, kind, "pending_expired"
        if (
            kind == KIND_VERIFY
            and user.email_verification_state == EmailVerificationState.VERIFIED
        ):
            return user, kind, "already_verified"
        return user, kind, None

    def get_success_url(self, user):
        raise NotImplementedError

    def get_verification_page_url(self):
        raise NotImplementedError

    def render_result(self, user, kind, error):
        target_email = None
        if user and not error:
            target_email = user.pending_email if kind == KIND_CHANGE else user.email
        context = self.get_context_data(
            error=error, kind=kind, target_email=target_email
        )
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["verification_page_url"] = self.get_verification_page_url()
        return context

    def get(self, request, *args, **kwargs):
        return self.render_result(*self.resolve_token())

    def post(self, request, *args, **kwargs):
        try:
            user, kind = confirm_verification(self.kwargs["token"])
        except ExpiredVerificationTokenError:
            return self.render_result(None, None, "expired")
        except InvalidVerificationTokenError:
            return self.render_result(None, None, "invalid")
        except PendingEmailExpiredError:
            return self.render_result(None, None, "pending_expired")
        except PendingEmailTakenError:
            return self.render_result(None, None, "taken")
        except AlreadyVerifiedError:
            return self.render_result(None, None, "already_verified")
        if kind == KIND_CHANGE:
            messages.success(
                request, _("Your new email address is confirmed and active now.")
            )
        else:
            messages.success(request, _("Your email address is now verified."))
        return redirect(self.get_success_url(user))
