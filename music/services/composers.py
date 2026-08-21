"""
Composer detection and crediting.

Jamendo credits the *performer* of a classical recording ("OnClassical",
"Esther Garcia"), never the composer - Mozart only ever appears as text inside
the track title. That makes "artist = Mozart" return nothing, because no such
Artist row exists.

This module recognises composers in track/album titles and credits them as real
Artist records with the 'writer' role, so ordinary artist queries find them.
"""

import re

from music.models import Artist, TrackCredit

# canonical display name -> (period, extra aliases beyond the surname)
COMPOSER_REGISTRY = {
    'Wolfgang Amadeus Mozart': ('Classical Era', ['mozart', 'w.a. mozart', 'wa mozart', 'amadeus']),
    'Ludwig van Beethoven': ('Classical Era', ['beethoven', 'van beethoven']),
    'Joseph Haydn': ('Classical Era', ['haydn']),
    'Johann Sebastian Bach': ('Baroque', ['bach', 'j.s. bach', 'js bach']),
    'Antonio Vivaldi': ('Baroque', ['vivaldi']),
    'George Frideric Handel': ('Baroque', ['handel', 'haendel', 'händel']),
    'Franz Schubert': ('Romantic', ['schubert']),
    'Frederic Chopin': ('Romantic', ['chopin']),
    'Franz Liszt': ('Romantic', ['liszt']),
    'Johannes Brahms': ('Romantic', ['brahms']),
    'Pyotr Ilyich Tchaikovsky': ('Romantic', ['tchaikovsky', 'tschaikowsky', 'chaikovsky']),
    'Edvard Grieg': ('Romantic', ['grieg']),
    'Antonin Dvorak': ('Romantic', ['dvorak', 'dvorák', 'dvořák']),
    'Robert Schumann': ('Romantic', ['schumann']),
    'Felix Mendelssohn': ('Romantic', ['mendelssohn']),
    'Giuseppe Verdi': ('Romantic', ['verdi']),
    'Richard Wagner': ('Romantic', ['wagner']),
    'Claude Debussy': ('Impressionist', ['debussy']),
    'Maurice Ravel': ('Impressionist', ['ravel']),
    'Erik Satie': ('Impressionist', ['satie']),
    'Sergei Prokofiev': ('Modern', ['prokofiev', 'prokofieff']),
    'Dmitri Shostakovich': ('Modern', ['shostakovich', 'schostakowitsch']),
    'Igor Stravinsky': ('Modern', ['stravinsky', 'strawinsky']),
    'Sergei Rachmaninoff': ('Modern', ['rachmaninoff', 'rachmaninov', 'rachmaninow']),
    'Gustav Mahler': ('Romantic', ['mahler']),
    'Camille Saint-Saens': ('Romantic', ['saint-saens', 'saint saens']),
    'Georges Bizet': ('Romantic', ['bizet']),
    'Modest Mussorgsky': ('Romantic', ['mussorgsky', 'moussorgsky']),
    'Niccolo Paganini': ('Romantic', ['paganini']),
    'Domenico Scarlatti': ('Baroque', ['scarlatti']),
    'Henry Purcell': ('Baroque', ['purcell']),
    'Gabriel Faure': ('Romantic', ['faure', 'fauré']),
    'Cesar Franck': ('Romantic', ['franck']),
    'Jean Sibelius': ('Romantic', ['sibelius']),
}


def _alias_pattern(alias):
    """
    Word-boundary regex for one alias.

    The boundaries matter: a naive "bach" substring search would also fire on
    "Offenbach" and "Bachata".
    """
    return re.compile(r'\b' + re.escape(alias) + r'\b', re.IGNORECASE)


# Precompiled so the backfill can scan hundreds of tracks cheaply.
_PATTERNS = [
    (canonical, period, [_alias_pattern(a) for a in aliases])
    for canonical, (period, aliases) in COMPOSER_REGISTRY.items()
]


def detect(*texts):
    """Return the canonical composer names mentioned across the given strings."""
    haystack = ' '.join(t for t in texts if t)
    if not haystack:
        return []

    found = []
    for canonical, _period, patterns in _PATTERNS:
        if any(p.search(haystack) for p in patterns):
            found.append(canonical)
    return found


def period_for(canonical):
    entry = COMPOSER_REGISTRY.get(canonical)
    return entry[0] if entry else None


def credit(track, canonical):
    """
    Credit one composer on a track as a 'writer'.

    Returns True when a new credit was created.
    """
    artist, _ = Artist.objects.get_or_create(name=canonical)
    _, created = TrackCredit.objects.get_or_create(
        track=track, artist=artist, role='writer'
    )
    return created


def credit_detected(track):
    """
    Scan a track's title and album title and credit every composer found.

    Returns the list of composers newly credited.
    """
    album_title = track.album.title if track.album_id else ''
    added = []
    for canonical in detect(track.title, album_title):
        if credit(track, canonical):
            added.append(canonical)
    return added
