from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render

STATUS = {
    Http404: (404, 'Not found'),
    PermissionDenied: (403, 'Not allowed'),
}

SAFE_BACK = '/'

# Marks a response this middleware already rendered, so __call__ does not
# re-wrap the 404 pages produced by process_exception.
MARKER = 'X-Crescendo-Error'


class ErrorPageMiddleware:
    """Renders any uncaught view exception as music/error.html.

    Runs even with DEBUG=True, which handler404/handler500 do not - Django only
    consults those when DEBUG is off, and turning it off here would also stop
    /media/ being served.

    /api/ never reaches this: the @api decorator catches inside the view and
    returns JSON.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # A URL matching no route never reaches a view, so process_exception is
        # never called for it. Catch those on the way out.
        if (response.status_code == 404
                and not request.path.startswith('/api/')
                and not response.has_header(MARKER)):
            return self._render(request, 404, 'Not found',
                                f'No page matches {request.path}', 'Http404')

        return response

    def process_exception(self, request, exception):
        if request.path.startswith('/api/'):
            return None

        status, heading = STATUS.get(type(exception), (500, 'Something went wrong'))

        return self._render(
            request, status, heading,
            str(exception) or exception.__class__.__name__,
            exception.__class__.__name__,
        )

    def _render(self, request, status, heading, message, exception_type):
        response = render(request, 'music/error.html', {
            'status': status,
            'heading': heading,
            'message': message,
            'exception_type': exception_type,
            'back_url': request.META.get('HTTP_REFERER') or SAFE_BACK,
        }, status=status)
        response[MARKER] = '1'
        return response
