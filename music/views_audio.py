import re

from django.http import Http404, StreamingHttpResponse

from .auth import users
from .db import audio as audio_db

RANGE_RE = re.compile(r'bytes=(\d*)-(\d*)')

# Read the response out of the database in pieces rather than building the whole
# body in memory. A range is served in full: truncating one makes the browser
# re-open the stream instead of continuing it, which stalls playback mid-track.
STREAM_STEP = 256 * 1024


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


def _stream(track_id, start, length):
    sent = 0
    while sent < length:
        piece = audio_db.chunk(track_id, start + sent, min(STREAM_STEP, length - sent))
        if not piece:
            return
        sent += len(piece)
        yield piece


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
        length = end - start + 1
        response = StreamingHttpResponse(
            _stream(track_id, start, length), status=206, content_type=row.content_type
        )
        response['Content-Range'] = f'bytes {start}-{end}/{size}'
    else:
        length = size
        response = StreamingHttpResponse(
            _stream(track_id, 0, size), content_type=row.content_type
        )

    response['Accept-Ranges'] = 'bytes'
    response['Content-Length'] = str(length)

    # A media element streams a file as a chain of range requests. Without a
    # validator the browser cannot tell that two partial responses belong to the
    # same resource, so it re-opens the stream instead of continuing it.
    response['ETag'] = f'"{track_id}-{size}"'
    response['Cache-Control'] = 'private, max-age=3600, no-transform'
    return response
