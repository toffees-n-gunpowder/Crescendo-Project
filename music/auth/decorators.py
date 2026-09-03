from functools import wraps

from django.http import JsonResponse
from django.shortcuts import redirect

from music.auth import users


def _wants_json(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return True
    accept = request.headers.get('accept', '')
    if not accept:
        return True
    return 'text/html' not in accept


def login_required(view=None, *, login_url='login'):
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if _wants_json(request):
                    return JsonResponse(
                        {'error': 'authentication_required',
                         'detail': 'You must be logged in to do this.'},
                        status=401,
                    )
                return redirect(f'/{login_url}/?next={request.path}')
            return func(request, *args, **kwargs)
        return wrapper

    return decorator(view) if view else decorator


def role_required(*roles):
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if _wants_json(request):
                    return JsonResponse(
                        {'error': 'authentication_required'}, status=401
                    )
                return redirect(f'/login/?next={request.path}')

            if not request.user.has_role(*roles):
                if _wants_json(request):
                    return JsonResponse(
                        {'error': 'forbidden',
                         'detail': f'This action requires one of: {", ".join(roles)}.',
                         'your_role': request.user.role},
                        status=403,
                    )
                return _forbidden_page(request, roles)

            return func(request, *args, **kwargs)
        return wrapper
    return decorator


def admin_required(view):
    return role_required(users.ROLE_ADMIN)(view)


def artist_required(view):
    return role_required(users.ROLE_ARTIST, users.ROLE_ADMIN)(view)


def _forbidden_page(request, roles):
    from django.shortcuts import render
    return render(
        request,
        'music/403.html',
        {'required_roles': list(roles), 'your_role': request.user.role},
        status=403,
    )
