from django.conf import settings

class HostRoutingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.site_host = request.get_host().split(":", 1)[0].lower()
        request.is_manager_host = request.site_host in {settings.MANAGER_HOST, "localhost", "127.0.0.1", "testserver"}
        return self.get_response(request)

