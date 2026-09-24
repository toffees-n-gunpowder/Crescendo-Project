# Crescendo — Backend SQL Function Reference

Running record of every backend data-access function: what it takes, what it
returns, and how it works. Backend/SQL only — no frontend or template helpers.

**Rule being satisfied (CSE216 60% guidelines §4):** *"Using ORM is strictly
prohibited. You must write raw SQL queries. You can build own ORM."*
Plus §3.3: *"All database access must use parameterized queries; string-
concatenated SQL will be penalised as an SQL-injection defect."*

**Status: no Django ORM remains anywhere in the project.** `django.contrib.admin`,
`auth`, `contenttypes` and `sessions` are all removed from `INSTALLED_APPS`;
`models.py` defines no models; `manage.py migrate` is no longer used.

**Injection policy, applied everywhere below:** user values are *never* placed
into SQL text. They travel as `%s` placeholders in a separate params list, so
psycopg2 escapes them. The only text ever interpolated into SQL is text we
control — an `ORDER BY` clause chosen from a fixed whitelist, table names taken
from hard-coded tuples or allowlists, and the two fixed clauses `list_groups`
picks between in code.

**Where logic lives:** rules that must never be skipped (auditing, numbering,
safe deletes, security checks) run inside PostgreSQL as PL/pgSQL triggers,
functions and procedures — see §8b. Python calls them with `SELECT fn(...)` or
`CALL proc(...)`.

Status legend: **[done]** implemented and verified · **[todo]** planned

---

## 1. `music/db/core.py` — the mini-ORM foundation

| Function | Arguments | Returns | Mechanism |
|---|---|---|---|
| `query(sql, params)` **[done]** | SQL, params | `list[Row]` | Executes, reads `cursor.description` for column names, zips each record into a dict, passes through `_nest()`. |
| `query_one(sql, params)` **[done]** | as above | `Row` or `None` | For lookups expected to match at most one row. |
| `scalar(sql, params)` **[done]** | as above | single value | `fetchone()[0]`. Used for `COUNT(*)`, `EXISTS`, `RETURNING id`. |
| `execute(sql, params)` **[done]** | as above | rows affected | INSERT / UPDATE / DELETE. |
| `insert_returning_id(sql, params)` **[done]** | as above | new primary key | Wrapper over `scalar()`. |
| `_nest(flat)` **[done]** | flat dict | `Row` | Splits keys on `__`: `album__title` becomes `row.album.title`. A child whose columns are all NULL becomes `None`, so `{% if track.album %}` still behaves. |
| `paginate(rows, total, number, per_page)` **[done]** | rows + total | `Page` | Wraps rows already limited in SQL. |
| `page_number(raw, num_pages)` **[done]** | `?page=` value | `int` ≥ 1 | Coerces junk (`abc`, `-3`, `999`) to a valid page; clamps to the last page. |

**Classes** — `Row` (attribute access; falsy when every value is `None`),
`RelatedList` (a `list` that also answers `.all`, keeping the
`{% for a in track.artists.all %}` idiom), `Page` (replaces Django's
`Paginator`, exposing `number`, `count`, `num_pages`, `has_previous()`,
`has_next()`, `has_other_pages()`, `previous_page_number()`,
`next_page_number()`, `paginator`).

---

## 2. `music/db/tracks.py` — catalogue reads

**Constants:** `SELECT_COLUMNS` (aliases use `__` to drive nesting) ·
`FROM_JOINS` (INNER JOIN album, LEFT JOIN genre and era, both nullable) ·
`ORDER_CLAUSES` (**whitelist** of sort name → ORDER BY text; the only place SQL
text is chosen dynamically) · `ARTIST_EXISTS` (correlated `EXISTS` against
`music_trackcredit`, used instead of a JOIN because a track has several
credited artists and a join would duplicate rows).

