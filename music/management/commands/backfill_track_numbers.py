"""
Give every track its position within its album.

Track.track_number defaults to 1 and the Jamendo importer never set it, so all
649 tracks claim to be track 1. That breaks anything that orders by position -
including the browse page, which interleaves albums by track number so the grid
does not show the same cover six times in a row.

Numbering follows the order tracks were imported (their primary key), which for
a Jamendo album matches the order the API returned them.

    python manage.py backfill_track_numbers --dry-run
    python manage.py backfill_track_numbers
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from music.models import Album, Track
from music.services.console import safe


class Command(BaseCommand):
    help = 'Numbers each album\'s tracks 1..n instead of leaving them all at 1.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report without saving.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        albums = Album.objects.prefetch_related('tracks').order_by('id')

        albums_touched = 0
        tracks_touched = 0
        multi_track = 0

        for album in albums:
            tracks = list(album.tracks.order_by('id'))
            if len(tracks) > 1:
                multi_track += 1

            updates = []
            for position, track in enumerate(tracks, start=1):
                if track.track_number != position:
                    track.track_number = position
                    updates.append(track)

            if not updates:
                continue

            albums_touched += 1
            tracks_touched += len(updates)

            if len(tracks) > 1:
                self.stdout.write(safe(
                    f'  {album.title[:46]:48} -> numbered 1..{len(tracks)}'
                ))

            if not dry_run:
                with transaction.atomic():
                    Track.objects.bulk_update(updates, ['track_number'])

        self.stdout.write('')
        self.stdout.write(
            f'{multi_track} albums hold more than one track.'
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'Dry run - would renumber {tracks_touched} tracks '
                f'across {albums_touched} albums.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Renumbered {tracks_touched} tracks across {albums_touched} albums.'
            ))
