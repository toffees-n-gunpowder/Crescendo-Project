-- 1. Trigger to number tracks within an album
-- Fills in track_number as "last number in this album + 1" when the INSERT
-- leaves it out.  Locking the album row first makes two uploads to the same
-- album take turns, so they can never get the same number.

CREATE OR REPLACE FUNCTION track_set_number_fn()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.track_number IS NULL THEN
        --PERFORM 1 is to let the programme know that the returned result doesnt matter.
        -- what matters is that we obtain the lock
        PERFORM 1 FROM music_album WHERE id = NEW.album_id FOR UPDATE;
        -- FOR UPDATE is for the lock so that no two users can access it at the same time

        SELECT COALESCE(MAX(track_number), 0) + 1 INTO NEW.track_number
        -- COALESCE scans from left to right and obtains the left most non-null value
        FROM music_track
        WHERE album_id = NEW.album_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS track_number_trigger ON music_track;
CREATE TRIGGER track_number_trigger
BEFORE INSERT ON music_track
FOR EACH ROW
EXECUTE FUNCTION track_set_number_fn();


-- 2. Trigger to log a user out everywhere when their account is deactivated
CREATE OR REPLACE FUNCTION user_deactivated_fn()
RETURNS TRIGGER AS $$ 
-- RETURNS TRIGGER means this function is to be used by a trigger only, an user can't actually call it
BEGIN
    DELETE FROM app_session WHERE user_id = NEW.id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS user_deactivated_trigger ON music_user;
CREATE TRIGGER user_deactivated_trigger
AFTER UPDATE OF is_active ON music_user
FOR EACH ROW
WHEN (OLD.is_active AND NOT NEW.is_active)
EXECUTE FUNCTION user_deactivated_fn();


-- 3. Trigger to keep at least one active admin
-- Refuses any change (demotion, deactivation or deletion) that would leave
-- the site with no active admin.  Raises SQLSTATE CR001 so the Python code
-- can recognise this error and show a friendly message.
CREATE OR REPLACE FUNCTION keep_last_admin_fn()
RETURNS TRIGGER AS $$
DECLARE
    was_admin BOOLEAN;
    still_admin BOOLEAN;
BEGIN
    was_admin := OLD.is_active AND (OLD.is_staff OR OLD.is_superuser);

    IF TG_OP = 'DELETE' THEN
        still_admin := FALSE;
    ELSE
        still_admin := NEW.is_active AND (NEW.is_staff OR NEW.is_superuser);
    END IF;

    IF was_admin AND NOT still_admin AND NOT EXISTS (
        SELECT 1 FROM music_user
        WHERE id <> OLD.id AND is_active AND (is_staff OR is_superuser)
    ) THEN
        RAISE EXCEPTION 'That is the only active admin account.'
            USING ERRCODE = 'CR001';
    END IF;
--TG_OP is automatically filled postgresql
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS keep_last_admin_trigger ON music_user;
CREATE TRIGGER keep_last_admin_trigger
BEFORE UPDATE OF is_active, is_staff, is_superuser OR DELETE ON music_user
FOR EACH ROW
EXECUTE FUNCTION keep_last_admin_fn();


-- 4. Function to like or unlike a track
-- Returns TRUE if the track is now liked, FALSE if it is now unliked.
-- Deleting first means a double click just toggles twice instead of
-- failing on the (user_id, track_id) unique constraint.
CREATE OR REPLACE FUNCTION toggle_like(p_user_id INT, p_track_id INT)
RETURNS BOOLEAN AS $$
BEGIN
    DELETE FROM music_likedtrack
    WHERE user_id = p_user_id AND track_id = p_track_id;

    IF FOUND THEN
        RETURN FALSE;
    END IF;
-- above comment explains very well the use of trying to delete first
    INSERT INTO music_likedtrack (user_id, track_id, created_at)
    VALUES (p_user_id, p_track_id, NOW())
    ON CONFLICT (user_id, track_id) DO NOTHING;
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;


-- 5. Function to follow or unfollow an artist
-- Returns TRUE if the user now follows the artist, FALSE if not.
CREATE OR REPLACE FUNCTION toggle_follow(p_user_id INT, p_artist_id INT)
RETURNS BOOLEAN AS $$
BEGIN
    DELETE FROM music_follow
    WHERE follower_id = p_user_id AND artist_id = p_artist_id;

    IF FOUND THEN
        RETURN FALSE;
    END IF;

    INSERT INTO music_follow (follower_id, artist_id, created_at)
    VALUES (p_user_id, p_artist_id, NOW())
    ON CONFLICT (follower_id, artist_id) DO NOTHING;
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;


-- 6. Procedure to approve or reject an uploaded track
-- Checks the status is valid, the reviewer is an active admin and the track
-- exists, then records the decision.  The audit trigger in
-- 003_db_features.sql logs the status change automatically.
CREATE OR REPLACE PROCEDURE review_track(p_track_id INT, p_status TEXT,
                                         p_admin_id INT, p_note TEXT DEFAULT '')
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_status NOT IN ('approved', 'rejected', 'pending') THEN
        RAISE EXCEPTION 'Unknown approval status: %', p_status;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM music_user
        WHERE id = p_admin_id AND is_active AND (is_staff OR is_superuser)
    ) THEN
        RAISE EXCEPTION 'User % is not an active admin', p_admin_id;
    END IF;

    UPDATE music_track
    SET approval_status = p_status,
        reviewed_by_id  = p_admin_id,
        reviewed_at     = NOW(),
        review_note     = LEFT(COALESCE(p_note, ''), 500)
    WHERE id = p_track_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Track % does not exist', p_track_id;
    END IF;
END;
$$;
