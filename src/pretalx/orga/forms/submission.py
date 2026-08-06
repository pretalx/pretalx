# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override

from pretalx.common.forms.renderers import InlineFormLabelRenderer
from pretalx.common.forms.widgets import EnhancedSelect, SpeakerSearchSelect
from pretalx.common.text.formatting import format_map
from pretalx.common.text.phrases import phrases
from pretalx.mail.domain.context import get_mail_context
from pretalx.mail.domain.placeholders import placeholders_for_role
from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles
from pretalx.mail.validators import validate_invitation_text
from pretalx.person.domain.profile import create_speaker_profile, send_speaker_invite
from pretalx.person.domain.queries.profile import speaker_by_email
from pretalx.person.models import SpeakerProfile
from pretalx.submission.domain.submission import add_speaker, notify_speaker_added


class SubmissionStateChangeForm(forms.Form):
    pending = forms.BooleanField(
        label=_("Mark the new state as “pending”"),
        help_text=_(
            "If you mark state changes as pending, they will not be visible to speakers right away. You can always apply pending changes for some or all proposals in one go once you are ready to make your decisions public."
        ),
        required=False,
        initial=False,
    )


class RemoveSpeakerForm(forms.Form):
    delete_profile = forms.BooleanField(
        label=_("Delete this speaker"),
        help_text=_(
            "You are removing this speaker from their only session. Deleting the profile permanently removes everything recorded about this speaker, including emails sent to them. This action cannot be undone."
        ),
        required=False,
    )

    def __init__(self, *args, can_delete_profile=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not can_delete_profile:
            self.fields.pop("delete_profile")


class AddSpeakerForm(forms.Form):
    """
    The speaker search submits profile:<code> for a picked event profile,
    a plain email address for a cross-event account pick, or nothing; typed
    email addresses travel in the email field instead.
    """

    speaker = forms.CharField(
        label=_("Name"), required=False, widget=SpeakerSearchSelect
    )
    name = forms.CharField(label=_("Name"), required=False)
    email = forms.EmailField(label=phrases.cfp.speaker_email, required=False)
    confirm_email_less = forms.BooleanField(
        label=_("Add this speaker without an email address"),
        help_text=_(
            "Without an email address, the speaker will not receive schedule updates or any other notifications."
        ),
        required=False,
    )
    send_invite = forms.BooleanField(
        label=_("Send invitation"),
        help_text=_(
            "Invite the speaker to claim their profile and manage it themselves. Without an invitation, the speaker remains managed by you: they cannot log in to see or edit their proposals, and you maintain their profile for them."
        ),
        required=False,
        initial=False,
    )
    invite_subject = forms.CharField(label=_("Subject"), required=False)
    invite_text = forms.CharField(
        label=_("Text"), required=False, widget=forms.Textarea
    )
    locale = forms.ChoiceField(
        label=_("Invite language"),
        choices=[],
        required=False,
        help_text=_(
            "The language in which the speaker will receive their invitation email."
        ),
        widget=EnhancedSelect,
    )

    def __init__(
        self,
        *args,
        event=None,
        submission=None,
        form_renderer=None,
        standalone=False,
        **kwargs,
    ):
        self.created_profile = False
        super().__init__(*args, **kwargs)
        self.event = event
        self.submission = submission
        self.standalone = standalone
        self.fields["speaker"].widget.remote_url = event.orga_urls.speaker_search
        if standalone:
            self.fields["speaker"].widget.attrs["data-existing-selectable"] = "false"
            self.fields["speaker"].widget.attrs["data-existing-note"] = _(
                "This speaker already exists."
            )
            self.fields["send_invite"].initial = True
        if not event.named_locales or len(event.named_locales) < 2:
            self.fields.pop("locale")
        else:
            self.fields["locale"].choices = event.named_locales
            self.fields["locale"].initial = event.locale
        self.invite_role = (
            MailTemplateRoles.STANDALONE_SPEAKER_INVITE
            if standalone
            else MailTemplateRoles.NEW_SPEAKER_INVITE
        )
        self.invite_template = mail_template_by_role(event, self.invite_role)
        if not self.is_bound:
            initial = self.invite_template_variants.get(
                event.locale
            ) or self._render_invite(event.locale)
            self.fields["invite_subject"].initial = initial["subject"]
            self.fields["invite_text"].initial = initial["text"]

    def _render_invite(self, locale):
        context_kwargs = {"event": self.event}
        if self.submission:
            context_kwargs["submission"] = self.submission
        with override(locale):
            context = get_mail_context(**context_kwargs)
            return {
                "subject": str(
                    format_map(
                        str(self.invite_template.subject),
                        context,
                        raise_on_missing=False,
                    )
                ),
                "text": str(
                    format_map(
                        str(self.invite_template.text), context, raise_on_missing=False
                    )
                ),
            }

    @cached_property
    def invite_template_variants(self):
        return {
            locale: self._render_invite(locale)
            for locale, __ in self.event.named_locales
        }

    @cached_property
    def invite_placeholders(self):
        return placeholders_for_role(self.event, self.invite_role)

    def clean_speaker(self):
        value = (self.cleaned_data.get("speaker") or "").strip()
        if not value:
            return None
        if value.startswith("profile:"):
            if self.standalone:
                raise forms.ValidationError(_("This speaker already exists."))
            code = value.removeprefix("profile:")
            profile = SpeakerProfile.objects.filter(
                event=self.event, code__iexact=code
            ).first()
            if not profile:
                raise forms.ValidationError(
                    _("This speaker profile does not exist (anymore).")
                )
            return profile
        return forms.EmailField().clean(value)

    def clean(self):
        data = super().clean()
        speaker = data.get("speaker")
        if isinstance(speaker, SpeakerProfile):
            if speaker.is_managed and data.get("send_invite"):
                if not speaker.effective_email:
                    self.add_error(
                        "send_invite",
                        _(
                            "This speaker has no contact email address, so no invitation can be sent."
                        ),
                    )
                else:
                    self._validate_invite_text(data)
            return data
        # speaker must be an email address
        if speaker:
            data["email"] = speaker
        if data.get("email"):
            if data.get("send_invite"):
                self._validate_invite_text(data)
        elif data.get("name") and not data.get("confirm_email_less"):
            self.add_error(
                "confirm_email_less",
                _(
                    "You have not provided an email address for this speaker, so they cannot be invited or notified. Please confirm that you want to add them anyway."
                ),
            )
        return data

    def _validate_invite_text(self, data):
        for field in ("invite_subject", "invite_text"):
            value = data.get(field)
            if not value:
                self.add_error(
                    field, _("Please provide a text for the invitation email.")
                )
                continue
            try:
                validate_invitation_text(
                    value,
                    self.invite_placeholders,
                    require_invitation_link=field == "invite_text",
                )
            except forms.ValidationError as error:
                self.add_error(field, error)

    @property
    def has_speaker_data(self):
        if not hasattr(self, "cleaned_data"):
            return False
        data = self.cleaned_data
        return bool(data.get("speaker") or data.get("email") or data.get("name"))

    def _resolve_speaker(self, user):
        data = self.cleaned_data
        speaker = data.get("speaker")
        if isinstance(speaker, SpeakerProfile):
            return speaker
        if (email := data.get("email")) and (
            existing := speaker_by_email(self.event, email)
        ):
            return existing
        self.created_profile = True
        return create_speaker_profile(
            self.event,
            name=data.get("name") or None,
            email=data.get("email") or None,
            locale=data.get("locale") or None,
            log_user=user,
        )

    def _send_invite_if_requested(self, speaker, *, submission=None, user=None):
        data = self.cleaned_data
        if data.get("send_invite") and speaker.is_managed and speaker.effective_email:
            send_speaker_invite(
                speaker,
                subject=data.get("invite_subject"),
                text=data.get("invite_text"),
                submission=submission,
                log_user=user,
            )

    def add_speaker_to(self, submission, *, user=None):
        if not self.has_speaker_data:
            return None
        speaker = self._resolve_speaker(user)
        add_speaker(submission, speaker, log_user=user)
        if speaker.user_id:
            notify_speaker_added(
                submission, speaker, locale=self.cleaned_data.get("locale") or None
            )
        else:
            self._send_invite_if_requested(speaker, submission=submission, user=user)
        return speaker

    def create_speaker(self, *, user=None):
        if not self.has_speaker_data:
            return None
        speaker = self._resolve_speaker(user)
        self._send_invite_if_requested(speaker, user=user)
        return speaker


class AddSpeakerInlineForm(AddSpeakerForm):
    default_renderer = InlineFormLabelRenderer
