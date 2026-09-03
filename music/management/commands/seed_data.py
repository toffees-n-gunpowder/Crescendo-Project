from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from music.db import catalog
from music.services import jamendo
from music.services.console import safe

SPREAD_TAGS = [
    'classical', 'jazz', 'rock', 'pop', 'electronic', 'hiphop',
    'metal', 'folk', 'blues', 'lounge', 'ambient', 'soundtrack',
]


class Command(BaseCommand):
    help = 'Seeds the database with tracks from the Jamendo API.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit', type=int, default=200,
            help='How many tracks to import (per tag when --spread is used). Default 200.',
        )
        parser.add_argument(
            '--tags', type=str, default='',
            help='Comma-separated Jamendo genre tags, e.g. --tags jazz,blues',
        )
        parser.add_argument(
            '--order', type=str, default='popularity_total',
            help='Jamendo sort order: popularity_total, popularity_month, releasedate_desc, downloads_total.',
        )
        parser.add_argument(
            '--offset', type=int, default=0,
            help='Skip this many results - useful for topping up an already-seeded database.',
        )
        parser.add_argument(
            '--spread', action='store_true',
            help='Import --limit tracks for each genre in a curated tag list.',
        )
        parser.add_argument(
            '--flush', action='store_true',
            help='Delete every existing track/album/artist before importing.',
        )

    def handle(self, *args, **options):
        if options['flush']:
            self._flush()

        if options['spread']:
            batches = [(tag, options['limit']) for tag in SPREAD_TAGS]
        elif options['tags']:
            tags = [t.strip() for t in options['tags'].split(',') if t.strip()]
            batches = [(tag, options['limit']) for tag in tags]
        else:
            batches = [(None, options['limit'])]

        total_new = 0
        total_seen = 0

        for tag, limit in batches:
            label = tag or 'all genres'
            self.stdout.write(f'\nFetching up to {limit} tracks from Jamendo ({label})...')

            try:
                items = jamendo.fetch_tracks(
                    limit=limit,
                    offset=options['offset'],
                    order=options['order'],
                    tags=tag,
                )
                new, seen = self._import_batch(items)
            except jamendo.JamendoError as exc:
                raise CommandError(str(exc))

            total_new += new
            total_seen += seen
            self.stdout.write(f'  {label}: {seen} returned, {new} new.')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. {total_seen} tracks returned by Jamendo, {total_new} newly added.'
        ))
        self.stdout.write(
            f"Catalogue now holds {catalog.count('music_track')} tracks "
            f"across {catalog.count('music_genre')} genres and "
            f"{catalog.count('music_artist')} artists."
        )

    def _import_batch(self, items):
        new = 0
        seen = 0
        for item in items:
            seen += 1
            try:
                with transaction.atomic():
                    track_id, created = jamendo.import_track(item)
            except Exception as exc:
                self.stderr.write(safe(f'  skipped "{item.get("name", "?")}": {exc}'))
                continue
            if created:
                new += 1
                self.stdout.write(safe(
                    f'  + {item.get("name", "?")} - {item.get("artist_name", "?")}'
                ))
        return new, seen

    def _flush(self):
        self.stdout.write(self.style.WARNING('Flushing existing catalogue...'))
        deleted = catalog.flush_catalogue()
        for table, rows in deleted.items():
            if rows:
                self.stdout.write(f'  {table}: {rows} rows')
        self.stdout.write(self.style.WARNING('Catalogue cleared.'))