| Function | Returns | Mechanism |
|---|---|---|
| `build_conditions(filters, tokens, artist_tokens)` **[done]** | `(where[], params[])` | The core of filtering. One fragment per active filter; empty values are skipped. Genre/era use `LOWER(x)=LOWER(%s)`; album uses `ILIKE %value%`; year uses `EXTRACT(YEAR FROM ...)`; decade becomes `BETWEEN start AND start+9`. Each artist word adds an `ARTIST_EXISTS`; each search word adds an OR-group across title/album/genre/era/artist. Caller ANDs the fragments. |
| `count_tracks(where, params)` **[done]** | `int` | `SELECT COUNT(*)` over the same joins. Drives the paginator and the "N results" line. |
| `fetch_page(where, params, sort, page, per_page)` **[done]** | `list[Row]` | Adds whitelisted `ORDER BY` plus `LIMIT %s OFFSET %s`. Paging happens in SQL — the catalogue is never pulled into Python to be sliced. |
| `attach_artists(rows)` **[done]** | rows, mutated | One query with `WHERE tc.track_id IN (...)` for the whole page, avoiding an N+1. Orders primary → featured → producer → writer so cards read "Performer, Composer". Also sets `formatted_duration`. |
| `format_duration(seconds)` **[done]** | `"3:27"` | Replaces the old model property. |
| `genre_counts` / `era_counts` / `year_counts` **[done]** | rows of `{name, count}` | `GROUP BY` with `COUNT(DISTINCT t.id)` — DISTINCT matters because artist conditions can multiply rows. `era_counts` adds `e.name !~ '^[0-9]{4}s$'` so a decade can never appear as a musical period. |
| `search_vocabulary(limit)` **[done]** | `list[str]` | `UNION` of track titles, artist names, album titles, genre names. Feeds typo correction. |
| `artist_names(limit)` **[done]** | `list[str]` | For fuzzy-matching the artist filter. |

---

## 3. `music/services/search.py` — search orchestration

No SQL of its own; composes §2. Kept separate so filtering is testable from the
shell without an HTTP request.

| Function | Returns | Mechanism |
|---|---|---|
| `search_tracks(params, page, per_page)` **[done]** | `SearchResult` | Entry point: read filters → build conditions → count → rescue an empty result → fetch page → compute facets. |
| `read_filters(params)` **[done]** | dict of 6 keys | Missing becomes `''` (= inactive). |
| `_conditions(filters, query, exclude)` **[done]** | `(where[], params[])` | `exclude` blanks named dimensions — the mechanism behind facet self-exclusion. |
| `_decade_start(value)` **[done]** | `2010` | Strips non-digits, floors to the decade. |
| `facets(filters, query)` **[done]** | 4 option lists | Runs the count queries **three times**, each excluding its own dimension — otherwise picking "2010s" would hide every other decade and you could never switch. |
| `_options(pairs, selected)` **[done]** | `{name, count}` list | Drops zero-count dead ends but always keeps the selected value so the `<select>` doesn't lose state. |
| `close_matches(query, limit)` **[done]** | `list[str]` | `difflib` against catalogue vocabulary. Indexes whole phrases *and* individual words — "beethovan" vs the full "Ludwig van Beethoven" scores too low as a whole-string comparison. |
| `_closest_artist(value)` **[done]** | name or `None` | Same trick, restricted to artist names. |

---

## 4. `music/views.py` — inline SQL

| View | SQL | Status |
|---|---|---|
| `home` | liked track ids; user playlists | **[done]** |
| `genres` | total count; genres + count + one cover per genre (correlated subquery) | **[done]** |
| `register_user` / `login_user` / `logout_user` | via `music/auth/` | **[done]** |
| `toggle_like` | existence check, then `SELECT toggle_like(user, track)` (PL/pgSQL, `005_business_rules.sql`) | **[done]** |
| `add_to_playlist` | ownership check, duplicate check, INSERT (position set by `playlisttrack_position_trigger`) | **[done]** |
| `my_library`, `playlists`, `playlist_detail`, `remove_from_playlist`, `delete_playlist`, `rename_playlist`, `dashboard` | see file | **[done]** |
| `eras` | total count; `catalog.era_counts()` + one cover per era | **[done]** |
| `admin_panel` | `users.list_users()`, `role_counts()`, `admin_count()` — admin only | **[done]** |
| `admin_set_role` / `admin_set_active` | `users.set_account_type` / `promote_to_admin` / `set_active`; `LastAdminError` shown as a message | **[done]** |
| `dictfetchall(cursor)` | helper — zips `cursor.description` with rows | **[done]** |

