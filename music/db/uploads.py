from music.db import core

PENDING = 'pending'
APPROVED = 'approved'
REJECTED = 'rejected'


def profile_for_user(user_id):
    return core.query_one(
        'SELECT id, name, bio, verified FROM music_artist WHERE user_id = %s',
        [user_id],
    )


def get_or_create_profile(user_id, display_name):
    existing = profile_for_user(user_id)
    if existing:
        return existing.id

    unclaimed = core.scalar(
        'SELECT id FROM music_artist WHERE name = %s AND user_id IS NULL LIMIT 1',
        [display_name],
    )
    if unclaimed:
        core.execute('UPDATE music_artist SET user_id = %s WHERE id = %s',
                     [user_id, unclaimed])
        return unclaimed

    return core.insert_returning_id(
        """
        INSERT INTO music_artist (name, bio, verified, user_id)
        VALUES (%s, '', FALSE, %s)
        RETURNING id
        """,
        [display_name, user_id],
    )


def update_profile(user_id, name, bio):
    return core.execute(
        'UPDATE music_artist SET name = %s, bio = %s WHERE user_id = %s',
        [name, bio, user_id],
    )


def create_album(title, release_date, cover_url, owner_user_id, artist_id):
    album_id = core.insert_returning_id(
        """
        INSERT INTO music_album (title, release_date, cover_url, created_by_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        [title, release_date, cover_url or '', owner_user_id],
    )
    core.execute(
        """
        INSERT INTO music_albumcredit (album_id, artist_id, role)
        VALUES (%s, %s, 'primary')
        """,
        [album_id, artist_id],
    )
    return album_id


def albums_for_user(user_id):
    return core.query(
        """
        SELECT a.id, a.title, a.release_date, a.cover_url,
               COUNT(t.id)                                              AS track_total,
               COUNT(*) FILTER (WHERE t.approval_status = 'approved')   AS approved,
               COUNT(*) FILTER (WHERE t.approval_status = 'pending')    AS pending,
               COUNT(*) FILTER (WHERE t.approval_status = 'rejected')   AS rejected
        FROM music_album a
        LEFT JOIN music_track t ON t.album_id = a.id
        WHERE a.created_by_id = %s
        GROUP BY a.id, a.title, a.release_date, a.cover_url
        ORDER BY a.id DESC
        """,
        [user_id],
    )


def find_own_album(album_id, user_id):
    return core.query_one(
        'SELECT id, title FROM music_album WHERE id = %s AND created_by_id = %s',
        [album_id, user_id],
    )


def delete_own_album(album_id, user_id):
    owned = find_own_album(album_id, user_id)
    if not owned:
        return 0

    core.execute(
        """
        DELETE FROM music_trackcredit
        WHERE track_id IN (SELECT id FROM music_track WHERE album_id = %s)
        """,
        [album_id],
    )
    for table in ('music_playlisttrack', 'music_likedtrack',
                  'music_playhistory', 'music_grouptrack'):
        core.execute(
            f'DELETE FROM {table} '
            'WHERE track_id IN (SELECT id FROM music_track WHERE album_id = %s)',
            [album_id],
        )
    core.execute('DELETE FROM music_track WHERE album_id = %s', [album_id])
    core.execute('DELETE FROM music_albumcredit WHERE album_id = %s', [album_id])
    return core.execute(
        'DELETE FROM music_album WHERE id = %s AND created_by_id = %s',
        [album_id, user_id],
    )


def create_pending_track(title, album_id, genre_id, duration_sec, audio_url,
                         submitted_by, artist_id, track_number=1):
    track_id = core.insert_returning_id(
        """
        INSERT INTO music_track (title, album_id, genre_id, era_id, duration_sec,
                                 audio_file, track_number,
                                 approval_status, submitted_by_id, submitted_at)
        VALUES (%s, %s, %s, NULL, %s, %s, %s, 'pending', %s, NOW())
        RETURNING id
        """,
        [title, album_id, genre_id, duration_sec or 0, audio_url,
         track_number, submitted_by],
    )
    core.execute(
        """
        INSERT INTO music_trackcredit (track_id, artist_id, role)
        VALUES (%s, %s, 'primary')
        """,
        [track_id, artist_id],
    )
    return track_id


def tracks_for_user(user_id):
    return core.query(
        """
        SELECT t.id, t.title, t.duration_sec, t.audio_file, t.approval_status,
               t.submitted_at, t.reviewed_at, t.review_note,
               a.title AS album_title, a.id AS album_id,
               g.name  AS genre_name,
               reviewer.username AS reviewed_by
        FROM music_track t
        JOIN music_album a ON a.id = t.album_id
        LEFT JOIN music_genre g ON g.id = t.genre_id
        LEFT JOIN music_user reviewer ON reviewer.id = t.reviewed_by_id
        WHERE t.submitted_by_id = %s
        ORDER BY t.submitted_at DESC NULLS LAST, t.id DESC
        """,
        [user_id],
    )


def next_track_number(album_id):
    return (core.scalar(
        'SELECT COALESCE(MAX(track_number), 0) + 1 FROM music_track WHERE album_id = %s',
        [album_id],
    ) or 1)


def find_own_track(track_id, user_id):
    return core.query_one(
        """
        SELECT id, title, audio_file, album_id, approval_status
        FROM music_track
        WHERE id = %s AND submitted_by_id = %s
        """,
        [track_id, user_id],
    )


def delete_own_track(track_id, user_id):
    owned = find_own_track(track_id, user_id)
    if not owned:
        return 0

    for table in ('music_trackcredit', 'music_playlisttrack', 'music_likedtrack',
                  'music_playhistory', 'music_grouptrack'):
        core.execute(f'DELETE FROM {table} WHERE track_id = %s', [track_id])

    return core.execute(
        'DELETE FROM music_track WHERE id = %s AND submitted_by_id = %s',
        [track_id, user_id],
    )


def counts_for_user(user_id):
    row = core.query_one(
        """
        SELECT COUNT(*)                                            AS total,
               COUNT(*) FILTER (WHERE approval_status = 'approved') AS approved,
               COUNT(*) FILTER (WHERE approval_status = 'pending')  AS pending,
               COUNT(*) FILTER (WHERE approval_status = 'rejected') AS rejected
        FROM music_track WHERE submitted_by_id = %s
        """,
        [user_id],
    )
    return row


def review_queue(status=PENDING):
    return core.query(
        """
        SELECT t.id, t.title, t.duration_sec, t.audio_file, t.approval_status,
               t.submitted_at, t.review_note,
               a.title AS album_title,
               g.name  AS genre_name,
               submitter.username AS submitted_by,
               submitter.id       AS submitted_by_id
        FROM music_track t
        JOIN music_album a ON a.id = t.album_id
        LEFT JOIN music_genre g ON g.id = t.genre_id
        LEFT JOIN music_user submitter ON submitter.id = t.submitted_by_id
        WHERE t.approval_status = %s
        ORDER BY t.submitted_at ASC NULLS LAST, t.id ASC
        """,
        [status],
    )


def pending_count():
    return core.scalar(
        "SELECT COUNT(*) FROM music_track WHERE approval_status = 'pending'"
    ) or 0


def set_review(track_id, status, admin_id, note=''):
    if status not in (APPROVED, REJECTED, PENDING):
        raise ValueError(f'unknown approval status: {status}')

    return core.execute(
        """
        UPDATE music_track
        SET approval_status = %s,
            reviewed_by_id  = %s,
            reviewed_at     = NOW(),
            review_note     = %s
        WHERE id = %s
        """,
        [status, admin_id, note[:500], track_id],
    )
