from music.db import core


def get_or_create_artist(name):
    existing = core.scalar('SELECT id FROM music_artist WHERE name = %s LIMIT 1', [name])
    if existing:
        return existing
    return core.insert_returning_id(
        """
        INSERT INTO music_artist (name, bio, verified, user_id)
        VALUES (%s, '', FALSE, NULL)
        RETURNING id
        """,
        [name],
    )


def artist_id_by_name(name):
    return core.scalar('SELECT id FROM music_artist WHERE name = %s LIMIT 1', [name])


def get_or_create_genre(name):
    existing = core.scalar('SELECT id FROM music_genre WHERE name = %s LIMIT 1', [name])
    if existing:
        return existing
    return core.insert_returning_id(
        'INSERT INTO music_genre (name) VALUES (%s) ON CONFLICT (name) DO NOTHING RETURNING id',
        [name],
    ) or core.scalar('SELECT id FROM music_genre WHERE name = %s', [name])


def get_or_create_era(name, description=''):
    existing = core.scalar('SELECT id FROM music_era WHERE name = %s LIMIT 1', [name])
    if existing:
        return existing
    return core.insert_returning_id(
        """
        INSERT INTO music_era (name, description) VALUES (%s, %s)
        ON CONFLICT (name) DO NOTHING
        RETURNING id
        """,
        [name, description],
    ) or core.scalar('SELECT id FROM music_era WHERE name = %s', [name])


def describe_era_if_blank(name, description):
    return core.execute(
        """
        UPDATE music_era SET description = %s
        WHERE name = %s AND (description IS NULL OR description = '')
        """,
        [description, name],
    )


def genre_counts():
    return core.query(
        """
        SELECT g.id AS id, g.name AS name, COUNT(t.id) AS track_count
        FROM music_genre g
        LEFT JOIN music_track t ON t.genre_id = g.id
        GROUP BY g.id, g.name
        ORDER BY COUNT(t.id) ASC, g.name ASC
        """
    )


def era_counts():
    return core.query(
        """
        SELECT e.id AS id, e.name AS name, e.description AS description,
               COUNT(t.id) AS track_count
        FROM music_era e
        LEFT JOIN music_track t ON t.era_id = e.id
        GROUP BY e.id, e.name, e.description
        ORDER BY e.name ASC
        """
    )


def move_tracks_to_genre(from_genre_id, to_genre_id):
    return core.execute(
        'UPDATE music_track SET genre_id = %s WHERE genre_id = %s',
        [to_genre_id, from_genre_id],
    )


def delete_genre(genre_id):
    return core.execute('DELETE FROM music_genre WHERE id = %s', [genre_id])


def delete_eras(era_ids):
    if not era_ids:
        return 0
    return core.execute('DELETE FROM music_era WHERE id = ANY(%s)', [list(era_ids)])


def find_album(title, artist_id):
    return core.scalar(
        """
        SELECT a.id
        FROM music_album a
        JOIN music_albumcredit ac ON ac.album_id = a.id
        WHERE a.title = %s AND ac.artist_id = %s AND ac.role = 'primary'
        LIMIT 1
        """,
        [title, artist_id],
    )