## 4b. Other view modules

| Module | Views | Data access |
|---|---|---|
| `views_artist.py` | `artist_studio`, `artist_upload`, `artist_update_profile`, `artist_delete_track`, `artist_delete_album` (artist or admin); `admin_approvals`, `admin_review_track` (admin) | `uploads.*`, `audio.store`, `get_artist_track_count()`, `CALL delete_album_proc`, `uploads.set_review` → `CALL review_track` |
| `views_artistpage.py` | `artist_detail`, `toggle_follow` | `artists.*` |
| `views_social.py` | `history`, `follows`, `toggle_follow`, `record_play` (JSON), `groups`, `group_detail` (review, add/remove track or playlist, delete review, delete group, visibility) | `social.*`, `artists.toggle_follow` |
| `views_audio.py` | `track_audio` — streams uploaded audio with HTTP range support | `audio.meta` + `audio.chunk`; pending/rejected audio only for its uploader or an admin |

---

## 5. `music/auth/` — authentication and authorization

Replaces `django.contrib.auth`.

### `hashing.py`

| Function | Returns | Mechanism |
|---|---|---|
| `hash_password(raw)` **[done]** | hash string | **scrypt** — named in §3.1 and in Python's stdlib, so no new dependency. 16 fresh random salt bytes from `secrets`. Stored as `scrypt$n$r$p$salt_hex$digest_hex`. |
| `verify(raw, stored)` **[done]** | `(is_valid, needs_upgrade)` | Constant-time compare via `hmac.compare_digest`, so a wrong password can't be found by timing. Also understands the legacy `pbkdf2_sha256$...` hashes from the 40% milestone — via `hashlib`, not Django — so the 4 existing accounts aren't locked out; they upgrade to scrypt on next login. |

### `users.py`

| Function | Returns | Mechanism |
|---|---|---|
| `authenticate(username, password)` **[done]** | `Row` or `None` | SELECT by `LOWER(username)`, verify hash, silently upgrade a legacy hash. |
| `create_user(...)` **[done]** | `Row` | `INSERT ... RETURNING id` with a salted hash. Role is whitelisted server-side — a client-supplied role is never trusted (§4). |
| `get_by_id` / `get_by_username` **[done]** | `Row` or `None` | Parameterised SELECT; `get_by_id` also requires `is_active`. |
| `username_exists` / `email_exists` **[done]** | `bool` | `SELECT 1 ... LIMIT 1`, case-insensitive. Drives the 409 on duplicate registration. |
| `set_password` / `touch_last_login` **[done]** | rows affected | UPDATE. |
| `get_any_by_id` **[done]** | `Row` or `None` | Like `get_by_id` but also finds deactivated users — for the admin panel. |
| `list_users(limit)` / `role_counts()` / `admin_count()` **[done]** | rows / int | Admin panel: users with playlist and like counts (correlated subqueries), users per role, number of admins. |
| `promote_to_admin(id)` **[done]** | rows affected | Sets `is_staff` and `is_superuser`. |
| `set_account_type(id, role)` / `set_active(id, bool)` **[done]** | rows affected | UPDATE through `_execute_user_update`, which turns the `keep_last_admin_trigger` error (SQLSTATE `CR001`) into **`LastAdminError`**. Deactivating also logs the user out everywhere via `user_deactivated_trigger`. |

**`AuthUser`** — the object on `request.user`; identity and role only, no write
methods. `role` resolves admin from `is_staff`/`is_superuser`, else
`account_type`. **`AnonymousUser`** — falsy stand-in.

