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
psycopg2 escapes them. The only text ever interpolated into SQL is identifiers
we control — an `ORDER BY` clause chosen from a fixed whitelist, and a table
name checked against a hard-coded allowlist.

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
| `toggle_like` | existence check, then INSERT or DELETE | **[done]** |
| `add_to_playlist` | ownership check, duplicate check, position, INSERT | **[done]** |
| `my_library`, `playlists`, `playlist_detail`, `remove_from_playlist`, `delete_playlist`, `rename_playlist`, `dashboard` | see file | **[done]** |
| `dictfetchall(cursor)` | helper — zips `cursor.description` with rows | **[done]** |

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

**`AuthUser`** — the object on `request.user`; identity and role only, no write
methods. `role` resolves admin from `is_staff`/`is_superuser`, else
`account_type`. **`AnonymousUser`** — falsy stand-in.

### `sessions.py` — server-side sessions (table `app_session`)

| Function | Returns | Mechanism |
|---|---|---|
| `create(user_id, ua, ip)` **[done]** | session key | 32 random bytes from `secrets` → 64 hex chars, INSERTed with a 14-day expiry. |
| `get_user_id(key)` **[done]** | id or `None` | `WHERE session_key = %s AND expires_at > NOW()` — expiry enforced in SQL. |
| `destroy(key)` **[done]** | rows deleted | **DELETEs the row** — what makes logout a genuine invalidation (§3.1) rather than a frontend redirect. |
| `destroy_all_for_user(id)` **[done]** | rows deleted | Log out everywhere, e.g. after a password change. |
| `purge_expired()` **[done]** | rows deleted | Housekeeping sweep. |
| `set_cookie` / `clear_cookie` **[done]** | response | `HttpOnly` (JS can't read it, so XSS can't steal it), `SameSite=Lax`. Set `secure=True` once served over HTTPS. |

### `middleware.py` / `decorators.py`

- **`SessionAuthMiddleware`** **[done]** — reads the cookie, resolves it through
  `app_session`, attaches `request.user`. Role comes from the database row,
  never from the cookie.
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
| `get_or_create_artist / _genre / _era` **[done]** | SELECT, else `INSERT ... ON CONFLICT DO NOTHING RETURNING id`, else re-SELECT. |
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

All eight management commands and both services (`jamendo.py`, `composers.py`)
go through this module.

---

## 7. Schema management

`manage.py migrate` is gone with the ORM. Schema now lives in DDL scripts, which
§2.2 expects the repository to have anyway.

- `docs/schema/*.sql` — source of truth. Currently `001_app_session.sql`.
- `manage.py apply_schema` **[done]** — runs them in filename order; every script
  is written re-runnable (`CREATE TABLE IF NOT EXISTS`).
- `docs/legacy_migrations_40pct/` — the 40% milestone's ORM migrations, retired.
  They created the live `music_*` tables but no longer run.

**[todo]** Dump the existing `music_*` tables to `docs/schema/000_core.sql` so a
fresh database can be built from scripts alone rather than relying on the tables
already existing in Neon.

---

## 8. Verification performed

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

## 9. Not yet built (guideline gaps)

| Requirement | Status |
|---|---|
| §3.2 role separation — distinct capability per role, cross-role blocked | **[todo]** decorators exist and are wired to `login_required`; no view yet uses `role_required`, and there is no admin-only or artist-only feature to demonstrate. |
| §3.2 object-level ownership checks | **[done]** for playlists (`WHERE id = %s AND user_id = %s`); needs auditing across every other user-owned record. |
| §3.3 REST endpoints for ≥20% of features | **[todo]** only `toggle_like` and `add_to_playlist` answer JSON today. |
| §3.4 role-aware interface | **[todo]** the UI is identical for listener and artist. |
