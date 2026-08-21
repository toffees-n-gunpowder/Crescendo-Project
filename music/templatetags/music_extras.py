"""
Template helpers for presenting cover art.

Jamendo cover art is user-uploaded, so it arrives small and visually all over
the place. These filters give every tile a consistent, genre-appropriate
treatment and a designed fallback when the image is missing or fails to load.
"""

import re

from django import template

register = template.Library()

# Genre families -> (css theme slug, Font Awesome icon).
# Keys are matched as substrings of the lowercased genre name, so "Classical
# Crossover" and "Neo-Classical" both land on the classical theme.
GENRE_THEMES = [
    (('classical', 'baroque', 'orchestral', 'opera', 'chamber', 'piano'),
     ('classical', 'fa-solid fa-music')),
    (('jazz', 'swing', 'bossa', 'blues', 'soul', 'funk'),
     ('jazz', 'fa-solid fa-record-vinyl')),
    (('metal', 'punk', 'hardcore', 'grunge'),
     ('metal', 'fa-solid fa-drum')),
    (('rock', 'indie', 'alternative', 'garage'),
     ('rock', 'fa-solid fa-guitar')),
    (('electronic', 'electro', 'techno', 'house', 'trance', 'dance', 'edm', 'dubstep'),
     ('electronic', 'fa-solid fa-headphones')),
    (('ambient', 'chillout', 'chill', 'lounge', 'downtempo', 'newage'),
     ('ambient', 'fa-solid fa-moon')),
    (('hip-hop', 'hiphop', 'rap', 'trap'),
     ('hiphop', 'fa-solid fa-microphone-lines')),
    (('folk', 'country', 'acoustic', 'singer', 'world'),
     ('folk', 'fa-solid fa-guitar')),
    (('pop', 'r&b', 'rnb', 'disco'),
     ('pop', 'fa-solid fa-star')),
    (('soundtrack', 'cinematic', 'score'),
     ('soundtrack', 'fa-solid fa-film')),
]

DEFAULT_THEME = ('default', 'fa-solid fa-compact-disc')


def _theme_for(genre_name):
    name = (genre_name or '').strip().lower()
    if name:
        for keywords, theme in GENRE_THEMES:
            if any(k in name for k in keywords):
                return theme
    return DEFAULT_THEME


@register.filter
def genre_theme(genre_name):
    """CSS slug for a genre, e.g. 'classical'. Used as .cover-theme-<slug>."""
    return _theme_for(genre_name)[0]


@register.filter
def genre_icon(genre_name):
    """Font Awesome class for a genre, e.g. 'fa-solid fa-guitar'."""
    return _theme_for(genre_name)[1]


@register.filter
def cover_size(url, width=400):
    """
    Ask Jamendo for a larger rendition.

    Cover URLs arrive as ...&width=300, which is soft on high-DPI screens.
    Jamendo serves fixed widths only, so we snap to a supported one.
    """
    if not url:
        return url

    try:
        width = int(width)
    except (TypeError, ValueError):
        width = 400

    allowed = [50, 100, 130, 200, 300, 400, 500, 600]
    width = min(allowed, key=lambda w: abs(w - width))

    if 'width=' in url:
        return re.sub(r'width=\d+', f'width={width}', url)
    if '?' in url:
        return f'{url}&width={width}'
    return f'{url}?width={width}'


@register.filter
def initials(text):
    """One or two letters to sit inside a fallback tile."""
    words = re.findall(r"[A-Za-z0-9]+", text or '')
    if not words:
        return '?'
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()