### `sessions.py` — server-side sessions (table `app_session`)

| Function | Returns | Mechanism |
|---|---|---|
| `create(user_id, ua, ip)` **[done]** | session key | 32 random bytes from `secrets` → 64 hex chars, INSERTed with a 14-day expiry. |
| `get_user_id(key)` **[done]** | id or `None` | `WHERE session_key = %s AND expires_at > NOW()` — expiry enforced in SQL. |
| `destroy(key)` **[done]** | rows deleted | **DELETEs the row** — what makes logout a genuine invalidation (§3.1) rather than a frontend redirect. |
| `destroy_all_for_user(id)` **[done]** | rows deleted | Log out everywhere. Used by `purge_sessions --user`; deactivation no longer needs it because `user_deactivated_trigger` does it in the database. |
| `purge_expired()` **[done]** | rows deleted | Housekeeping sweep. |
| `set_cookie` / `clear_cookie` **[done]** | response | `HttpOnly` (JS can't read it, so XSS can't steal it), `SameSite=Lax`. Set `secure=True` once served over HTTPS. |

### `middleware.py` / `decorators.py`

- **`SessionAuthMiddleware`** **[done]** — reads the cookie, resolves it through
  `app_session`, attaches `request.user`. Role comes from the database row,
  never from the cookie. It is also a **site-wide login gate**: any request
  without a valid cookie is redirected to `/login/`, except `/login`,
  `/register`, `/admin`, static and media paths. **Known issue:** `/api/` is not
  on that list, so the token-based API (§6h) is unreachable — see §9.
- **`auth_context`** **[done]** — context processor providing `user`,
  `is_admin`, `is_artist`.
- **`login_required`** **[done]** — 401 JSON for API callers, redirect for browsers.
- **`role_required(*roles)`** **[done]** — 401 anonymous, **403** wrong role.
  Enforced server-side, so the endpoint can't be reached with curl/Postman (§3.2).
- **`admin_required`** / **`artist_required`** **[done]** — wrappers.

---

## 6. `music/db/catalog.py` — catalogue writes and maintenance

| Function | Mechanism |
|---|---|
| `get_or_create_artist` **[done]** | SELECT by name, else `INSERT ... RETURNING id`. |
| `get_or_create_genre / _era` **[done]** | SELECT, else `INSERT ... ON CONFLICT (name) DO NOTHING RETURNING id`, else re-SELECT — safe if two imports create the same name at once. |
| `find_album(title, artist_id)` **[done]** | Joins `music_albumcredit` so lookup is per artist — matching on title alone would merge every "Greatest Hits" from different artists. |
| `create_album`, `set_album_cover_if_blank`, `clear_album_covers` **[done]** | INSERT / conditional UPDATE / `UPDATE ... WHERE id = ANY(%s)`. |
| `add_album_credit`, `add_track_credit` **[done]** | `INSERT ... SELECT ... WHERE NOT EXISTS` — insert-if-absent without needing a unique constraint. |
| `find_track`, `create_track`, `set_track_title` **[done]** | Parameterised SELECT / INSERT / UPDATE. |
| `backfill_track_fields` **[done]** | `COALESCE` inside the UPDATE fills only columns that were NULL/blank, so no read is needed first. |
| `renumber_tracks_within_albums` **[done]** | One `UPDATE ... FROM (SELECT ROW_NUMBER() OVER (PARTITION BY album_id ORDER BY id))` — replaces the ORM version's 96-album read-modify-write loop with a single round trip. |
| `genre_counts`, `era_counts`, `track_count_by_album` **[done]** | `LEFT JOIN ... GROUP BY`, so genres/eras with zero tracks still appear. |
| `move_tracks_to_genre`, `delete_genre`, `delete_eras` **[done]** | UPDATE / DELETE. `Track.era` is `ON DELETE SET NULL`, so deleting an era keeps its tracks. |
| `count(table)` **[done]** | `COUNT(*)`; `table` is checked against a hard-coded allowlist and raises otherwise — never user input. |
| `flush_catalogue()` **[done]** | DELETEs in foreign-key-safe order. Users untouched. |

