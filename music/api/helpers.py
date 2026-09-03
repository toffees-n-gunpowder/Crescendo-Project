import json
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from music.auth import sessions, users


def ok(payload=None, status=200):
    return JsonResponse(payload if payload is not None else {}, status=status,
                        json_dumps_params={'default': str})


def created(payload=None, location=None):
    response = ok(payload, status=201)
    if location:
        response['Location'] = location
    return response


def no_content():
    return JsonResponse({}, status=204)


def error(code, message, status, **extra):
    body = {'error': code, 'detail': message}
    body.update(extra)
    return JsonResponse(body, status=status)


def bad_request(message, **extra):
    return error('bad_request', message, 400, **extra)


def unauthorized(message='Authentication required.'):
    response = error('unauthorized', message, 401)
    response['WWW-Authenticate'] = 'Bearer realm="crescendo"'
    return response


def forbidden(message='You do not have permission to do that.', **extra):
    return error('forbidden', message, 403, **extra)


def not_found(message='Not found.'):
    return error('not_found', message, 404)


def conflict(message='That already exists.'):
    return error('conflict', message, 409)


def method_not_allowed(allowed):
    response = error('method_not_allowed',
                     f'Allowed: {", ".join(allowed)}.', 405)
    response['Allow'] = ', '.join(allowed)
    return response


def body(request):
    if request.content_type and 'application/json' in request.content_type:
        raw = (request.body or b'').decode('utf-8').strip()
        if not raw:
            return {}, None
        try:
            data = json.loads(raw)
        except ValueError:
            return None, bad_request('Request body is not valid JSON.')
        if not isinstance(data, dict):
            return None, bad_request('Request body must be a JSON object.')
        return data, None

    return request.POST.dict(), None


def require_fields(data, *names):
    missing = [n for n in names if not str(data.get(n, '')).strip()]
    if missing:
        return bad_request(
            'Missing required field(s): ' + ', '.join(missing),
            fields=missing,
        )
    return None


def as_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bearer_user(request):
    header = request.headers.get('authorization', '')
    if not header.lower().startswith('bearer '):
        return None

    token = header[7:].strip()
    user_id = sessions.get_user_id(token)
    if not user_id:
        return None

    row = users.get_by_id(user_id)
    return users.AuthUser(row) if row else None


def api(*methods):
    allowed = tuple(m.upper() for m in methods) or ('GET',)

    def decorator(func):
        @csrf_exempt
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if request.method == 'OPTIONS':
                response = no_content()
                response['Allow'] = ', '.join(allowed + ('OPTIONS',))
                return response

            if request.method not in allowed:
                return method_not_allowed(allowed)

            request.api_user = _bearer_user(request)
            try:
                return func(request, *args, **kwargs)
            except Exception as exc:
                return error('server_error', str(exc), 500)
        return wrapper
    return decorator


def auth_required(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        if not getattr(request, 'api_user', None):
            return unauthorized()
        return func(request, *args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            user = getattr(request, 'api_user', None)
            if not user:
                return unauthorized()
            if not user.has_role(*roles):
                return forbidden(
                    f'This endpoint requires one of: {", ".join(roles)}.',
                    your_role=user.role,
                )
            return func(request, *args, **kwargs)
        return wrapper
    return decorator


def track_json(row, request=None):
    data = {
        'id': row.id,
        'title': row.title,
        'duration_sec': row.duration_sec,
        'duration': row.get('formatted_duration'),
        'audio_url': row.audio_file,
        'track_number': row.track_number,
        'album': None,
        'genre': row.genre.name if row.get('genre') else None,
        'artists': [
            {'id': a.id, 'name': a.name, 'role': a.role}
            for a in (row.get('artists') or [])
        ],
    }
    album = row.get('album')
    if album:
        data['album'] = {
            'id': row.get('album_id'),
            'title': album.title,
            'cover_url': album.cover_url,
            'release_date': album.release_date,
        }
    return data


def playlist_json(row):
    return {
        'id': row.id,
        'name': row.name,
        'is_public': row.get('is_public'),
        'created_at': row.get('created_at'),
        'track_count': row.get('track_count'),
    }


def user_json(row):
    is_admin = bool(row.get('is_staff') or row.get('is_superuser'))
    return {
        'id': row.id,
        'username': row.username,
        'email': row.get('email'),
        'role': 'admin' if is_admin else row.get('account_type'),
        'is_active': row.get('is_active'),
    }


def artist_json(row):
    return {
        'id': row.id,
        'name': row.name,
        'bio': row.get('bio'),
        'verified': row.get('verified'),
    }
