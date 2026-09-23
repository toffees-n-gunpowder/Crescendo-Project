-- Crescendo - audio stored in the database
--
-- Uploaded audio used to be written to media/uploads/ on whichever machine
-- served the request, and only the path was stored in music_track.audio_file.
-- Both developers share one Neon database but not one filesystem, so the row
-- was visible everywhere and the sound was playable on exactly one PC.
--
-- Holding the bytes in the database makes the audio as shared as the row.
--
-- A separate table rather than a column on music_track: every catalogue query
-- selects from music_track, and none of them want to drag a multi-megabyte
-- column along for the ride.
--
-- Run with:  python manage.py apply_schema

CREATE TABLE IF NOT EXISTS music_trackaudio (
    track_id      BIGINT       PRIMARY KEY
                               REFERENCES music_track(id) ON DELETE CASCADE,
    content       BYTEA        NOT NULL,
    content_type  VARCHAR(100) NOT NULL DEFAULT 'audio/mpeg',
    byte_size     INTEGER      NOT NULL,
    original_name VARCHAR(255) NOT NULL DEFAULT '',
    uploaded_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- A zero-length row would serve a silent file and look like a player bug.
ALTER TABLE music_trackaudio DROP CONSTRAINT IF EXISTS music_trackaudio_size_check;
ALTER TABLE music_trackaudio
    ADD CONSTRAINT music_trackaudio_size_check CHECK (byte_size > 0);