The seeding and clean-up commands (§6g) and the `jamendo.py` / `composers.py`
services go through this module.

---

## 6b. `music/db/artists.py` — artist pages

Every read counts only approved tracks (`APPROVED_ONLY`).

| Function | Returns | Mechanism |
|---|---|---|
| `get(id)` **[done]** | `Row` or `None` | Artist plus the username that claimed it (`LEFT JOIN music_user`). |
| `stats(id)` **[done]** | `Row` | Three scalar subqueries in one SELECT: tracks, albums, followers. |
| `roles_played(id)` / `genres(id)` **[done]** | rows | `GROUP BY` role / genre with `COUNT(DISTINCT t.id)`. |
| `tracks(id, limit, offset)` **[done]** | rows | Credited tracks, newest album first, then `tracks.attach_artists`. |
| `albums(id)` **[done]** | rows | `COUNT(...) FILTER (WHERE approved)` with `HAVING > 0`, so albums with no public track are hidden. |
| `is_following(user, artist)` **[done]** | `bool` | `SELECT 1 ... LIMIT 1`. |
| `toggle_follow(user, artist)` **[done]** | `bool` | `SELECT toggle_follow(...)` (PL/pgSQL). The single follow implementation — the old duplicate in `social.py` is gone. |
| `find_by_name(name)` | `Row` | Currently unused. |

## 6c. `music/db/playlists.py`

| Function | Returns | Mechanism |
|---|---|---|
| `get_owned(id, user)` **[done]** | `Row` or `None` | `WHERE id = %s AND user_id = %s` — the ownership check behind every playlist edit. |
| `list_for_user(user)` **[done]** | rows | `LEFT JOIN ... GROUP BY` so empty playlists show 0 tracks. |
| `tracks_in(id, user)` **[done]** | rows | Ordered by `position`; checks ownership and approval in the same query. |
| `create`, `set_visibility`, `liked_ids` **[done]** | id / rows affected / ids | INSERT ... RETURNING / owner-scoped UPDATE / SELECT. |

## 6d. `music/db/uploads.py` — Artist Studio and approvals

| Function | Returns | Mechanism |
|---|---|---|
| `profile_for_user` / `get_or_create_profile` / `update_profile` **[done]** | row / id / rows | Links a user to an artist row: reuses their own, else claims an unclaimed artist with the same name, else creates one. |
| `create_album(...)` **[done]** | id | INSERT album (with `created_by_id`) + primary album credit. |
| `albums_for_user` / `tracks_for_user` / `counts_for_user` **[done]** | rows / row | `COUNT(*) FILTER (WHERE approval_status = ...)` gives total, approved, pending, rejected in one pass. |
| `find_own_album` / `find_own_track` **[done]** | `Row` or `None` | Ownership checks (`created_by_id` / `submitted_by_id`). |
| `create_pending_track(...)` **[done]** | id | INSERT as `pending` + primary credit. Leaves `track_number` NULL so `track_number_trigger` numbers it. |
| `set_audio_url` **[done]** | rows affected | Points the track at `/track/<id>/audio/`. |
| `delete_own_track(id, user)` **[done]** | rows deleted | Clears credits, playlist entries, likes, history and group entries (table names from a fixed tuple), then the track. |
| `review_queue(status)` / `pending_count()` **[done]** | rows / int | Admin approval queue, oldest first. |
| `set_review(track, status, admin, note)` **[done]** | — | `CALL review_track(...)` (PL/pgSQL). |

## 6e. `music/db/audio.py` — uploaded audio stored in the database

Audio bytes live in `music_trackaudio.content` (`bytea`), so every server sees
the same files.

