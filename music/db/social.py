from music.db import core
from datetime import datetime

# --- Play History ---

def record_play(user_id, track_id):
    return core.execute(
        """
        INSERT INTO music_playhistory (user_id, track_id, played_at)
        VALUES (%s, %s, %s)
        """,
        [user_id, track_id, datetime.now()]
    )

def record_play_once(user_id, track_id, window_seconds=30):
    """Records a play unless the same track was already logged moments ago.

    The player restores itself on every page load, so without this guard a
    single listen would land in the history once per page the user visits.
    """
    recent = core.scalar(
        """
        SELECT 1 FROM music_playhistory
        WHERE user_id = %s AND track_id = %s
          AND played_at > NOW() - (%s * INTERVAL '1 second')
        LIMIT 1
        """,
        [user_id, track_id, window_seconds]
    )
    if recent:
        return 0
    return record_play(user_id, track_id)


def get_play_history(user_id, limit=50):
    return core.query(
        """
        SELECT ph.played_at, t.id, t.title, t.audio_file, t.duration_sec,
               a.title AS album_title, a.cover_url AS album_cover_url,
               COALESCE(NULLIF(STRING_AGG(DISTINCT ar.name, ', '), ''),
                        'Unknown Artist') AS artist_names
        FROM music_playhistory ph
        JOIN music_track t ON t.id = ph.track_id
        JOIN music_album a ON a.id = t.album_id
        LEFT JOIN music_trackcredit tc ON tc.track_id = t.id
        LEFT JOIN music_artist ar ON ar.id = tc.artist_id
        WHERE ph.user_id = %s AND t.approval_status = 'approved'
        GROUP BY ph.played_at, t.id, t.title, t.audio_file, t.duration_sec,
                 a.title, a.cover_url
        ORDER BY ph.played_at DESC
        LIMIT %s
        """,
        [user_id, limit]
    )

# --- Follows ---

def toggle_follow(follower_id, artist_id):
    exists = core.scalar(
        "SELECT 1 FROM music_follow WHERE follower_id = %s AND artist_id = %s",
        [follower_id, artist_id]
    )
    if exists:
        core.execute(
            "DELETE FROM music_follow WHERE follower_id = %s AND artist_id = %s",
            [follower_id, artist_id]
        )
        return False
    else:
        core.execute(
            "INSERT INTO music_follow (follower_id, artist_id, created_at) VALUES (%s, %s, %s)",
            [follower_id, artist_id, datetime.now()]
        )
        return True

def get_followed_artists(user_id):
    return core.query(
        """
        SELECT a.id, a.name, a.bio, a.verified, f.created_at as followed_at
        FROM music_follow f
        JOIN music_artist a ON a.id = f.artist_id
        WHERE f.follower_id = %s
        ORDER BY f.created_at DESC
        """,
        [user_id]
    )

# --- Groups ---

