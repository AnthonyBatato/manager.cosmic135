from django.conf import settings
from users.auth import is_owner

def app_config(request):
    return {
        "MANAGER_HOST": settings.MANAGER_HOST,
        "PUBLIC_ROOT_HOST": settings.PUBLIC_ROOT_HOST,
        "GOOGLE_AUTH_CONFIGURED": bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
        "IS_OWNER": is_owner(request.user),
    }

