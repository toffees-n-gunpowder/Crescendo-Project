import time
from datetime import datetime

import requests
from django.conf import settings

from music.db import catalog

MAX_PAGE_SIZE = 200
REQUEST_TIMEOUT = 30
REQUEST_PAUSE = 0.35
EMPTY_RETRIES = 2
RETRY_BACKOFF = 2.0

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
    pass


def client_id():
    return getattr(settings, 'JAMENDO_CLIENT_ID', '') or ''


def normalize_genre(raw):
    if not raw:
        return 'Indie'
    key = str(raw).strip().lower().replace('-', '').replace('_', '').replace(' ', '')
    if key in GENRE_ALIASES:
        return GENRE_ALIASES[key]
    return str(raw).strip().replace('_', ' ').title()


def decade_label(release_date):
    if not release_date:
        return None
    return f"{(release_date.year // 10) * 10}s"


def parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _request_page(query):
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

        if got < page_size:
            return


def import_track(item, genre_override=None, era_override=None):
    artist_name = (item.get('artist_name') or 'Unknown Artist').strip()
    artist_id = catalog.get_or_create_artist(artist_name)

    release_date = parse_date(item.get('releasedate')) or datetime.now().date()
    album_title = (item.get('album_name') or 'Singles').strip()
    cover_url = item.get('album_image') or item.get('image') or ''

    album_id = catalog.find_album(album_title, artist_id)
    if album_id:
        catalog.set_album_cover_if_blank(album_id, cover_url)
    else:
        album_id = catalog.create_album(album_title, release_date, cover_url)
        catalog.add_album_credit(album_id, artist_id, 'primary')

    if genre_override:
        genre_name = genre_override
    else:
        tags = (item.get('musicinfo') or {}).get('tags', {}).get('genres') or []
        genre_name = normalize_genre(tags[0] if tags else 'Indie')
    genre_id = catalog.get_or_create_genre(genre_name)

    era_id = None
    if era_override:
        era_id = catalog.get_or_create_era(
            era_override, f'Music from the {era_override}.'
        )

    title = (item.get('name') or 'Unknown Track').strip()
    track_id = catalog.find_track(title, album_id)
    created = track_id is None

    if created:
        track_id = catalog.create_track(
            title, album_id, genre_id, era_id,
            item.get('duration') or 0, item.get('audio') or '',
        )
    else:
        catalog.backfill_track_fields(
            track_id,
            audio_file=item.get('audio') or None,
            genre_id=genre_id,
            era_id=era_id,
        )

    catalog.add_track_credit(track_id, artist_id, 'primary')
    return track_id, created
