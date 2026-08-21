"""
Catalogue search: multi-field matching, faceted filters and fuzzy fallback.

The public entry point is `search_tracks(request.GET)`, which returns a
SearchResult carrying the queryset plus everything the template needs to render
the filter bar and the "did you mean" hint.
"""

import difflib
import re

from django.db.models import Count, Q

from music.models import Album, Artist, Era, Genre, Track

# How similar a word has to be before we treat it as a typo of a catalogue term.
FUZZY_CUTOFF = 0.62
MAX_SUGGESTIONS = 5
# Cap on how many catalogue terms we pull into memory for fuzzy comparison.
VOCAB_LIMIT = 4000

# The dimensions a user can filter on. Kept separate from 'q' and 'sort',
# which are not facets.
FILTER_KEYS = ('genre', 'artist', 'album', 'year', 'decade', 'era')

SORT_OPTIONS = {
    # Track.Meta.ordering is ['album', 'track_number'], which groups every
    # album's tracks together - so a browse page shows the same cover five or
    # six times in a row. Leading with track_number interleaves the albums
    # instead: track 1 of many different albums, then track 2, and so on.
    'relevance': ['track_number', 'album__title', 'title'],
    'album': ['album__title', 'track_number'],
    'title': ['title'],
    'newest': ['-album__release_date', 'title'],
    'oldest': ['album__release_date', 'title'],
    'longest': ['-duration_sec'],
    'shortest': ['duration_sec'],
}


class SearchResult:
    """Everything the home template needs to render a result page."""

    def __init__(self, queryset, filters, suggestions=None, corrected_from=None,
                 facets=None):
        self.queryset = queryset
        self.filters = filters
        self.suggestions = suggestions or []
        # Set when we silently re-ran the search using a corrected spelling.
        self.corrected_from = corrected_from
        # Filter options counted against this exact selection.
        self.facets = facets or {}

    @property
    def has_active_filters(self):
        return any(self.filters.get(k) for k in FILTER_KEYS)


def _base_queryset():
    return (
        Track.objects
        .select_related('album', 'genre', 'era')
        .prefetch_related('artists')
    )


def _tokenize(query):
    """Split a query into meaningful words, dropping punctuation and noise."""
    words = re.findall(r"[\w']+", query.lower())
    return [w for w in words if len(w) > 1]


def _text_filter(token):
    """One token must appear somewhere in the track's searchable text."""
    return (
        Q(title__icontains=token)
        | Q(artists__name__icontains=token)
        | Q(album__title__icontains=token)
        | Q(genre__name__icontains=token)
        | Q(era__name__icontains=token)
    )


def _apply_query(queryset, query):
    """
    AND the tokens together so "mozart piano" narrows rather than widens,
    but let each token match any field.
    """
    tokens = _tokenize(query)
    if not tokens:
        # Query was all punctuation or single letters - fall back to raw contains.
        return queryset.filter(_text_filter(query.strip())).distinct()

    for token in tokens:
        queryset = queryset.filter(_text_filter(token))
    return queryset.distinct()


def _vocabulary():
    """
    Two lookup tables used for typo correction:

    - phrases: whole titles / artist names / album titles ("Trio HxC")
    - words:   the individual words inside them ("relifion")

    Indexing words separately is what lets "releigion" find the track called
    "Un Poil De Relifion" - comparing against the full title alone scores too
    low for difflib to accept.
    """
    phrases = set()
    phrases.update(Track.objects.values_list('title', flat=True)[:VOCAB_LIMIT])
    phrases.update(Artist.objects.values_list('name', flat=True)[:VOCAB_LIMIT])
    phrases.update(Album.objects.values_list('title', flat=True)[:VOCAB_LIMIT])
    phrases.update(Genre.objects.values_list('name', flat=True))
    phrases = {p.strip() for p in phrases if p and p.strip()}

    words = {}
    for phrase in phrases:
        for word in re.findall(r"[\w']+", phrase):
            # Very short words generate noisy matches, so skip them.
            if len(word) > 3:
                words.setdefault(word.lower(), word)

    return {p.lower(): p for p in phrases}, words


def close_matches(query, limit=MAX_SUGGESTIONS):
    """
    Suggest catalogue terms close to `query`.

    Tries the whole phrase first, then each individual word, so both
    "Trioo HxC" -> "Trio HxC" and "beathoven sonata" -> "Beethoven" work.
    """
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


def _artist_filter(queryset, value):
    """
    Match an artist by any part of their name, in any order.

    "amadeus mozart", "mozart" and "Mozart, W.A." all have to land on
    "Wolfgang Amadeus Mozart", so each word is required but position is not.
    Composers are credited as writers (see services.composers), which is what
    lets a composer name match at all.
    """
    # Keep the unfiltered queryset around: the fallbacks below must start from
    # it, not from the narrowed one that just returned nothing.
    base = queryset

    matched = base
    for token in _tokenize(value) or [value.strip()]:
        matched = matched.filter(artists__name__icontains=token)
    matched = matched.distinct()

    if matched.exists():
        return matched

    # Nothing matched - try the closest artist name, so "beethovan" still
    # resolves. Individual name words are indexed too, because a full-name
    # comparison ("beethovan" vs "Ludwig van Beethoven") scores too low.
    names = [n for n in Artist.objects.values_list('name', flat=True)[:VOCAB_LIMIT] if n]
    lookup = {n.lower(): n for n in names}
    for name in names:
        for word in re.findall(r"[\w']+", name):
            if len(word) > 3:
                lookup.setdefault(word.lower(), name)

    for candidate in difflib.get_close_matches(
        value.lower(), list(lookup.keys()), n=1, cutoff=FUZZY_CUTOFF
    ):
        return base.filter(artists__name__iexact=lookup[candidate]).distinct()

    # Last resort: the name may only exist inside the title (a composer we do
    # not recognise yet). Better to show those than an empty page.
    return base.filter(
        Q(title__icontains=value) | Q(album__title__icontains=value)
    ).distinct()


