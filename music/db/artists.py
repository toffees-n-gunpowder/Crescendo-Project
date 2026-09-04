from music.db import core

APPROVED_ONLY = "t.approval_status = 'approved'"


def get(artist_id):
    return core.query_one(
        """
        SELECT ar.id, ar.name, ar.bio, ar.verified, ar.user_id,
               u.username AS claimed_by
        FROM music_artist ar
        LEFT JOIN music_user u ON u.id = ar.user_id
        WHERE ar.id = %s
        """,
        [artist_id],
    )


def find_by_name(name):
    return core.query_one(
        'SELECT id, name FROM music_artist WHERE LOWER(name) = LOWER(%s) LIMIT 1',
        [name],
    )


def stats(artist_id):
    row = core.query_one(
        f"""
        SELECT
            (SELECT COUNT(DISTINCT t.id)
             FROM music_track t
             JOIN music_trackcredit tc ON tc.track_id = t.id
             WHERE tc.artist_id = %s AND {APPROVED_ONLY})            AS track_count,
            (SELECT COUNT(DISTINCT a.id)
             FROM music_album a
             JOIN music_albumcredit ac ON ac.album_id = a.id
             WHERE ac.artist_id = %s)                                 AS album_count,
            (SELECT COUNT(*) FROM music_follow WHERE artist_id = %s)  AS follower_count
        """,
        [artist_id, artist_id, artist_id],
    )
    return row or core.Row(
        {'track_count': 0, 'album_count': 0, 'follower_count': 0}
    )


def roles_played(artist_id):
    return core.query(
        f"""
        SELECT tc.role, COUNT(DISTINCT t.id) AS count
        FROM music_trackcredit tc
        JOIN music_track t ON t.id = tc.track_id
        WHERE tc.artist_id = %s AND {APPROVED_ONLY}
        GROUP BY tc.role
        ORDER BY COUNT(DISTINCT t.id) DESC
        """,
        [artist_id],
    )


def tracks(artist_id, limit=50, offset=0):
    rows = core.query(
        f"""
        SELECT t.id, t.title, t.audio_file, t.duration_sec, t.track_number,
               tc.role                AS credit_role,
               a.id                   AS album_id,
               a.title                AS album__title,
               a.cover_url            AS album__cover_url,
               a.release_date         AS album__release_date,
               g.name                 AS genre__name
        FROM music_track t
        JOIN music_trackcredit tc ON tc.track_id = t.id
        JOIN music_album a ON a.id = t.album_id
        LEFT JOIN music_genre g ON g.id = t.genre_id
        WHERE tc.artist_id = %s AND {APPROVED_ONLY}
        ORDER BY a.release_date DESC NULLS LAST, a.title, t.track_number
        LIMIT %s OFFSET %s
        """,
        [artist_id, limit, offset],
    )

    from music.db import tracks as track_db
    track_db.attach_artists(rows)
    return rows


def albums(artist_id):
    return core.query(
        f"""
        SELECT a.id, a.title, a.cover_url, a.release_date,
               COUNT(t.id) FILTER (WHERE {APPROVED_ONLY}) AS track_count
        FROM music_album a
        JOIN music_albumcredit ac ON ac.album_id = a.id
        LEFT JOIN music_track t ON t.album_id = a.id
        WHERE ac.artist_id = %s
        GROUP BY a.id, a.title, a.cover_url, a.release_date
        HAVING COUNT(t.id) FILTER (WHERE {APPROVED_ONLY}) > 0
        ORDER BY a.release_date DESC NULLS LAST, a.title
        """,
        [artist_id],
    )


def genres(artist_id):
    return core.query(
        f"""
        SELECT g.name, COUNT(DISTINCT t.id) AS count
        FROM music_track t
        JOIN music_trackcredit tc ON tc.track_id = t.id
        JOIN music_genre g ON g.id = t.genre_id
        WHERE tc.artist_id = %s AND {APPROVED_ONLY}
        GROUP BY g.name
        ORDER BY COUNT(DISTINCT t.id) DESC
        LIMIT 6
        """,
        [artist_id],
    )


def is_following(user_id, artist_id):
    if not user_id:
        return False
    return bool(core.scalar(
        'SELECT 1 FROM music_follow WHERE follower_id = %s AND artist_id = %s LIMIT 1',
        [user_id, artist_id],
    ))


def toggle_follow(user_id, artist_id):
    if is_following(user_id, artist_id):
        core.execute(
            'DELETE FROM music_follow WHERE follower_id = %s AND artist_id = %s',
            [user_id, artist_id],
        )
        return False

    core.execute(
        """
        INSERT INTO music_follow (follower_id, artist_id, created_at)
        VALUES (%s, %s, NOW())
        """,
        [user_id, artist_id],
    )
    return True