| Function | Returns | Mechanism |
|---|---|---|
| `store(track, bytes, type, name)` **[done]** | rows | Replaces any existing row for the track. |
| `meta(track)` **[done]** | `Row` | Size, type, and the track's approval status and uploader, for the permission check. |
| `chunk(track, offset, length)` **[done]** | `bytes` | `SUBSTRING(content FROM %s FOR %s)` — reads only the requested byte range, so streaming never loads the whole file. |
| `delete`, `exists`, `total_bytes`, `content_type_for` **[done]** | — | Housekeeping. |

## 6f. `music/db/social.py` — history, follows, groups

| Function | Returns | Mechanism |
|---|---|---|
| `record_play_once(user, track)` **[done]** | `bool` | `SELECT record_play(...)` (PL/pgSQL) — skips a repeat within 30 s. |
| `get_play_history(user, limit)` **[done]** | rows | `SELECT * FROM get_play_history(...)` — a table-returning PL/pgSQL function. |
| `get_followed_artists(user)` **[done]** | rows | JOIN follow → artist, newest first. |
| `create_group`, `get_group`, `update_group_visibility` **[done]** | id / row / — | INSERT ... RETURNING / SELECT with owner name / UPDATE. |
| `list_groups(user, search)` **[done]** | rows | Public groups plus the user's own, average rating via `LEFT JOIN ... AVG`, optional `ILIKE` search (parameterised); own groups sorted first. |
| `add_group_track` / `add_group_playlist` **[done]** | rows | Check-then-INSERT. |
| `group_tracks` / `group_playlists` / `group_reviews` **[done]** | rows | `STRING_AGG` joins artist names into one string. |
| `addable_tracks` / `addable_playlists` / `track_is_addable` / `playlist_is_addable` **[done]** | rows / `bool` | `NOT IN (subquery)` excludes what's already in the group; playlists must be the user's own or public. |
| `remove_group_track` / `remove_group_playlist` / `delete_own_review` **[done]** | rows deleted | Owner- or reviewer-scoped DELETE. |
| `add_group_review(...)` **[done]** | — | `CALL save_group_review(...)` (PL/pgSQL) — enforces 1-5 stars, one review per user. |
| `delete_group(group, owner)` **[done]** | 1 or 0 | Ownership check, then `CALL delete_group_proc(...)`. |

## 6g. Services and management commands

**Services** (`music/services/`):
- `search.py` — see §3.
- `jamendo.py` — fetches tracks from the Jamendo API and imports them through `catalog.py`.
- `composers.py` — recognises classical composers in titles and credits them as writers.
- `imagehash.py` — perceptual hashing to spot the same cover art reused across albums.
- `console.py` — safe printing of non-ASCII titles on Windows consoles.

**Management commands** (`python manage.py <name>`):

| Command | Purpose |
|---|---|
| `apply_schema` | Runs `docs/schema/*.sql` in order (§7). |
| `seed_data` / `seed_classical` | Import tracks from Jamendo. |
| `backfill_composers` / `backfill_track_numbers` | Fill in composer credits / number album tracks 1..n. |
| `clean_eras` / `clean_titles` / `prune_genres` / `dedupe_covers` | Catalogue clean-up. |
| `import_local_audio` | Moves audio still in `media/` into `music_trackaudio`. |
| `create_admin` | Creates or promotes an admin account. |
| `purge_sessions` | Deletes expired sessions (`--user` logs one user out everywhere). |

## 6h. `music/api/` — JSON API

A second way into the app that answers JSON instead of HTML, authenticated with
a **Bearer token** (the same `app_session` key, sent as
`Authorization: Bearer <key>`) instead of a cookie. 21 routes under `/api/`.

- **`helpers.py`** — `@api(methods)` (method check, token lookup, errors → JSON),
  `@auth_required`, `@role_required`, response helpers (`ok`, `created`,
  `not_found`, `conflict`, ...), and `track_json` / `user_json` / ... serialisers.
