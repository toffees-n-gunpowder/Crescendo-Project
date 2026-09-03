import re

from music.db import catalog

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
    return re.compile(r'\b' + re.escape(alias) + r'\b', re.IGNORECASE)


_PATTERNS = [
    (canonical, period, [_alias_pattern(a) for a in aliases])
    for canonical, (period, aliases) in COMPOSER_REGISTRY.items()
]


def detect(*texts):
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


def credit(track_id, canonical):
    artist_id = catalog.get_or_create_artist(canonical)
    return catalog.add_track_credit(track_id, artist_id, 'writer') > 0


def credit_detected(track_id, title, album_title=''):
    added = []
    for canonical in detect(title, album_title):
        if credit(track_id, canonical):
            added.append(canonical)
    return added
