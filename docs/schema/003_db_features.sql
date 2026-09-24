-- Triggers, Functions, and Procedures

-- 1. Create a shadow table for audit
-- No foreign key to music_track on purpose: the history of a deleted track
-- must survive the track itself.
CREATE TABLE IF NOT EXISTS music_track_audit (
    audit_id SERIAL PRIMARY KEY,
    track_id INT,
    title VARCHAR(255),
    action VARCHAR(50),
    action_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    old_status VARCHAR(20),
    new_status VARCHAR(20),
    changed_by_id INT
);

-- Columns added after the table first shipped
ALTER TABLE music_track_audit ADD COLUMN IF NOT EXISTS old_status VARCHAR(20);
ALTER TABLE music_track_audit ADD COLUMN IF NOT EXISTS new_status VARCHAR(20);
ALTER TABLE music_track_audit ADD COLUMN IF NOT EXISTS changed_by_id INT;

-- Replaces the earlier insert-only trigger
DROP TRIGGER IF EXISTS track_insert_trigger ON music_track;
DROP FUNCTION IF EXISTS audit_track_insert_fn();

-- Trigger function
-- INSERT: log who submitted it.  UPDATE: log only approval status changes,
-- and who reviewed it.  DELETE: log the last known title and status.
CREATE OR REPLACE FUNCTION audit_track_change_fn()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO music_track_audit (track_id, title, action, new_status, changed_by_id)
        VALUES (NEW.id, NEW.title, 'INSERT', NEW.approval_status, NEW.submitted_by_id);
        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.approval_status IS DISTINCT FROM OLD.approval_status THEN
            INSERT INTO music_track_audit (track_id, title, action, old_status,
                                           new_status, changed_by_id)
            VALUES (NEW.id, NEW.title, 'STATUS_CHANGE', OLD.approval_status,
                    NEW.approval_status, NEW.reviewed_by_id);
        END IF;
        RETURN NEW;

    ELSE
        INSERT INTO music_track_audit (track_id, title, action, old_status)
        VALUES (OLD.id, OLD.title, 'DELETE', OLD.approval_status);
        RETURN OLD;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Trigger
DROP TRIGGER IF EXISTS track_audit_trigger ON music_track;
CREATE TRIGGER track_audit_trigger
AFTER INSERT OR UPDATE OR DELETE ON music_track
FOR EACH ROW
EXECUTE FUNCTION audit_track_change_fn();

-- 2. Function to get track count
-- Counts each approved track once, even when the artist holds several
-- credits on it (e.g. primary and producer).
CREATE OR REPLACE FUNCTION get_artist_track_count(p_artist_id INT)
RETURNS INT AS $$
DECLARE
    v_count INT;
BEGIN
    SELECT COUNT(DISTINCT t.id) INTO v_count
    FROM music_track t
    JOIN music_trackcredit tc ON tc.track_id = t.id
    WHERE tc.artist_id = p_artist_id
      AND t.approval_status = 'approved';
    RETURN COALESCE(v_count, 0);
END;
$$ LANGUAGE plpgsql;

-- 3. Procedure to delete album safely
-- Refuses unless p_user_id created the album, then removes every row that
-- points at the album's tracks before the tracks and album themselves.
-- No COMMIT inside: a CALL is one statement, so it either all succeeds or
-- all rolls back, and it can still be called inside a larger transaction.
CREATE OR REPLACE PROCEDURE delete_album_proc(p_album_id INT, p_user_id INT)
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM music_album
        WHERE id = p_album_id AND created_by_id = p_user_id
    ) THEN
        RAISE EXCEPTION 'Album % does not exist or is not owned by user %',
            p_album_id, p_user_id;
    END IF;

    DELETE FROM music_trackcredit
    WHERE track_id IN (SELECT id FROM music_track WHERE album_id = p_album_id);
    DELETE FROM music_playlisttrack
    WHERE track_id IN (SELECT id FROM music_track WHERE album_id = p_album_id);
    DELETE FROM music_likedtrack
    WHERE track_id IN (SELECT id FROM music_track WHERE album_id = p_album_id);
    DELETE FROM music_playhistory
    WHERE track_id IN (SELECT id FROM music_track WHERE album_id = p_album_id);
    DELETE FROM music_grouptrack
    WHERE track_id IN (SELECT id FROM music_track WHERE album_id = p_album_id);

    -- music_trackaudio rows go automatically (ON DELETE CASCADE)
    DELETE FROM music_track WHERE album_id = p_album_id;

    DELETE FROM music_albumcredit WHERE album_id = p_album_id;
    DELETE FROM music_album WHERE id = p_album_id AND created_by_id = p_user_id;
END;
$$;

-- 4. Trigger to number playlist entries
-- Fills in position as "last position in this playlist + 1" when the
-- INSERT leaves it out.  Locking the playlist row first makes two adds to
-- the same playlist take turns, so they can never get the same number.
CREATE OR REPLACE FUNCTION playlisttrack_set_position_fn()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.position IS NULL THEN
        PERFORM 1 FROM music_playlist WHERE id = NEW.playlist_id FOR UPDATE;

        SELECT COALESCE(MAX(position), 0) + 1 INTO NEW.position
        FROM music_playlisttrack
        WHERE playlist_id = NEW.playlist_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS playlisttrack_position_trigger ON music_playlisttrack;
CREATE TRIGGER playlisttrack_position_trigger
BEFORE INSERT ON music_playlisttrack
FOR EACH ROW
EXECUTE FUNCTION playlisttrack_set_position_fn();
