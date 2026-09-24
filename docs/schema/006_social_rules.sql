-- Crescendo - play history and group logic inside the database


-- 1. Procedure to add or update a user's review of a group
-- One review per user per group: a second review replaces the first.
-- The table only checks rating >= 0, so the 1-5 star rule lives here.
CREATE OR REPLACE PROCEDURE save_group_review(p_group_id INT, p_user_id INT,
                                              p_rating INT, p_text TEXT)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_rating IS NULL OR p_rating NOT BETWEEN 1 AND 5 THEN
        RAISE EXCEPTION 'Rating must be between 1 and 5, got %', p_rating;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM music_personalgroup WHERE id = p_group_id) THEN
        RAISE EXCEPTION 'Group % does not exist', p_group_id;
    END IF;

    INSERT INTO music_groupreview (group_id, reviewer_id, rating, review_text, created_at)
    VALUES (p_group_id, p_user_id, p_rating, COALESCE(p_text, ''), NOW())
    ON CONFLICT (group_id, reviewer_id) -- meaning that if multiple reviews by the same user
                                        -- then update the existing review to the new on
                                        -- Excluded means the value i just tried to add
    DO UPDATE SET rating      = EXCLUDED.rating,
                  review_text = EXCLUDED.review_text;
END;
$$;


-- 2. Function to record a play in the listening history
-- Skips the play if the same user already played the same track within the
-- last p_window_seconds (the player restores itself on every page load).
-- Returns TRUE if a row was added.  The advisory lock is a named lock for
-- this user's history, so two page loads at once take turns instead of both
-- passing the "played recently?" check.
CREATE OR REPLACE FUNCTION record_play(p_user_id INT, p_track_id INT,
                                       p_window_seconds INT DEFAULT 30)
RETURNS BOOLEAN AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(216, p_user_id); 
    -- lock 
    IF EXISTS (
        SELECT 1 FROM music_playhistory
        WHERE user_id = p_user_id
          AND track_id = p_track_id
          AND played_at > NOW() - make_interval(secs => p_window_seconds)
    ) THEN
        RETURN FALSE;
    END IF;

    INSERT INTO music_playhistory (user_id, track_id, played_at)
    VALUES (p_user_id, p_track_id, NOW());
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;


-- 3. Function returning a user's recent plays, newest first
-- Returns a whole table (one row per play) instead of a single value, so it
-- is used as  SELECT * FROM get_play_history(user_id, 50).
CREATE OR REPLACE FUNCTION get_play_history(p_user_id INT, p_limit INT DEFAULT 50)
RETURNS TABLE (
    played_at       TIMESTAMPTZ,
    id              BIGINT,
    title           TEXT,
    audio_file      TEXT,
    duration_sec    INT,
    album_title     TEXT,
    album_cover_url TEXT,
    artist_names    TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT ph.played_at,
           t.id,
           t.title::TEXT,
           t.audio_file::TEXT,
           t.duration_sec,
           a.title::TEXT,
           a.cover_url::TEXT,
           COALESCE(NULLIF(STRING_AGG(DISTINCT ar.name, ', '), ''),
                    'Unknown Artist')::TEXT
    FROM music_playhistory ph
    JOIN music_track t ON t.id = ph.track_id
    JOIN music_album a ON a.id = t.album_id
    LEFT JOIN music_trackcredit tc ON tc.track_id = t.id
    LEFT JOIN music_artist ar ON ar.id = tc.artist_id
    WHERE ph.user_id = p_user_id AND t.approval_status = 'approved'
    GROUP BY ph.played_at, t.id, t.title, t.audio_file, t.duration_sec,
             a.title, a.cover_url
    ORDER BY ph.played_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;


-- 4. Procedure to delete a group safely
-- Refuses unless p_owner_id owns the group, then removes the group's
-- tracks, playlists and reviews before the group itself.  Like
-- delete_album_proc, it either all succeeds or all rolls back.
CREATE OR REPLACE PROCEDURE delete_group_proc(p_group_id INT, p_owner_id INT)
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM music_personalgroup
        WHERE id = p_group_id AND owner_id = p_owner_id
    ) THEN
        RAISE EXCEPTION 'Group % does not exist or is not owned by user %',
            p_group_id, p_owner_id;
    END IF;

    DELETE FROM music_grouptrack    WHERE personal_group_id = p_group_id;
    DELETE FROM music_groupplaylist WHERE personal_group_id = p_group_id;
    DELETE FROM music_groupreview   WHERE group_id = p_group_id;
    DELETE FROM music_personalgroup WHERE id = p_group_id AND owner_id = p_owner_id;
END;
$$;
