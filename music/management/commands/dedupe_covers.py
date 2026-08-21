"""
Find and clear reused cover art using perceptual hashing.

Some Jamendo labels (OnClassical is the worst offender) upload one promotional
banner and reuse it as the artwork for every release. Each album gets its own
cover URL *and* its own re-encoded file, so neither string comparison nor an
MD5 of the bytes finds them - only the picture is the same.

This fingerprints every cover with dHash, clusters fingerprints that are within
a few bits of each other, and blanks cover_url on any image shared by several
albums. A blank cover_url makes partials/cover.html fall back to its
genre-themed tile, which looks deliberate instead of showing the same banner
twenty times down the page.

    python manage.py dedupe_covers --dry-run
    python manage.py dedupe_covers
    python manage.py dedupe_covers --threshold 2 --max-distance 8
"""

from concurrent.futures import ThreadPoolExecutor

import requests
from django.core.management.base import BaseCommand

from music.models import Album, Track
from music.services import imagehash
from music.services.console import safe

# Fetch a small rendition: plenty for a 8x8 fingerprint, cheap to download.
PROBE_WIDTH = 100
TIMEOUT = 20
WORKERS = 12


class Command(BaseCommand):
    help = 'Clears cover art reused across albums, detected by perceptual hash.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--threshold', type=int, default=3,
            help='An image shared by this many albums counts as a placeholder. Default 3.',
        )
        parser.add_argument(
            '--max-distance', type=int, default=5,
            help='Max Hamming distance (out of 64) to call two covers the same '
                 'picture. 0 is byte-identical-looking, 10 is loose. Default 5.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be cleared without writing anything.',
        )

    def handle(self, *args, **options):
        albums = list(
            Album.objects.exclude(cover_url='').values('id', 'title', 'cover_url')
        )
        if not albums:
            self.stdout.write('No albums with cover art.')
            return

        self.stdout.write(f'Fingerprinting {len(albums)} covers...')

        def probe(album):
            url = album['cover_url']
            for size in ('width=300', 'width=400', 'width=500', 'width=600'):
                url = url.replace(size, f'width={PROBE_WIDTH}')
            try:
                response = requests.get(url, timeout=TIMEOUT)
                if response.status_code != 200 or not response.content:
                    return album['id'], None
                return album['id'], imagehash.dhash(response.content)
            except requests.RequestException:
                return album['id'], None

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(probe, albums))

        fingerprints = [(a_id, h) for a_id, h in results if h is not None]
        broken = [a_id for a_id, h in results if h is None]

        self.stdout.write(
            f'Fingerprinted {len(fingerprints)}; {len(broken)} failed to load.\n'
        )

        groups = imagehash.cluster(fingerprints, options['max_distance'])
        threshold = options['threshold']
        reused = [g for g in groups if len(g) >= threshold]

        titles = {a['id']: a['title'] for a in albums}
        track_counts = {}
        for album_id in (i for g in reused for i in g):
            track_counts[album_id] = Track.objects.filter(album_id=album_id).count()

        doomed = []
        if reused:
            self.stdout.write(f'Reused artwork (same picture on {threshold}+ albums):')
            for group in sorted(reused, key=len, reverse=True):
                affected = sum(track_counts.get(i, 0) for i in group)
                self.stdout.write(
                    f'\n  {len(group)} albums / {affected} tracks share one image:'
                )
                for album_id in group[:5]:
                    self.stdout.write(safe(f'      - {titles[album_id][:58]}'))
                if len(group) > 5:
                    self.stdout.write(f'      ... and {len(group) - 5} more')
                doomed.extend(group)
        else:
            self.stdout.write('No reused cover art found.')

        if broken:
            self.stdout.write(f'\n{len(broken)} covers failed to load and will also be cleared.')
            doomed.extend(broken)

        self.stdout.write('')
        if options['dry_run']:
            self.stdout.write(self.style.WARNING(
                f'Dry run - would clear cover art on {len(doomed)} albums.'
            ))
            return

        updated = Album.objects.filter(id__in=doomed).update(cover_url='')
        remaining = Album.objects.exclude(cover_url='').count()
        self.stdout.write(self.style.SUCCESS(f'Cleared cover art on {updated} albums.'))
        self.stdout.write(
            f'{remaining} albums keep unique artwork; the rest now render a '
            f'genre-themed tile.'
        )