def _apply_filters(queryset, filters):
    if filters['genre']:
        queryset = queryset.filter(genre__name__iexact=filters['genre'])

    if filters['artist']:
        queryset = _artist_filter(queryset, filters['artist'])

    if filters['album']:
        queryset = queryset.filter(album__title__icontains=filters['album'])

    if filters['era']:
        queryset = queryset.filter(era__name__iexact=filters['era'])

    if filters['year']:
        try:
            queryset = queryset.filter(album__release_date__year=int(filters['year']))
        except (TypeError, ValueError):
            pass

    if filters['decade']:
        # Accepts "1990s" or "1990"; both mean 1990-1999 inclusive.
        digits = re.sub(r'\D', '', str(filters['decade']))
        if digits:
            start = (int(digits) // 10) * 10
            queryset = queryset.filter(
                album__release_date__year__gte=start,
                album__release_date__year__lte=start + 9,
            )

    return queryset


def search_tracks(params):
    """
    Run a catalogue search from a GET QueryDict.

    Recognised keys: q, genre, artist, album, year, decade, era, sort.
    """
    filters = {
        'genre': (params.get('genre') or '').strip(),
        'artist': (params.get('artist') or '').strip(),
        'album': (params.get('album') or '').strip(),
        'year': (params.get('year') or '').strip(),
        'decade': (params.get('decade') or '').strip(),
        'era': (params.get('era') or '').strip(),
    }
    query = (params.get('q') or '').strip()
    sort = (params.get('sort') or 'relevance').strip()

    queryset = _apply_filters(_base_queryset(), filters)

    suggestions = []
    corrected_from = None

    if query:
        matched = _apply_query(queryset, query)

        if not matched.exists():
            suggestions = close_matches(query)
            # If the best suggestion actually returns something, show those
            # results directly rather than a dead end.
            for suggestion in suggestions:
                retry = _apply_query(queryset, suggestion)
                if retry.exists():
                    matched = retry
                    corrected_from = query
                    query = suggestion
                    break

        queryset = matched

    order = SORT_OPTIONS.get(sort)
    if order:
        queryset = queryset.order_by(*order)

    # Facets are computed from the filters as finally resolved - including a
    # spelling correction - so the counts match what is on screen.
    computed_facets = facets(filters, query)

    filters['q'] = query
    filters['sort'] = sort
    return SearchResult(queryset, filters, suggestions, corrected_from, computed_facets)


def _facet_queryset(filters, query, exclude=()):
    """
    The result set as it would be *without* the named filters.

    Proper faceting excludes a dimension from its own counts: the Decade
    options must reflect the chosen genre, but not the chosen decade - or
    picking "2010s" would hide every other decade and you could never switch.
    """
    reduced = {k: ('' if k in exclude else v) for k, v in filters.items()}
    queryset = _apply_filters(_base_queryset(), reduced)
    if query and 'q' not in exclude:
        queryset = _apply_query(queryset, query)
    return queryset


def _options(pairs, selected):
    """
    Build dropdown options, dropping empties.

    An option with no results is a dead end, so it is hidden - except the one
    currently selected, which must stay so the control keeps its value.
    """
    options = []
    for name, count in pairs:
        if count or (selected and str(name).lower() == str(selected).lower()):
            options.append({'name': name, 'count': count})
    return options


def facets(filters=None, query=''):
    """
    Filter options counted against the *current* selection.

    Without this the dropdowns offer combinations that return nothing - the
    catalogue has no Metal from the 2020s, but a global facet list still
    advertises it.
    """
    filters = filters or {k: '' for k in FILTER_KEYS}

    # --- Genres, counted with every filter except genre itself -------------
    genre_rows = (
        _facet_queryset(filters, query, exclude=('genre',))
        .exclude(genre__isnull=True)
        .values('genre__name')
        .annotate(n=Count('id', distinct=True))
        .order_by('-n', 'genre__name')
    )
    genres = _options(
        [(r['genre__name'], r['n']) for r in genre_rows],
        filters.get('genre'),
    )

    # --- Musical periods ---------------------------------------------------
    era_rows = (
        _facet_queryset(filters, query, exclude=('era',))
        .exclude(era__isnull=True)
        .exclude(era__name__regex=r'^[0-9]{4}s$')
        .values('era__name')
        .annotate(n=Count('id', distinct=True))
        .order_by('era__name')
    )
    eras = _options(
        [(r['era__name'], r['n']) for r in era_rows],
        filters.get('era'),
    )

    # --- Release year and decade share one queryset ------------------------
    date_rows = (
        _facet_queryset(filters, query, exclude=('year', 'decade'))
        .exclude(album__release_date__isnull=True)
        .values('album__release_date__year')
        .annotate(n=Count('id', distinct=True))
    )

    year_counts = {}
    for row in date_rows:
        year = row['album__release_date__year']
        year_counts[year] = year_counts.get(year, 0) + row['n']

    decade_counts = {}
    for year, count in year_counts.items():
        label = f'{(year // 10) * 10}s'
        decade_counts[label] = decade_counts.get(label, 0) + count

    years = _options(
        sorted(year_counts.items(), key=lambda kv: -kv[0]),
        filters.get('year'),
    )
    decades = _options(
        sorted(decade_counts.items(), key=lambda kv: -int(kv[0][:4])),
        filters.get('decade'),
    )

    return {
        'genres': genres,
        'years': years,
        'decades': decades,
        'eras': eras,
    }
