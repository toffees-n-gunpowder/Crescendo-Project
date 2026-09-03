-- Crescendo - server-side session store
--
-- Replaces django.contrib.sessions (which is ORM-backed). Sessions live in our
-- own table and are read/written with hand-written SQL.
--
-- Why a table rather than a signed cookie: CSE216 §3.1 requires a logout that
-- "genuinely invalidates the session or token - not merely a redirect on the
-- frontend". A row we can DELETE is genuinely invalidated server-side; a signed
-- cookie can only be asked nicely to go away.
--
-- Run with:  python manage.py apply_schema

CREATE TABLE IF NOT EXISTS app_session (
    session_key  VARCHAR(64)  PRIMARY KEY,
    user_id      BIGINT       NOT NULL
                              REFERENCES music_user(id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ  NOT NULL,
    user_agent   VARCHAR(255) NOT NULL DEFAULT '',
    ip_address   VARCHAR(45)  NOT NULL DEFAULT ''
);

-- Logging out everywhere, and purging a deleted user's sessions, both filter
-- by user.
CREATE INDEX IF NOT EXISTS app_session_user_id_idx
    ON app_session (user_id);

-- The expiry sweep filters by expires_at.
CREATE INDEX IF NOT EXISTS app_session_expires_at_idx
    ON app_session (expires_at);