- **`views.py`** — auth (`register`, `login`, `logout`, `me`); catalogue
  (`tracks`, `tracks/<id>`, `genres`, `artists/<id>`); playlists (list, create,
  rename, delete, add/remove track); likes and follows (`PUT` to add, `DELETE`
  to remove); studio (artist's tracks, delete); admin (users, change role or
  active, approval queue, approve/reject).

It reuses the same `db/` functions and PL/pgSQL routines as the website.
**Currently unreachable** because of the middleware issue in §5 and §9.

---

## 7. Schema management

`manage.py migrate` is gone with the ORM. Schema now lives in DDL scripts, which
§2.2 expects the repository to have anyway.

- `docs/schema/*.sql` — source of truth, applied in filename order:

  | Script | Contents |
  |---|---|
  | `000_core.sql` | All `music_*` tables, keys, unique/check constraints and indexes |
  | `001_app_session.sql` | `app_session` (login sessions) |
  | `002_artist_uploads.sql` | Approval columns on tracks, album ownership |
  | `003_db_features.sql` | Track audit trigger, `get_artist_track_count`, `delete_album_proc`, playlist position trigger |
  | `004_track_audio.sql` | `music_trackaudio` (audio bytes in the database) |
  | `005_business_rules.sql` | Track number, deactivation logout and last-admin triggers; `toggle_like`, `toggle_follow`; `review_track` |
  | `006_social_rules.sql` | `save_group_review`, `record_play`, `get_play_history`, `delete_group_proc` |

- `manage.py apply_schema` **[done]** — runs them in order; every script is
  re-runnable (`IF NOT EXISTS`, `CREATE OR REPLACE`, `DROP TRIGGER IF EXISTS`).
  A fresh database can be built from these scripts alone.
- `docs/legacy_migrations_40pct/` — the 40% milestone's ORM migrations, retired.

---

## 8. Verification performed

*Recorded when the ORM was removed. Tests of the PL/pgSQL routines are
summarised under §8b.*

**Filtering** — 26 filter combinations compared before/after conversion, all
match. (`q=rock` differs only because the old baseline was recorded when the DB
held 20 tracks.) Facets confirmed contextual: `genre=Metal` offers only
2000s/2010s and hides the period dropdown; `decade=2020s` still lists all three
decades. Fuzzy: `beathoven`→Beethoven, `mozzart`→Mozart, `beethovan`→Ludwig van
Beethoven, `chopan`→Frederic Chopin; `xyzzyqq` correctly returns 0. Pagination:
pages 1 / 2 / 33 / 99 / `abc` all resolve sanely across 33 pages.

**Authentication cycle**

| Step | Result |
|---|---|
| Register | 302 → `/login/`, no auto-login; stored with a `scrypt$` hash and role `artist` |
| Register same username again | **409 Conflict** |
| Login, wrong password | **401**, zero session rows created |
| Login, unknown username | **401** + "create an account first" panel |
| Login, correct | 302, `HttpOnly` `SameSite=Lax` cookie, 64-char key, 1 session row |
| Authenticated page load | 200, username rendered |
| Logout | session row **DELETEd** (count → 0) |
| Replay the old cookie | does **not** authenticate |

Hashing: the same password hashed twice gives different output (unique salt);
legacy `pbkdf2_sha256` hashes still verify, so no existing account is locked out.

**Authorization**

| Request | Result |
|---|---|
| `GET /library/`, `/playlists/`, `/dashboard/` anonymous | 302 → `/login/?next=...` |
| `POST /like/3/` anonymous with `X-Requested-With: XMLHttpRequest` | **401** `{"error": "authentication_required"}` |
| `GET /admin/` | **404** — the ORM-backed admin site is gone |

**Pages** — `/`, `/?genre=Classical&artist=mozart`, `/?q=beathoven`, `/?page=2`,
`/genres/`, `/login/`, `/register/` all HTTP 200 with correct card counts and no
tracebacks.

**Management commands** — all nine load and run. Dry-runs against live data
report zero outstanding work, confirming the SQL versions read the same state the
ORM versions left: `prune_genres` "every genre already has 10+",
`clean_eras` "no decade rows", `clean_titles` 0 rewrites,
`backfill_track_numbers` 0 mis-numbered, `backfill_composers` nothing new.

