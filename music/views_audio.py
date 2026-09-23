import re

from django.http import Http404, HttpResponse

from .auth import users
from .db import audio as audio_db

RANGE_RE = re.compile(r'bytes=(\d*)-(\d*)')
MAX_CHUNK = 2 * 1024 * 1024


def _may_listen(request, row):
    if row.approval_status == 'approved':
        return True

    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return False
    return user.has_role(users.ROLE_ADMIN) or row.submitted_by_id == user.id


def _parse_range(header, size):
    match = RANGE_RE.match(header or '')
    if not match:
        return None

    raw_start, raw_end = match.group(1), match.group(2)

    if raw_start:
        start = int(raw_start)
        end = int(raw_end) if raw_end else size - 1
    elif raw_end:
        start = max(0, size - int(raw_end))
        end = size - 1
    else:
        return None

    end = min(end, size - 1)
    if start > end or start >= size:
        return None
    return start, end


def track_audio(request, track_id):
    row = audio_db.meta(track_id)
    if not row:
        raise Http404('No audio stored for that track.')
    if not _may_listen(request, row):
        raise Http404('No audio stored for that track.')

    size = row.byte_size
    span = _parse_range(request.headers.get('range'), size)

    if span:
        start, end = span
        length = min(end - start + 1, MAX_CHUNK)
        end = start + length - 1
        body = audio_db.chunk(track_id, start, length)
        response = HttpResponse(body, status=206, content_type=row.content_type)
        response['Content-Range'] = f'bytes {start}-{end}/{size}'
    else:
        body = audio_db.chunk(track_id, 0, size)
        response = HttpResponse(body, content_type=row.content_type)
        length = size

    response['Accept-Ranges'] = 'bytes'
    response['Content-Length'] = str(length)
    response['Cache-Control'] = 'private, max-age=3600'
    return response
