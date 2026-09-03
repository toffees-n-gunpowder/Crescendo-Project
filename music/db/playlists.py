from music.db import core, tracks as track_db


def get_owned(playlist_id, user_id):
    return core.query_one(
        """
        SELECT id, name, is_public, created_at
        FROM music_playlist
        WHERE id = %s AND user_id = %s
        """,
        [playlist_id, user_id],
    )


def list_for_user(user_id):
    return core.query(
        """
        SELECT p.id, p.name, p.is_public, p.created_at,
               COUNT(pt.track_id) AS track_count
        FROM music_playlist p
        LEFT JOIN music_playlisttrack pt ON pt.playlist_id = p.id
        WHERE p.user_id = %s
        GROUP BY p.id, p.name, p.is_public, p.created_at
        ORDER BY p.created_at DESC
        """,
        [user_id],
    )


def tracks_in(playlist_id, user_id):
    rows = core.query(
        f"""
        SELECT t.id, t.title, t.audio_file, t.duration_sec, t.track_number,
               pt.position           AS position,
               a.title               AS album__title,
               a.cover_url           AS album__cover_url,
               a.release_date        AS album__release_date,
               g.name                AS genre__name
        FROM music_playlisttrack pt
        JOIN music_playlist p ON p.id = pt.playlist_id
        JOIN music_track t    ON t.id = pt.track_id
        JOIN music_album a    ON a.id = t.album_id
        LEFT JOIN music_genre g ON g.id = t.genre_id
        WHERE pt.playlist_id = %s
          AND p.user_id = %s
          AND t.approval_status = 'approved'
        ORDER BY pt.position ASC
        """,
        [playlist_id, user_id],
    )
    track_db.attach_artists(rows)
    return rows


def liked_ids(user_id):
    return [r.track_id for r in core.query(
        'SELECT track_id FROM music_likedtrack WHERE user_id = %s', [user_id]
    )]


def create(user_id, name):
    return core.insert_returning_id(
        """
        INSERT INTO music_playlist (user_id, name, is_public, created_at)
        VALUES (%s, %s, TRUE, NOW())
        RETURNING id
        """,
        [user_id, name],
    )
