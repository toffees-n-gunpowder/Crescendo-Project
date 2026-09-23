-- Triggers, Functions, and Procedures

-- 1. Create a shadow table for audit
CREATE TABLE IF NOT EXISTS music_track_audit (
    audit_id SERIAL PRIMARY KEY,
    track_id INT,
    title VARCHAR(255),
    action VARCHAR(50),
    action_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trigger function
CREATE OR REPLACE FUNCTION audit_track_insert_fn()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO music_track_audit (track_id, title, action)
    VALUES (NEW.id, NEW.title, 'INSERT');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger
DROP TRIGGER IF EXISTS track_insert_trigger ON music_track;
CREATE TRIGGER track_insert_trigger
AFTER INSERT ON music_track
FOR EACH ROW
EXECUTE FUNCTION audit_track_insert_fn();

-- 2. Function to get track count
CREATE OR REPLACE FUNCTION get_artist_track_count(p_artist_id INT)
RETURNS INT AS $$
DECLARE
    v_count INT;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM music_track t
    JOIN music_trackcredit tc ON tc.track_id = t.id
    WHERE tc.artist_id = p_artist_id;
    RETURN COALESCE(v_count, 0);
END;
$$ LANGUAGE plpgsql;

-- 3. Procedure to delete album safely
CREATE OR REPLACE PROCEDURE delete_album_proc(p_album_id INT, p_user_id INT)
LANGUAGE plpgsql
AS $$
BEGIN
    -- Verify ownership indirectly if needed, or assume it's done before calling
    -- We'll delete tracks associated with the album first
    DELETE FROM music_track WHERE album_id = p_album_id;
    -- Then delete the album
    DELETE FROM music_album WHERE id = p_album_id;
    
    COMMIT;
END;
$$;
