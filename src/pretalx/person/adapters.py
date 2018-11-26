from allauth.account.utils import user_field
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class PersonAdapter(DefaultSocialAccountAdapter):
    """Adapter to get additional information from the Social Account."""

    def populate_user(self, request, sociallogin, data):
        """Use provider supplied name if there is one."""
        user = super().populate_user(request, sociallogin, data)
        name = data.get('name')
        user_field(user, 'name', name or '')
        return user