def create_album(title, release_date, cover_url=''):
    return core.insert_returning_id(
        """
        INSERT INTO music_album (title, release_date, cover_url)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        [title, release_date, cover_url or ''],
    )


def set_album_cover_if_blank(album_id, cover_url):
    if not cover_url:
        return 0
    return core.execute(
        """
        UPDATE music_album SET cover_url = %s
        WHERE id = %s AND (cover_url IS NULL OR cover_url = '')
        """,
        [cover_url, album_id],
    )


def clear_album_covers(album_ids):
    if not album_ids:
        return 0
    return core.execute(
        "UPDATE music_album SET cover_url = '' WHERE id = ANY(%s)",
        [list(album_ids)],
    )


def albums_with_covers():
    return core.query(
        """
        SELECT id, title, cover_url
        FROM music_album
        WHERE cover_url IS NOT NULL AND cover_url <> ''
        ORDER BY id
        """
    )


def add_album_credit(album_id, artist_id, role='primary'):
    return core.execute(
        """
        INSERT INTO music_albumcredit (album_id, artist_id, role)
        SELECT %s, %s, %s
        WHERE NOT EXISTS (
            SELECT 1 FROM music_albumcredit
            WHERE album_id = %s AND artist_id = %s AND role = %s
        )
        """,
        [album_id, artist_id, role, album_id, artist_id, role],
    )


def find_track(title, album_id):
    return core.scalar(
        'SELECT id FROM music_track WHERE title = %s AND album_id = %s LIMIT 1',
        [title, album_id],
    )


def create_track(title, album_id, genre_id, era_id, duration_sec, audio_file,
                 track_number=1):
    return core.insert_returning_id(
        """
        INSERT INTO music_track (title, album_id, genre_id, era_id,
                                 duration_sec, audio_file, track_number)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        [title, album_id, genre_id, era_id, duration_sec or 0,
         audio_file or '', track_number],
    )


def backfill_track_fields(track_id, audio_file=None, genre_id=None, era_id=None):
    return core.execute(
        """
        UPDATE music_track
        SET audio_file = CASE WHEN (audio_file IS NULL OR audio_file = '')
                              THEN COALESCE(%s, audio_file) ELSE audio_file END,
            genre_id   = COALESCE(genre_id, %s),
            era_id     = COALESCE(era_id, %s)
        WHERE id = %s
        """,
        [audio_file, genre_id, era_id, track_id],
    )


def add_track_credit(track_id, artist_id, role='primary'):
    return core.execute(
        """
        INSERT INTO music_trackcredit (track_id, artist_id, role)
        SELECT %s, %s, %s
        WHERE NOT EXISTS (
            SELECT 1 FROM music_trackcredit
            WHERE track_id = %s AND artist_id = %s AND role = %s
        )
        """,
        [track_id, artist_id, role, track_id, artist_id, role],
    )


def set_track_title(track_id, title):
    return core.execute(
        'UPDATE music_track SET title = %s WHERE id = %s', [title, track_id]
    )


def tracks_with_album_titles():
    return core.query(
        """
        SELECT t.id AS id, t.title AS title, a.title AS album_title
        FROM music_track t
        LEFT JOIN music_album a ON a.id = t.album_id
        ORDER BY t.id
        """
    )


def track_titles():
    return core.query('SELECT id, title FROM music_track ORDER BY id')


def renumber_tracks_within_albums():
    return core.execute(
        """
        UPDATE music_track t
        SET track_number = numbered.position
        FROM (
            SELECT id,
                   ROW_NUMBER() OVER (PARTITION BY album_id ORDER BY id) AS position
            FROM music_track
        ) AS numbered
        WHERE t.id = numbered.id AND t.track_number IS DISTINCT FROM numbered.position
        """
    )


def track_count_by_album(album_ids):
    if not album_ids:
        return {}
    rows = core.query(
        """
        SELECT album_id, COUNT(*) AS n
        FROM music_track
        WHERE album_id = ANY(%s)
        GROUP BY album_id
        """,
        [list(album_ids)],
    )
    return {row.album_id: row.n for row in rows}


def count(table):
    allowed = {
        'music_track', 'music_album', 'music_artist', 'music_genre',
        'music_era', 'music_user', 'music_playlist', 'app_session',
    }
    if table not in allowed:
        raise ValueError(f'refusing to count unknown table: {table}')
    return core.scalar(f'SELECT COUNT(*) FROM {table}') or 0


def count_tracks_in_genre(genre_name):
    return core.scalar(
        """
        SELECT COUNT(*) FROM music_track t
        JOIN music_genre g ON g.id = t.genre_id
        WHERE g.name = %s
        """,
        [genre_name],
    ) or 0


def flush_catalogue():
    deleted = {}
    for table in ('music_trackcredit', 'music_albumcredit', 'music_playlisttrack',
                  'music_likedtrack', 'music_playhistory', 'music_grouptrack',
                  'music_track', 'music_album', 'music_artist'):
        deleted[table] = core.execute(f'DELETE FROM {table}')
    return deleted
