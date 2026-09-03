import re

from django import template

register = template.Library()

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
    return _theme_for(genre_name)[0]


@register.filter
def genre_icon(genre_name):
    return _theme_for(genre_name)[1]


@register.filter
def cover_size(url, width=400):
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
    words = re.findall(r"[A-Za-z0-9]+", text or '')
    if not words:
        return '?'
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()
