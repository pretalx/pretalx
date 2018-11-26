from allauth.socialaccount.models import SocialApp
from django import template

register = template.Library()


@register.simple_tag
def is_auth_provider_setup(provider):
    """Returns true if the given allauth provider is setup."""
    return SocialApp.objects.filter(provider=provider).exists()
