from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.http import HttpResponseForbidden
from .models import ApprovedEmail

def email_is_allowed(email):
    return bool(email) and ApprovedEmail.objects.filter(email__iexact=email, active=True).exists()

def apply_approved_role(user):
    approved = ApprovedEmail.objects.filter(email__iexact=user.email, active=True).first()
    if approved:
        user.is_staff = approved.role == ApprovedEmail.ROLE_OWNER
        user.is_superuser = approved.role == ApprovedEmail.ROLE_OWNER
        user.save(update_fields=["is_staff", "is_superuser"])
    return user

class AllowlistAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False

class AllowlistSocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return email_is_allowed(sociallogin.user.email)

    def pre_social_login(self, request, sociallogin):
        if not email_is_allowed(sociallogin.user.email):
            raise ImmediateHttpResponse(HttpResponseForbidden("This Google account is not approved for Cosmic Launch."))
        if sociallogin.is_existing:
            apply_approved_role(sociallogin.user)

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        return apply_approved_role(user)

