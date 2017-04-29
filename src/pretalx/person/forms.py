from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.utils import timezone, translation
from django.utils.translation import ugettext_lazy as _

from pretalx.person.models import SpeakerProfile, User


class UserForm(forms.Form):
    login_username = forms.CharField(max_length=60,
                                     label=_('Username or email address'),
                                     required=False)
    login_password = forms.CharField(widget=forms.PasswordInput,
                                     label=_('Password'),
                                     required=False)
    register_username = forms.CharField(max_length=60,
                                        label=_('Username'),
                                        required=False)
    register_email = forms.EmailField(label=_('Email address'),
                                      required=False)
    register_password = forms.CharField(widget=forms.PasswordInput,
                                        label=_('Password'),
                                        required=False)
    register_password_repeat = forms.CharField(widget=forms.PasswordInput,
                                               label=_('Password (again)'),
                                               required=False)

    def _clean_login(self, data):
        if '@' in data.get('login_username'):
            try:
                uname = User.objects.get(email=data.get('login_username')).nick
            except User.DoesNotExist:
                uname = 'user@invalid'
        else:
            uname = data.get('login_username')

        user = authenticate(username=uname, password=data.get('login_password'))

        if user is None:
            raise ValidationError(_('No user account matches the entered credentials. '
                                    'Are you sure that you typed your password correctly?'))

        if not user.is_active:
            raise ValidationError(_('Sorry, your account is currently disabled.'))

        data['user_id'] = user.pk

    def _clean_register(self, data):
        if data.get('register_password') != data.get('register_password_repeat'):
            raise ValidationError(_('You entered two different passwords. Please input the same one twice!'))

        if User.objects.filter(nick=data.get('register_username')).exists():
            raise ValidationError(_('We already have a user with that username. Did you already register before '
                                    'and just need to log in?'))

        if User.objects.filter(email=data.get('register_email')).exists():
            raise ValidationError(_('We already have a user with that email address. Did you already register '
                                    'before and just need to log in?'))

    def clean(self):
        data = super().clean()

        if data.get('login_username') and data.get('login_password'):
            self._clean_login(data)
        elif data.get('register_username') and data.get('register_email') and data.get('register_password'):
            self._clean_register(data)
        else:
            raise ValidationError(
                _('You need to fill all fields of either the login or the registration form.')
            )

        return data

    def save(self):
        data = self.cleaned_data
        if data.get('register_username') and data.get('register_email') and data.get('register_password'):
            user = User.objects.create_user(nick=data.get('register_username'),
                                            email=data.get('register_email'),
                                            password=data.get('register_password'),
                                            locale=translation.get_language(),
                                            timezone=timezone.get_current_timezone_name())
            data['user_id'] = user.pk

        return data['user_id']


class SpeakerProfileForm(forms.ModelForm):
    name = forms.CharField(
        max_length=100, label=_('Name')
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.event = kwargs.pop('event', None)
        initial = kwargs.pop('initial', dict())
        if self.user:
            initial['name'] = self.user.name
            kwargs['instance'] = self.user.profiles.filter(event=self.event).first()
        else:
            kwargs['instance'] = SpeakerProfile()
        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)

    def save(self, **kwargs):
        name = self.cleaned_data.get('name')
        if name:
            self.user.name = name
            self.user.save(update_fields=['name'])
        self.instance.event = self.event
        self.instance.user = self.user
        super().save(**kwargs)

    class Meta:
        model = SpeakerProfile
        fields = ('biography', )


class LoginInfoForm(forms.ModelForm):
    error_messages = {
        'pw_current_wrong': _("The current password you entered was not correct."),
    }

    old_password = forms.CharField(widget=forms.PasswordInput,
                                   label=_('Password (current)'),
                                   required=False)
    password = forms.CharField(widget=forms.PasswordInput,
                               label=_('Password (new)'),
                               required=False)
    password_repeat = forms.CharField(widget=forms.PasswordInput,
                                      label=_('Password (again)'),
                                      required=False)

    def clean_old_password(self):
        old_pw = self.cleaned_data.get('old_password')
        if old_pw and not check_password(old_pw, self.user.password):
            raise forms.ValidationError(
                self.error_messages['pw_current_wrong'],
                code='pw_current_wrong',
            )
        return old_pw

    def __init__(self, user, *args, **kwargs):
        self.user = user
        kwargs['instance'] = user
        super().__init__(*args, **kwargs)

    def save(self):
        password = self.cleaned_data.get('password')
        if not password == self.cleaned_data.get('password_repeat'):
            raise ValidationError(_('You entered two different passwords. Please input the same one twice!'))
        super().save()
        if password:
            self.user.set_password(password)
            self.user.save()

    class Meta:
        model = User
        fields = ('email', )
