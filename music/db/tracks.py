from music.db import core

PER_PAGE = 20

SELECT_COLUMNS = """
    t.id                AS id,
    t.title             AS title,
    t.audio_file        AS audio_file,
    t.duration_sec      AS duration_sec,
    t.track_number      AS track_number,
    t.album_id          AS album_id,
    t.genre_id          AS genre_id,
    t.era_id            AS era_id,
    a.title             AS album__title,
    a.cover_url         AS album__cover_url,
    a.release_date      AS album__release_date,
    g.name              AS genre__name,
    e.name              AS era__name
"""

FROM_JOINS = """
    FROM music_track t
    JOIN music_album a ON a.id = t.album_id
    LEFT JOIN music_genre g ON g.id = t.genre_id
    LEFT JOIN music_era   e ON e.id = t.era_id
"""

ORDER_CLAUSES = {
    'relevance': 't.track_number ASC, a.title ASC, t.title ASC',
    'album':     'a.title ASC, t.track_number ASC',
    'title':     't.title ASC',
    'newest':    'a.release_date DESC NULLS LAST, t.title ASC',
    'oldest':    'a.release_date ASC NULLS LAST, t.title ASC',
    'longest':   't.duration_sec DESC',
    'shortest':  't.duration_sec ASC',
}
DEFAULT_SORT = 'relevance'

ARTIST_EXISTS = """
    EXISTS (
        SELECT 1
        FROM music_trackcredit tc
        JOIN music_artist ar ON ar.id = tc.artist_id
        WHERE tc.track_id = t.id AND ar.name ILIKE %s
    )
"""


def _like(value):
    return f'%{value}%'


def build_conditions(filters, tokens=None, artist_tokens=None):
    where = []
    params = []

    if filters.get('genre'):
        where.append('LOWER(g.name) = LOWER(%s)')
        params.append(filters['genre'])

    if filters.get('album'):
        where.append('a.title ILIKE %s')
        params.append(_like(filters['album']))

    if filters.get('era'):
        where.append('LOWER(e.name) = LOWER(%s)')
        params.append(filters['era'])

    if filters.get('year'):
        try:
            year = int(filters['year'])
        except (TypeError, ValueError):
            year = None
        if year:
            where.append('EXTRACT(YEAR FROM a.release_date) = %s')
            params.append(year)

    if filters.get('decade'):
        start = filters['decade']
        if start is not None:
            where.append(
                'EXTRACT(YEAR FROM a.release_date) BETWEEN %s AND %s'
            )
            params.extend([start, start + 9])

    for token in (artist_tokens or []):
        where.append(ARTIST_EXISTS)
        params.append(_like(token))

    for token in (tokens or []):
        where.append(f"""(
            t.title ILIKE %s
            OR a.title ILIKE %s
            OR COALESCE(g.name, '') ILIKE %s
            OR COALESCE(e.name, '') ILIKE %s
            OR {ARTIST_EXISTS}
        )""")
        params.extend([_like(token)] * 5)

    return where, params


PUBLIC_ONLY = "t.approval_status = 'approved'"


def _where_sql(where):
    clauses = [PUBLIC_ONLY] + list(where)
    return 'WHERE ' + ' AND '.join(clauses)


def count_tracks(where, params):
    sql = f'SELECT COUNT(*) {FROM_JOINS} {_where_sql(where)}'
    return core.scalar(sql, params) or 0


def fetch_page(where, params, sort, page, per_page=PER_PAGE):
    order = ORDER_CLAUSES.get(sort) or ORDER_CLAUSES[DEFAULT_SORT]
    offset = (max(1, page) - 1) * per_page

    sql = f"""
        SELECT {SELECT_COLUMNS}
        {FROM_JOINS}
        {_where_sql(where)}
        ORDER BY {order}
        LIMIT %s OFFSET %s
    """
    rows = core.query(sql, list(params) + [per_page, offset])
    attach_artists(rows)
    return rows


def attach_artists(rows):
    if not rows:
        return rows

    track_ids = [row.id for row in rows]
    placeholders = ', '.join(['%s'] * len(track_ids))

    sql = f"""
        SELECT tc.track_id AS track_id, ar.id AS artist_id, ar.name AS name, tc.role AS role
        FROM music_trackcredit tc
        JOIN music_artist ar ON ar.id = tc.artist_id
        WHERE tc.track_id IN ({placeholders})
        ORDER BY
            CASE tc.role
                WHEN 'primary'  THEN 0
                WHEN 'featured' THEN 1
                WHEN 'producer' THEN 2
                ELSE 3
            END,
            ar.name
    """
    credits = core.query(sql, track_ids)

    by_track = {}
    for credit in credits:
        by_track.setdefault(credit.track_id, core.RelatedList()).append(
            core.Row({'id': credit.artist_id, 'name': credit.name,
                      'role': credit.role})
        )

    for row in rows:
        row['artists'] = by_track.get(row.id, core.RelatedList())
        row['formatted_duration'] = format_duration(row.duration_sec)

    return rows


def format_duration(seconds):
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        seconds = 0
    return f'{seconds // 60}:{seconds % 60:02d}'


def genre_counts(where, params):
    sql = f"""
        SELECT g.name AS name, COUNT(DISTINCT t.id) AS count
        {FROM_JOINS}
        {_where_sql(where + ['t.genre_id IS NOT NULL'])}
        GROUP BY g.id, g.name
        ORDER BY COUNT(DISTINCT t.id) DESC, g.name ASC
    """
    return core.query(sql, params)


def era_counts(where, params):
    conditions = where + ["t.era_id IS NOT NULL", "e.name !~ '^[0-9]{4}s$'"]
    sql = f"""
        SELECT e.name AS name, COUNT(DISTINCT t.id) AS count
        {FROM_JOINS}
        {_where_sql(conditions)}
        GROUP BY e.id, e.name
        ORDER BY e.name ASC
    """
    return core.query(sql, params)


def year_counts(where, params):
    conditions = where + ['a.release_date IS NOT NULL']
    sql = f"""
        SELECT EXTRACT(YEAR FROM a.release_date)::int AS year,
               COUNT(DISTINCT t.id) AS count
        {FROM_JOINS}
        {_where_sql(conditions)}
        GROUP BY EXTRACT(YEAR FROM a.release_date)
        ORDER BY year DESC
    """
    return core.query(sql, params)


def search_vocabulary(limit=4000):
    sql = """
        SELECT title AS term FROM music_track
        UNION
        SELECT name  AS term FROM music_artist
        UNION
        SELECT title AS term FROM music_album
        UNION
        SELECT name  AS term FROM music_genre
        LIMIT %s
    """
    return [row.term for row in core.query(sql, [limit]) if row.term]


def artist_names(limit=4000):
    sql = 'SELECT name AS name FROM music_artist ORDER BY name LIMIT %s'
    return [row.name for row in core.query(sql, [limit]) if row.name]


def tracks_matching_artist_exact(where, params, name):
    return where + [ARTIST_EXISTS], list(params) + [name]
