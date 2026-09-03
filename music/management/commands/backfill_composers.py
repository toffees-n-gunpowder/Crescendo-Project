from django.core.management.base import BaseCommand
from django.db import transaction

from music.db import catalog
from music.services import composers
from music.services.console import safe


class Command(BaseCommand):
    help = 'Credits recognised composers as writers on existing tracks.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be credited without writing anything.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        tracks = catalog.tracks_with_album_titles()

        scanned = 0
        matched = 0
        credits_added = 0
        per_composer = {}

        for track in tracks:
            scanned += 1
            found = composers.detect(track.title, track.album_title or '')
            if not found:
                continue

            matched += 1
            for canonical in found:
                per_composer[canonical] = per_composer.get(canonical, 0) + 1

                if dry_run:
                    continue

                with transaction.atomic():
                    if composers.credit(track.id, canonical):
                        credits_added += 1
                        self.stdout.write(safe(f'  + {canonical} <- {track.title[:60]}'))

        self.stdout.write('')
        self.stdout.write(f'Scanned {scanned} tracks; {matched} mention a known composer.')

        if per_composer:
            self.stdout.write('\nComposers found:')
            for name, count in sorted(per_composer.items(), key=lambda kv: -kv[1]):
                self.stdout.write(f'  {name:32} {count:3d} track(s)')

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDry run - nothing was written.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nAdded {credits_added} composer credits.'))
