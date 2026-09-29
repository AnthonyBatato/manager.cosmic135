from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from .models import ApprovedEmail

class AllowlistedGoogleBackend(ModelBackend):
    """Django backend that permits existing superusers or allowlisted accounts."""
    def user_can_authenticate(self, user):
        if not super().user_can_authenticate(user):
            return False
        return user.is_superuser or ApprovedEmail.objects.filter(email__iexact=user.email, active=True).exists()

    def get_user(self, user_id):
        try:
            user = get_user_model().objects.get(pk=user_id)
        except get_user_model().DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None

def is_owner(user):
    return user.is_authenticated and (
        user.is_superuser or ApprovedEmail.objects.filter(
            email__iexact=user.email, active=True, role=ApprovedEmail.ROLE_OWNER,
        ).exists()
    )

owner_required = user_passes_test(is_owner, login_url="account_login")

