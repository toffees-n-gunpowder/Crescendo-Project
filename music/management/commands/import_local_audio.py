from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse

from music.db import audio as audio_db, core, uploads


class Command(BaseCommand):
    help = ('Moves audio still sitting in media/ into the database, so it plays '
            'on every machine sharing this database rather than only this one.')

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would move without writing anything.')

    def handle(self, *args, **options):
        rows = core.query(
            """
            SELECT id, title, audio_file
            FROM music_track
            WHERE audio_file LIKE %s
            ORDER BY id
            """,
            [settings.MEDIA_URL + '%'],
        )

        if not rows:
            self.stdout.write('No tracks point at local files. Nothing to move.')
            return

        moved = missing = 0

        for row in rows:
            relative = row.audio_file[len(settings.MEDIA_URL):]
            path = Path(settings.MEDIA_ROOT) / relative

            if not path.exists():
                self.stdout.write(self.style.WARNING(
                    f'  [{row.id}] "{row.title}" - file not on this machine: {relative}'
                ))
                missing += 1
                continue

            content = path.read_bytes()
            size_mb = len(content) / (1024 * 1024)

            if options['dry_run']:
                self.stdout.write(f'  [{row.id}] "{row.title}" - would move {size_mb:.1f} MB')
                moved += 1
                continue

            audio_db.store(row.id, content, audio_db.content_type_for(relative), relative)
            uploads.set_audio_url(row.id, reverse('track_audio', args=[row.id]))

            self.stdout.write(self.style.SUCCESS(
                f'  [{row.id}] "{row.title}" - moved {size_mb:.1f} MB into the database'
            ))
            moved += 1

        self.stdout.write('')
        if options['dry_run']:
            self.stdout.write(f'{moved} track(s) would move. Re-run without --dry-run.')
        else:
            self.stdout.write(self.style.SUCCESS(f'{moved} track(s) moved.'))
            self.stdout.write(
                f'Database now holds {audio_db.total_bytes() / (1024*1024):.1f} MB of audio.'
            )

        if missing:
            self.stdout.write(self.style.WARNING(
                f'{missing} track(s) reference a file that is not on this machine. '
                'Run this command on the machine that has them.'
            ))
