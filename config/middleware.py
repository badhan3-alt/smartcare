from django.conf import settings
from django.http import HttpResponseBadRequest, HttpResponse


class RequestSizeLimitMiddleware:
    """Reject oversized declared bodies before session or multipart processing."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        content_length = request.META.get('CONTENT_LENGTH')
        if content_length:
            try:
                length = int(content_length)
            except (TypeError, ValueError):
                return HttpResponseBadRequest('Invalid request length.')
            if length < 0:
                return HttpResponseBadRequest('Invalid request length.')
            if length > settings.SMARTCARE_MAX_REQUEST_BYTES:
                return HttpResponse('The request is too large.', status=413)
        return self.get_response(request)


class NoCacheAuthenticatedPagesMiddleware:
    """Prevent the browser from restoring stale authenticated pages."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        response.setdefault('Permissions-Policy', 'geolocation=(), payment=(), usb=()')
        response.setdefault('Cross-Origin-Resource-Policy', 'same-origin')
        return response
