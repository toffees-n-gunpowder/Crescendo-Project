"""
Thin client + importer for the Jamendo v3.0 API.

Jamendo hosts Creative Commons licensed music, so every track it returns comes
with a legally streamable MP3 URL that we can drop straight into Track.audio_file.

Docs: https://developer.jamendo.com/v3.0/tracks
Get your own Client ID at https://devportal.jamendo.com/ and put it in .env as
JAMENDO_CLIENT_ID (see settings.JAMENDO_CLIENT_ID).
"""

import time
from datetime import datetime

import requests
from django.conf import settings

from music.models import Album, AlbumCredit, Artist, Era, Genre, Track, TrackCredit

# Jamendo caps a single response at 200 rows; anything larger must be paged.
MAX_PAGE_SIZE = 200
REQUEST_TIMEOUT = 30
# Jamendo throttles bursts by answering "success" with an empty result list, so
# we pace requests and retry an empty first page before believing it.
REQUEST_PAUSE = 0.35
EMPTY_RETRIES = 2
RETRY_BACKOFF = 2.0

# Jamendo tags are lowercase slugs. Map them onto the display names we want to
# show as genre chips, so "hiphop" and "hip_hop" both land on "Hip-Hop".
GENRE_ALIASES = {
    'hiphop': 'Hip-Hop',
    'rap': 'Hip-Hop',
    'rnb': 'R&B',
    'electro': 'Electronic',
    'electronic': 'Electronic',
    'edm': 'Electronic',
    'house': 'Electronic',
    'techno': 'Electronic',
    'dance': 'Electronic',
    'popfolk': 'Folk',
    'folk': 'Folk',
    'songwriter': 'Folk',
    'classical': 'Classical',
    'orchestral': 'Classical',
    'chamber': 'Classical',
    'opera': 'Classical',
    'baroque': 'Classical',
    'piano': 'Classical',
    'soundtrack': 'Soundtrack',
    'jazz': 'Jazz',
    'blues': 'Blues',
    'rock': 'Rock',
    'metal': 'Metal',
    'punk': 'Punk',
    'indie': 'Indie',
    'pop': 'Pop',
    'lounge': 'Lounge',
    'ambient': 'Ambient',
    'world': 'World',
    'reggae': 'Reggae',
    'country': 'Country',
}


class JamendoError(RuntimeError):
    """Raised when Jamendo refuses a request or returns an error payload."""


def client_id():
    return getattr(settings, 'JAMENDO_CLIENT_ID', '') or ''


def normalize_genre(raw):
    """Turn a raw Jamendo tag into a tidy display genre name."""
    if not raw:
        return 'Indie'
    key = str(raw).strip().lower().replace('-', '').replace('_', '').replace(' ', '')
    if key in GENRE_ALIASES:
        return GENRE_ALIASES[key]
    return str(raw).strip().replace('_', ' ').title()


def decade_label(release_date):
    """1994-05-02 -> '1990s'. Used to fill the Era table for decade filtering."""
    if not release_date:
        return None
    return f"{(release_date.year // 10) * 10}s"


def parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _request_page(query):
    """Fire one /tracks/ request and return its results list."""
    time.sleep(REQUEST_PAUSE)

    try:
        response = requests.get(
            f"{settings.JAMENDO_API_BASE}/tracks/",
            params=query,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise JamendoError(f'Could not reach Jamendo: {exc}') from exc

    if response.status_code != 200:
        raise JamendoError(
            f'Jamendo returned HTTP {response.status_code}. Check your Client ID.'
        )

    payload = response.json()
    headers = payload.get('headers', {})
    if headers.get('status') != 'success':
        raise JamendoError(headers.get('error_message') or 'Jamendo rejected the request.')

    return payload.get('results', [])


def fetch_tracks(limit=200, offset=0, **params):
    """
    Yield raw Jamendo track dicts, transparently paging past the 200-row cap.

    Any extra keyword lands in the query string, so callers can pass
    tags='classical', search='mozart', order='popularity_total', etc.
    """
    cid = client_id()
    if not cid:
        raise JamendoError(
            'No Jamendo Client ID configured. Add JAMENDO_CLIENT_ID=... to your .env file.'
        )

    remaining = limit
    current_offset = offset
    first_page = True

    while remaining > 0:
        page_size = min(remaining, MAX_PAGE_SIZE)
        query = {
            'client_id': cid,
            'format': 'json',
            'limit': page_size,
            'offset': current_offset,
            'include': 'musicinfo',
            'audioformat': 'mp32',
        }
        query.update({k: v for k, v in params.items() if v not in (None, '')})

        results = _request_page(query)

        # An empty first page is usually throttling rather than an empty
        # catalogue, so back off and ask again before giving up.
        attempt = 0
        while not results and first_page and attempt < EMPTY_RETRIES:
            attempt += 1
            time.sleep(RETRY_BACKOFF * attempt)
            results = _request_page(query)

        first_page = False

        if not results:
            return

        for item in results:
            yield item

        got = len(results)
        remaining -= got
        current_offset += got

        # A short page means we reached the end of the catalogue for this query.
        if got < page_size:
            return


def _get_or_create_album(title, artist, release_date, cover_url):
    """
    Look albums up per-artist. A plain get_or_create(title=...) would merge every
    'Greatest Hits' or 'Unknown Album' from different artists into one record.
    """
    album = Album.objects.filter(
        title=title, albumcredit__artist=artist, albumcredit__role='primary'
    ).first()

    if album:
        if cover_url and not album.cover_url:
            album.cover_url = cover_url
            album.save(update_fields=['cover_url'])
        return album, False

    album = Album.objects.create(
        title=title,
        release_date=release_date,
        cover_url=cover_url or '',
    )
    AlbumCredit.objects.get_or_create(album=album, artist=artist, role='primary')
    return album, True


def import_track(item, genre_override=None, era_override=None):
    """
    Persist one raw Jamendo track dict as Artist + Album + Genre + Era + Track.

    Returns (track, created). Safe to run repeatedly - everything is get_or_create.
    """
    artist_name = (item.get('artist_name') or 'Unknown Artist').strip()
    artist, _ = Artist.objects.get_or_create(name=artist_name)

    release_date = parse_date(item.get('releasedate')) or datetime.now().date()
    album_title = (item.get('album_name') or 'Singles').strip()
    album, _ = _get_or_create_album(
        album_title,
        artist,
        release_date,
        item.get('album_image') or item.get('image') or '',
    )

    if genre_override:
        genre_name = genre_override
    else:
        tags = (item.get('musicinfo') or {}).get('tags', {}).get('genres') or []
        genre_name = normalize_genre(tags[0] if tags else 'Indie')
    genre, _ = Genre.objects.get_or_create(name=genre_name)

    # Era means *musical period* (Baroque, Romantic, ...), which only the
    # classical seeder knows. Release decade is a separate axis, derived from
    # album.release_date at query time - so nothing is invented here.
    era = None
    era_name = era_override
    if era_name:
        era, _ = Era.objects.get_or_create(
            name=era_name,
            defaults={'description': f'Music from the {era_name}.'},
        )

    track, created = Track.objects.get_or_create(
        title=(item.get('name') or 'Unknown Track').strip(),
        album=album,
        defaults={
            'genre': genre,
            'era': era,
            'duration_sec': item.get('duration') or 0,
            'audio_file': item.get('audio') or '',
        },
    )

    # Backfill fields on tracks imported before this data was being captured.
    if not created:
        changed = []
        if not track.audio_file and item.get('audio'):
            track.audio_file = item['audio']
            changed.append('audio_file')
        if track.genre_id is None and genre:
            track.genre = genre
            changed.append('genre')
        if track.era_id is None and era:
            track.era = era
            changed.append('era')
        if changed:
            track.save(update_fields=changed)

    TrackCredit.objects.get_or_create(track=track, artist=artist, role='primary')
    return track, created