---

## 8b. Database-side logic (PL/pgSQL)

Defined in `docs/schema/003_db_features.sql`, `005_business_rules.sql` and `006_social_rules.sql`.

| Object | Kind | What it does | Called from |
|---|---|---|---|
| `track_audit_trigger` → `audit_track_change_fn()` | trigger | Logs track INSERT, approval status changes and DELETE into `music_track_audit` | automatic |
| `playlisttrack_position_trigger` | trigger | Fills `position` as last + 1, locking the playlist so concurrent adds take turns | automatic |
| `track_number_trigger` | trigger | Fills `track_number` as last in album + 1, same locking | automatic (`uploads.create_pending_track`) |
| `user_deactivated_trigger` | trigger | Deletes every `app_session` row when `is_active` goes TRUE → FALSE | automatic (`users.set_active`) |
| `keep_last_admin_trigger` | trigger | Refuses demoting, deactivating or deleting the last active admin (SQLSTATE `CR001` → `users.LastAdminError`) | automatic |
| `get_artist_track_count(artist)` | function | Approved tracks credited to the artist, each counted once | `views_artist.artist_studio` |
| `toggle_like(user, track)` | function | Likes or unlikes; returns TRUE if now liked | `views.toggle_like` |
| `toggle_follow(user, artist)` | function | Follows or unfollows; returns TRUE if now following | `artists.toggle_follow` |
| `delete_album_proc(album, user)` | procedure | Ownership check, then deletes the album, its tracks and every row pointing at them | `views_artist.artist_delete_album` |
| `review_track(track, status, admin, note)` | procedure | Validates status, reviewer and track, then records the decision | `uploads.set_review` |
| `record_play(user, track, window)` | function | Adds a play unless the same track was played in the last `window` seconds; returns TRUE if added | `social.record_play_once` |
| `get_play_history(user, limit)` | function (returns a table) | Recent plays with album, cover and artist names, newest first | `social.get_play_history` |
| `save_group_review(group, user, rating, text)` | procedure | Enforces 1-5 stars, then adds or replaces the user's review | `social.add_group_review` |
| `delete_group_proc(group, owner)` | procedure | Ownership check, then deletes the group's tracks, playlists, reviews and the group | `social.delete_group` |

**Verified** against the live database inside transactions that were rolled
back: every refusal path (wrong owner, bad status or rating, non-admin reviewer,
last admin) raises; deletes leave no orphan rows; two simultaneous playlist adds
or play records take turns (the second waits on the lock); `get_play_history`
returns exactly the rows of the query it replaced.

---

## 9. Guideline status and open issues

| Requirement | Status |
|---|---|
| §3.2 role separation — distinct capability per role, cross-role blocked | **[done]** Studio views require artist or admin; approvals and the admin panel require admin (`role_required`, 403 otherwise). |
| §3.2 object-level ownership checks | **[done]** playlists (`user_id`), albums (`created_by_id`), tracks (`submitted_by_id`), groups (`owner_id`), reviews (`reviewer_id`). `delete_album_proc` and `delete_group_proc` re-check ownership inside the database. |
| §3.3 REST endpoints for ≥20% of features | **[built, blocked]** `music/api/` has 21 routes (§6h), but `SessionAuthMiddleware` redirects `/api/` to the login page. **[todo]** add `/api/` to the middleware's allowed paths. |
| §3.4 role-aware interface | **[done]** `auth_context` supplies `is_admin` / `is_artist`; the nav bar, home page and artist page show Studio and admin links only to those roles. |

**Other open items**
- `get_artist_track_count()` is computed for the Studio page but no template displays it yet.
- Unused Python functions: `artists.find_by_name`, `tracks.tracks_matching_artist_exact`, `catalog.top_artists_by_likes`, `jamendo.decade_label`, `composers.period_for`.
