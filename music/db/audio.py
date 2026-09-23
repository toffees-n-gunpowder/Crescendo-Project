from music.db import core

CONTENT_TYPES = {
    '.mp3':  'audio/mpeg',
    '.ogg':  'audio/ogg',
    '.wav':  'audio/wav',
    '.m4a':  'audio/mp4',
    '.flac': 'audio/flac',
}
DEFAULT_CONTENT_TYPE = 'application/octet-stream'


def content_type_for(filename):
    name = (filename or '').lower()
    for extension, mime in CONTENT_TYPES.items():
        if name.endswith(extension):
            return mime
    return DEFAULT_CONTENT_TYPE


def store(track_id, content, content_type, original_name=''):
    core.execute('DELETE FROM music_trackaudio WHERE track_id = %s', [track_id])
    return core.execute(
        """
        INSERT INTO music_trackaudio (track_id, content, content_type, byte_size,
                                      original_name, uploaded_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        """,
        [track_id, content, content_type, len(content), (original_name or '')[:255]],
    )


def meta(track_id):
    return core.query_one(
        """
        SELECT ta.content_type, ta.byte_size, ta.original_name,
               t.approval_status, t.submitted_by_id
        FROM music_trackaudio ta
        JOIN music_track t ON t.id = ta.track_id
        WHERE ta.track_id = %s
        """,
        [track_id],
    )


def chunk(track_id, offset, length):
    raw = core.scalar(
        'SELECT SUBSTRING(content FROM %s FOR %s) FROM music_trackaudio WHERE track_id = %s',
        [offset + 1, length, track_id],
    )
    return bytes(raw) if raw is not None else None


def delete(track_id):
    return core.execute('DELETE FROM music_trackaudio WHERE track_id = %s', [track_id])


def exists(track_id):
    return bool(core.scalar(
        'SELECT 1 FROM music_trackaudio WHERE track_id = %s', [track_id]
    ))


def total_bytes():
    return core.scalar('SELECT COALESCE(SUM(byte_size), 0) FROM music_trackaudio') or 0