def create_group(owner_id, name, description, is_public=True):
    return core.insert_returning_id(
        """
        INSERT INTO music_personalgroup (owner_id, name, description, is_public, created_at)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        [owner_id, name, description, is_public, datetime.now()]
    )

def list_groups(user_id=None, search_query=None):
    base_query = """
        SELECT g.id, g.name, g.description, g.is_public, g.created_at,
               u.username as owner_name, g.owner_id,
               COALESCE(AVG(r.rating), 0) as avg_rating
        FROM music_personalgroup g
        JOIN music_user u ON u.id = g.owner_id
        LEFT JOIN music_groupreview r ON r.group_id = g.id
        WHERE ({visibility_clause})
    """
    
    visibility_clause = "g.is_public = TRUE OR g.owner_id = %s" if user_id else "g.is_public = TRUE"
    params = [user_id] if user_id else []

    if search_query:
        base_query += " AND (g.name ILIKE %s OR g.description ILIKE %s OR u.username ILIKE %s)"
        search_term = f"%{search_query}%"
        params.extend([search_term, search_term, search_term])

    base_query += """
        GROUP BY g.id, u.username
        ORDER BY {order_clause}
    """
    
    if user_id:
        order_clause = "(g.owner_id = %s) DESC, g.created_at DESC"
        params.append(user_id)
    else:
        order_clause = "g.created_at DESC"

    query = base_query.format(visibility_clause=visibility_clause, order_clause=order_clause)
    return core.query(query, params)

def get_group(group_id):
    return core.query_one(
        """
        SELECT g.id, g.name, g.description, g.is_public, g.created_at,
               u.username as owner_name, g.owner_id
        FROM music_personalgroup g
        JOIN music_user u ON u.id = g.owner_id
        WHERE g.id = %s
        """,
        [group_id]
    )

def update_group_visibility(group_id, is_public):
    core.execute(
        "UPDATE music_personalgroup SET is_public = %s WHERE id = %s",
        [is_public, group_id]
    )

def add_group_track(group_id, track_id):
    exists = core.scalar(
        "SELECT 1 FROM music_grouptrack WHERE personal_group_id = %s AND track_id = %s",
        [group_id, track_id]
    )
    if not exists:
        return core.execute(
            "INSERT INTO music_grouptrack (personal_group_id, track_id, added_at) VALUES (%s, %s, %s)",
            [group_id, track_id, datetime.now()]
        )
    return 0

def group_tracks(group_id):
    return core.query(
        """
        SELECT t.id, t.title, t.audio_file, t.duration_sec,
               a.title AS album_title, a.cover_url AS album_cover_url,
               gt.added_at,
               COALESCE(NULLIF(STRING_AGG(ar.name, ', ' ORDER BY ar.name), ''),
                        'Unknown Artist') AS artist_names
        FROM music_grouptrack gt
        JOIN music_track t ON t.id = gt.track_id
        JOIN music_album a ON a.id = t.album_id
        LEFT JOIN music_trackcredit tc ON tc.track_id = t.id
        LEFT JOIN music_artist ar ON ar.id = tc.artist_id
        WHERE gt.personal_group_id = %s
          AND t.approval_status = 'approved'
        GROUP BY t.id, t.title, t.audio_file, t.duration_sec,
                 a.title, a.cover_url, gt.added_at
        ORDER BY gt.added_at DESC
        """,
        [group_id]
    )


def addable_tracks(group_id):
    return core.query(
        """
        SELECT t.id, t.title,
               a.title AS album_title,
               COALESCE(NULLIF(STRING_AGG(ar.name, ', ' ORDER BY ar.name), ''),
                        'Unknown Artist') AS artist_names
        FROM music_track t
        JOIN music_album a ON a.id = t.album_id
        LEFT JOIN music_trackcredit tc ON tc.track_id = t.id
        LEFT JOIN music_artist ar ON ar.id = tc.artist_id
        WHERE t.approval_status = 'approved'
          AND t.id NOT IN (
              SELECT track_id FROM music_grouptrack WHERE personal_group_id = %s
          )
        GROUP BY t.id, t.title, a.title
        ORDER BY t.title ASC
        """,
        [group_id]
    )


def track_is_addable(track_id):
    return bool(core.scalar(
        "SELECT 1 FROM music_track WHERE id = %s AND approval_status = 'approved'",
        [track_id]
    ))

def remove_group_track(group_id, track_id):
    return core.execute(
        "DELETE FROM music_grouptrack WHERE personal_group_id = %s AND track_id = %s",
        [group_id, track_id]
    )


def remove_group_playlist(group_id, playlist_id):
    return core.execute(
        "DELETE FROM music_groupplaylist WHERE personal_group_id = %s AND playlist_id = %s",
        [group_id, playlist_id]
    )


def delete_group(group_id, owner_id):
    owned = core.scalar(
        "SELECT 1 FROM music_personalgroup WHERE id = %s AND owner_id = %s",
        [group_id, owner_id]
    )
    if not owned:
        return 0

    core.execute("DELETE FROM music_grouptrack WHERE personal_group_id = %s", [group_id])
    core.execute("DELETE FROM music_groupplaylist WHERE personal_group_id = %s", [group_id])
    core.execute("DELETE FROM music_groupreview WHERE group_id = %s", [group_id])
    return core.execute(
        "DELETE FROM music_personalgroup WHERE id = %s AND owner_id = %s",
        [group_id, owner_id]
    )


def add_group_review(group_id, reviewer_id, rating, review_text):
    exists = core.scalar(
        "SELECT 1 FROM music_groupreview WHERE group_id = %s AND reviewer_id = %s",
        [group_id, reviewer_id]
    )
    if exists:
        return core.execute(
            """
            UPDATE music_groupreview 
            SET rating = %s, review_text = %s 
            WHERE group_id = %s AND reviewer_id = %s
            """,
            [rating, review_text, group_id, reviewer_id]
        )
    else:
        return core.execute(
            """
            INSERT INTO music_groupreview (group_id, reviewer_id, rating, review_text, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [group_id, reviewer_id, rating, review_text, datetime.now()]
        )

def group_reviews(group_id):
    return core.query(
        """
        SELECT r.id, r.rating, r.review_text, r.created_at,
               r.reviewer_id, u.username as reviewer_name
        FROM music_groupreview r
        JOIN music_user u ON u.id = r.reviewer_id
        WHERE r.group_id = %s
        ORDER BY r.created_at DESC
        """,
        [group_id]
    )


def delete_own_review(review_id, reviewer_id):
    return core.execute(
        "DELETE FROM music_groupreview WHERE id = %s AND reviewer_id = %s",
        [review_id, reviewer_id]
    )

def add_group_playlist(group_id, playlist_id):
    exists = core.scalar(
        "SELECT 1 FROM music_groupplaylist WHERE personal_group_id = %s AND playlist_id = %s",
        [group_id, playlist_id]
    )
    if not exists:
        return core.execute(
            "INSERT INTO music_groupplaylist (personal_group_id, playlist_id, added_at) VALUES (%s, %s, %s)",
            [group_id, playlist_id, datetime.now()]
        )
    return 0

def addable_playlists(user_id, group_id):
    return core.query(
        """
        SELECT p.id, p.name, p.is_public, u.username AS owner_name,
               (p.user_id = %s) AS is_mine,
               COUNT(pt.track_id) AS track_count
        FROM music_playlist p
        JOIN music_user u ON u.id = p.user_id
        LEFT JOIN music_playlisttrack pt ON pt.playlist_id = p.id
        WHERE (p.user_id = %s OR p.is_public = TRUE)
          AND p.id NOT IN (
              SELECT playlist_id FROM music_groupplaylist WHERE personal_group_id = %s
          )
        GROUP BY p.id, p.name, p.is_public, u.username, p.user_id
        ORDER BY (p.user_id = %s) DESC, u.username ASC, p.name ASC
        """,
        [user_id, user_id, group_id, user_id]
    )


def playlist_is_addable(playlist_id, user_id):
    return bool(core.scalar(
        """
        SELECT 1 FROM music_playlist
        WHERE id = %s AND (user_id = %s OR is_public = TRUE)
        """,
        [playlist_id, user_id]
    ))


def group_playlists(group_id):
    return core.query(
        """
        SELECT p.id, p.name, gp.added_at, u.username as creator_name
        FROM music_groupplaylist gp
        JOIN music_playlist p ON p.id = gp.playlist_id
        JOIN music_user u ON u.id = p.user_id
        WHERE gp.personal_group_id = %s
        ORDER BY gp.added_at DESC
        """,
        [group_id]
    )
