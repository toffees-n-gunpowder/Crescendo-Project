from django.core.management.base import BaseCommand

from music.db import catalog, core


class Command(BaseCommand):
    help = 'Numbers each album\'s tracks 1..n instead of leaving them all at 1.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report without saving.')

    def handle(self, *args, **options):
        multi = core.scalar("""
            SELECT COUNT(*) FROM (
                SELECT album_id FROM music_track
                GROUP BY album_id HAVING COUNT(*) > 1
            ) AS multi_track_albums
        """) or 0

        wrong = core.scalar("""
            SELECT COUNT(*) FROM (
                SELECT id, track_number,
                       ROW_NUMBER() OVER (PARTITION BY album_id ORDER BY id) AS position
                FROM music_track
            ) AS numbered
            WHERE track_number IS DISTINCT FROM position
        """) or 0

        self.stdout.write(f'{multi} albums hold more than one track.')
        self.stdout.write(f'{wrong} tracks are numbered incorrectly.')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING(
                f'Dry run - would renumber {wrong} tracks.'
            ))
            return

        updated = catalog.renumber_tracks_within_albums()
        self.stdout.write(self.style.SUCCESS(f'Renumbered {updated} tracks.'))
