import difflib
import re

from music.db import core, tracks as track_db

FUZZY_CUTOFF = 0.62
MAX_SUGGESTIONS = 5
VOCAB_LIMIT = 4000

FILTER_KEYS = ('genre', 'artist', 'album', 'year', 'decade', 'era')

SORT_KEYS = tuple(track_db.ORDER_CLAUSES.keys())


class SearchResult:

    def __init__(self, page, filters, suggestions=None, corrected_from=None,
                 facets=None):
        self.page = page
        self.filters = filters
        self.suggestions = suggestions or []
        self.corrected_from = corrected_from
        self.facets = facets or {}

    @property
    def total(self):
        return self.page.count

    @property
    def has_active_filters(self):
        return any(self.filters.get(k) for k in FILTER_KEYS)


def _tokenize(text):
    words = re.findall(r"[\w']+", (text or '').lower())
    return [w for w in words if len(w) > 1]


def _decade_start(value):
    digits = re.sub(r'\D', '', str(value or ''))
    if not digits:
        return None
    return (int(digits) // 10) * 10


def read_filters(params):
    filters = {key: (params.get(key) or '').strip() for key in FILTER_KEYS}
    return filters


def _sql_filters(filters):
    return {
        'genre': filters.get('genre'),
        'album': filters.get('album'),
        'era': filters.get('era'),
        'year': filters.get('year'),
        'decade': _decade_start(filters.get('decade')),
    }


def _conditions(filters, query, exclude=()):
    active = {k: ('' if k in exclude else v) for k, v in filters.items()}

    artist_tokens = []
    if active.get('artist'):
        artist_tokens = _tokenize(active['artist']) or [active['artist']]

    tokens = [] if 'q' in exclude else _tokenize(query)

    return track_db.build_conditions(
        _sql_filters(active),
        tokens=tokens,
        artist_tokens=artist_tokens,
    )


def _vocabulary():
    phrases = {t.strip() for t in track_db.search_vocabulary(VOCAB_LIMIT) if t and t.strip()}

    words = {}
    for phrase in phrases:
        for word in re.findall(r"[\w']+", phrase):
            if len(word) > 3:
                words.setdefault(word.lower(), word)

    return {p.lower(): p for p in phrases}, words


def close_matches(query, limit=MAX_SUGGESTIONS):
    phrases, words = _vocabulary()
    if not phrases:
        return []

    found = []

    def collect(needle, table):
        for candidate in difflib.get_close_matches(
            needle, list(table.keys()), n=limit, cutoff=FUZZY_CUTOFF
        ):
            term = table[candidate]
            if term not in found:
                found.append(term)

    collect(query.lower(), phrases)

    if len(found) < limit:
        for token in _tokenize(query):
            collect(token, words)
            if len(found) >= limit:
                break

    return found[:limit]


def _closest_artist(value):
    names = track_db.artist_names(VOCAB_LIMIT)
    if not names:
        return None

    lookup = {n.lower(): n for n in names}
    for name in names:
        for word in re.findall(r"[\w']+", name):
            if len(word) > 3:
                lookup.setdefault(word.lower(), name)

    matches = difflib.get_close_matches(
        value.lower(), list(lookup.keys()), n=1, cutoff=FUZZY_CUTOFF
    )
    return lookup[matches[0]] if matches else None


def _options(pairs, selected):
    options = []
    for name, count in pairs:
        if count or (selected and str(name).lower() == str(selected).lower()):
            options.append({'name': name, 'count': count})
    return options


def facets(filters, query=''):
    where, params = _conditions(filters, query, exclude=('genre',))
    genres = _options(
        [(r.name, r.count) for r in track_db.genre_counts(where, params)],
        filters.get('genre'),
    )

    where, params = _conditions(filters, query, exclude=('era',))
    eras = _options(
        [(r.name, r.count) for r in track_db.era_counts(where, params)],
        filters.get('era'),
    )

    where, params = _conditions(filters, query, exclude=('year', 'decade'))
    year_rows = track_db.year_counts(where, params)

    decade_totals = {}
    for row in year_rows:
        label = f'{(row.year // 10) * 10}s'
        decade_totals[label] = decade_totals.get(label, 0) + row.count

    years = _options(
        [(r.year, r.count) for r in year_rows],
        filters.get('year'),
    )
    decades = _options(
        sorted(decade_totals.items(), key=lambda kv: -int(kv[0][:4])),
        filters.get('decade'),
    )

    return {'genres': genres, 'years': years, 'decades': decades, 'eras': eras}


def search_tracks(params, page=1, per_page=track_db.PER_PAGE):
    filters = read_filters(params)
    query = (params.get('q') or '').strip()

    sort = (params.get('sort') or track_db.DEFAULT_SORT).strip()
    if sort not in SORT_KEYS:
        sort = track_db.DEFAULT_SORT

    where, sql_params = _conditions(filters, query)
    total = track_db.count_tracks(where, sql_params)

    suggestions = []
    corrected_from = None

    if total == 0 and (query or filters['artist']):

        if filters['artist']:
            corrected_artist = _closest_artist(filters['artist'])
            if corrected_artist:
                candidate = dict(filters, artist=corrected_artist)
                cand_where, cand_params = _conditions(candidate, query)
                if track_db.count_tracks(cand_where, cand_params):
                    corrected_from = filters['artist']
                    filters['artist'] = corrected_artist
                    where, sql_params = cand_where, cand_params
                    total = track_db.count_tracks(where, sql_params)

        if total == 0 and query:
            suggestions = close_matches(query)
            for suggestion in suggestions:
                cand_where, cand_params = _conditions(filters, suggestion)
                if track_db.count_tracks(cand_where, cand_params):
                    corrected_from = query
                    query = suggestion
                    where, sql_params = cand_where, cand_params
                    total = track_db.count_tracks(where, sql_params)
                    break

    num_pages = max(1, -(-total // per_page))
    page_no = core.page_number(page, num_pages)
    rows = track_db.fetch_page(where, sql_params, sort, page_no, per_page)
    page_obj = core.paginate(rows, total, page_no, per_page)

    computed_facets = facets(filters, query)

    filters['q'] = query
    filters['sort'] = sort
    return SearchResult(page_obj, filters, suggestions, corrected_from, computed_facets)
