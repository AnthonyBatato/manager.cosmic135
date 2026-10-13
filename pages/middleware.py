from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.http.request import split_domain_port, validate_host

from .models import Domain

class HostRoutingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw_host = request.META.get("HTTP_HOST") or request.META.get("SERVER_NAME", "")
        host, _port = split_domain_port(raw_host.lower())
        if not host:
            raise DisallowedHost("Invalid HTTP host header.")
        configured_hosts = settings.ROUTING_ALLOWED_HOSTS + ["web", "testserver"]
        is_configured = validate_host(host, configured_hosts)
        is_verified_custom = False if is_configured else Domain.objects.filter(
            hostname=host, status=Domain.STATUS_VERIFIED,
        ).exists()
        if not is_configured and not is_verified_custom:
            raise DisallowedHost(f"Unrecognised host: {host}")
        request.site_host = host
        request.is_manager_host = request.site_host in {settings.MANAGER_HOST, "localhost", "127.0.0.1", "testserver"}
        return self.get_response(request)

