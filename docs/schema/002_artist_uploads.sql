-- Crescendo - artist uploads and admin approval
--
-- Gives the artist role a capability listeners do not have (CSE216 §3.2:
-- "Distinct capability per role ... differences must be visible"), and gives
-- admins something to moderate.
--
-- Flow:  artist uploads -> status 'pending' -> admin approves or rejects
--        only 'approved' tracks appear in the public catalogue
--
-- Existing seeded tracks default to 'approved' so the catalogue is unaffected.
--
-- Run with:  python manage.py apply_schema

ALTER TABLE music_track
    ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20)  NOT NULL DEFAULT 'approved',
    ADD COLUMN IF NOT EXISTS submitted_by_id BIGINT       NULL
                             REFERENCES music_user(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS submitted_at    TIMESTAMPTZ  NULL,
    ADD COLUMN IF NOT EXISTS reviewed_by_id  BIGINT       NULL
                             REFERENCES music_user(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS reviewed_at     TIMESTAMPTZ  NULL,
    ADD COLUMN IF NOT EXISTS review_note     VARCHAR(500) NOT NULL DEFAULT '';

-- Only these three states are meaningful; anything else is a bug.
ALTER TABLE music_track DROP CONSTRAINT IF EXISTS music_track_approval_status_check;
ALTER TABLE music_track
    ADD CONSTRAINT music_track_approval_status_check
    CHECK (approval_status IN ('pending', 'approved', 'rejected'));

-- Who owns an album, so an artist can only delete their own.
ALTER TABLE music_album
    ADD COLUMN IF NOT EXISTS created_by_id BIGINT NULL
                             REFERENCES music_user(id) ON DELETE SET NULL;

-- The public catalogue filters on approval_status on every query.
CREATE INDEX IF NOT EXISTS music_track_approval_status_idx
    ON music_track (approval_status);

-- "My uploads" and the admin approval queue both filter by submitter.
CREATE INDEX IF NOT EXISTS music_track_submitted_by_idx
    ON music_track (submitted_by_id);

CREATE INDEX IF NOT EXISTS music_album_created_by_idx
    ON music_album (created_by_id);
